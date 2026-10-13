#include "app_ws_bridge.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>

#include "esp_event.h"
#include "esp_camera.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_websocket_client.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sdkconfig.h"
#include "mbedtls/base64.h"
#include "app_audio_record.h"
#include "app_imu.h"
#include "app_power.h"
#include "cJSON.h"
#include "tracked_chassis_control.h"
#include "ui.h"

#define SPARKBOT_WS_URI CONFIG_SPARKBOT_WS_URI
#define WS_TEXT_MAX_LEN (256 * 1024)
#define CAPTURE_IMAGE_MAX_COUNT 10

static const char *TAG = "ws_bridge";
static esp_websocket_client_handle_t s_ws_client;
static bool s_ws_connected;
static uint32_t s_move_generation;
static char s_auth_headers[512];
static bool s_status_task_started;
static TaskHandle_t s_reconnect_task_handle;
static bool s_capture_task_running;
static char *s_text_payload;
static int s_text_payload_len;

typedef struct {
    uint32_t generation;
    int delay_ms;
} move_stop_task_args_t;

typedef struct {
    int count;
    int interval_ms;
} capture_task_args_t;

static bool send_ws_text_timeout(const char *text, TickType_t timeout_ticks);

static const char *move_command_for_direction(const char *direction)
{
    if (!direction) {
        return NULL;
    }

    if (strcmp(direction, "forward") == 0) {
        return "x0.0y1.0";
    }

    if (strcmp(direction, "backward") == 0) {
        return "x0.0y-1.0";
    }

    if (strcmp(direction, "left") == 0) {
        return "x-1.0y0.0";
    }

    if (strcmp(direction, "right") == 0) {
        return "x1.0y0.0";
    }

    if (strcmp(direction, "stop") == 0) {
        return "x0.0y0.0";
    }

    return NULL;
}

static void move_stop_task(void *arg)
{
    move_stop_task_args_t *task_args = (move_stop_task_args_t *)arg;
    uint32_t generation = task_args->generation;
    int delay_ms = task_args->delay_ms;
    free(task_args);

    vTaskDelay(pdMS_TO_TICKS(delay_ms));
    if (generation == s_move_generation) {
        tracked_chassis_motion_control("x0.0y0.0");
        ESP_LOGI(TAG, "Auto stop after move duration");
    }

    vTaskDelete(NULL);
}

static bool dispatch_move_event(const char *direction, int duration_s)
{
    const char *command = move_command_for_direction(direction);
    if (!command) {
        return false;
    }

    if (duration_s < 0) {
        duration_s = 0;
    } else if (duration_s > 5) {
        duration_s = 5;
    }

    s_move_generation++;
    tracked_chassis_motion_control(command);

    if (strcmp(direction, "stop") != 0 && duration_s > 0) {
        move_stop_task_args_t *task_args = calloc(1, sizeof(*task_args));
        if (task_args) {
            task_args->generation = s_move_generation;
            task_args->delay_ms = duration_s * 1000;
            xTaskCreate(move_stop_task, "move_stop", 2048, task_args, 5, NULL);
        }
    }

    return true;
}

static bool dispatch_face_event(const char *expression_id)
{
    if (!expression_id) {
        return false;
    }

    if (strcmp(expression_id, "look") == 0) {
        ui_send_sys_event(ui_face, LV_EVENT_FACE_LOOK, NULL);
        return true;
    }

    if (strcmp(expression_id, "ask") == 0) {
        ui_send_sys_event(ui_face, LV_EVENT_FACE_ASK, NULL);
        return true;
    }

    if (strcmp(expression_id, "think") == 0) {
        ui_send_sys_event(ui_face, LV_EVENT_FACE_THINK, NULL);
        return true;
    }

    if (strcmp(expression_id, "speak") == 0) {
        ui_send_sys_event(ui_face, LV_EVENT_FACE_SPEAK, NULL);
        return true;
    }

    return false;
}

static void status_report_task(void *arg)
{
    (void)arg;
    char msg[160];

    while (1) {
        if (app_ws_bridge_is_connected()) {
            float pitch = 0.0f;
            float roll = 0.0f;
            float yaw = 0.0f;
            int battery = get_power_value();

            app_imu_get_attitude(&pitch, &roll, &yaw);
            if (!isfinite(pitch)) {
                pitch = 0.0f;
            }
            if (!isfinite(roll)) {
                roll = 0.0f;
            }
            if (!isfinite(yaw)) {
                yaw = 0.0f;
            }

            snprintf(msg,
                     sizeof(msg),
                     "{\"type\":\"status\",\"battery\":%d,\"pitch\":%.2f,\"roll\":%.2f,\"yaw\":%.2f}",
                     battery,
                     pitch,
                     roll,
                     yaw);
            ESP_LOGI(TAG,
                     "Status: battery=%d%% pitch=%.2f roll=%.2f yaw=%.2f",
                     battery,
                     pitch,
                     roll,
                     yaw);
            app_ws_send_text(msg);
        }

        vTaskDelay(pdMS_TO_TICKS(2000));
    }
}

static bool send_camera_frame(camera_fb_t *pic, int index, int total)
{
    if (!pic || !pic->buf || pic->len == 0) {
        return false;
    }

    size_t encoded_len = 0;
    int ret = mbedtls_base64_encode(NULL, 0, &encoded_len, pic->buf, pic->len);
    if (ret != MBEDTLS_ERR_BASE64_BUFFER_TOO_SMALL || encoded_len == 0) {
        ESP_LOGE(TAG, "Failed to get camera base64 length: %d", ret);
        return false;
    }

    char *encoded = heap_caps_malloc(encoded_len + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!encoded) {
        ESP_LOGE(TAG, "malloc camera base64 failed: %u bytes", (unsigned)(encoded_len + 1));
        return false;
    }

    size_t actual_encoded_len = 0;
    ret = mbedtls_base64_encode((unsigned char *)encoded,
                                encoded_len + 1,
                                &actual_encoded_len,
                                pic->buf,
                                pic->len);
    if (ret != 0) {
        ESP_LOGE(TAG, "Camera base64 encode failed: %d", ret);
        free(encoded);
        return false;
    }
    encoded[actual_encoded_len] = '\0';

    size_t json_len = actual_encoded_len + 256;
    char *json = heap_caps_malloc(json_len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!json) {
        ESP_LOGE(TAG, "malloc camera json failed: %u bytes", (unsigned)json_len);
        free(encoded);
        return false;
    }

    int written = snprintf(json,
                           json_len,
                           "{\"type\":\"image\",\"format\":\"rgb565\",\"width\":%d,\"height\":%d,"
                           "\"index\":%d,\"total\":%d,\"len\":%u,\"data\":\"%s\"}",
                           pic->width,
                           pic->height,
                           index,
                           total,
                           (unsigned)pic->len,
                           encoded);
    free(encoded);

    if (written <= 0 || (size_t)written >= json_len) {
        ESP_LOGE(TAG, "Camera json overflow");
        free(json);
        return false;
    }

    bool ok = send_ws_text_timeout(json, pdMS_TO_TICKS(10000));
    free(json);
    return ok;
}

static void capture_images_task(void *arg)
{
    capture_task_args_t *task_args = (capture_task_args_t *)arg;
    int count = task_args->count;
    int interval_ms = task_args->interval_ms;
    free(task_args);

    ESP_LOGI(TAG, "Capture images start: count=%d interval=%dms", count, interval_ms);

    for (int i = 1; i <= count; i++) {
        if (!app_ws_bridge_is_connected()) {
            ESP_LOGW(TAG, "Capture stopped: WebSocket disconnected");
            break;
        }

        camera_fb_t *pic = esp_camera_fb_get();
        if (!pic) {
            ESP_LOGE(TAG, "esp_camera_fb_get failed");
            break;
        }

        ESP_LOGI(TAG,
                 "Capture image %d/%d: %ux%u len=%u",
                 i,
                 count,
                 (unsigned)pic->width,
                 (unsigned)pic->height,
                 (unsigned)pic->len);
        bool ok = send_camera_frame(pic, i, count);
        esp_camera_fb_return(pic);

        if (!ok) {
            ESP_LOGW(TAG, "Capture image %d/%d upload failed", i, count);
            break;
        }

        if (i < count) {
            vTaskDelay(pdMS_TO_TICKS(interval_ms));
        }
    }

    ESP_LOGI(TAG, "Capture images done");
    s_capture_task_running = false;
    vTaskDelete(NULL);
}

static bool dispatch_capture_images_event(int count, int interval_ms)
{
    if (s_capture_task_running) {
        ESP_LOGW(TAG, "Capture task already running");
        return false;
    }

    if (count <= 0) {
        count = 1;
    } else if (count > CAPTURE_IMAGE_MAX_COUNT) {
        count = CAPTURE_IMAGE_MAX_COUNT;
    }

    if (interval_ms < 100) {
        interval_ms = 100;
    } else if (interval_ms > 5000) {
        interval_ms = 5000;
    }

    capture_task_args_t *task_args = calloc(1, sizeof(*task_args));
    if (!task_args) {
        ESP_LOGE(TAG, "calloc capture args failed");
        return false;
    }

    task_args->count = count;
    task_args->interval_ms = interval_ms;
    BaseType_t ret = xTaskCreate(capture_images_task,
                                 "capture_images",
                                 8192,
                                 task_args,
                                 4,
                                 NULL);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Create capture task failed");
        free(task_args);
        return false;
    }

    s_capture_task_running = true;
    return true;
}

static void websocket_reconnect_task(void *arg)
{
    (void)arg;
    vTaskDelay(pdMS_TO_TICKS(1000));

    if (s_ws_client && !esp_websocket_client_is_connected(s_ws_client)) {
        ESP_LOGI(TAG, "Restarting WebSocket client");
        esp_websocket_client_stop(s_ws_client);
        vTaskDelay(pdMS_TO_TICKS(300));
        esp_websocket_client_start(s_ws_client);
    }

    s_reconnect_task_handle = NULL;
    vTaskDelete(NULL);
}

static void request_websocket_reconnect(void)
{
    s_ws_connected = false;
    if (!s_reconnect_task_handle) {
        xTaskCreate(websocket_reconnect_task, "ws_reconnect", 3072, NULL, 5, &s_reconnect_task_handle);
    }
}

static bool dispatch_play_audio_event_len(const char *encoded_audio, size_t encoded_len)
{
    if (!encoded_audio) {
        return false;
    }

    size_t audio_len = 0;
    int ret = mbedtls_base64_decode(NULL,
                                    0,
                                    &audio_len,
                                    (const unsigned char *)encoded_audio,
                                    encoded_len);
    if (ret != MBEDTLS_ERR_BASE64_BUFFER_TOO_SMALL || audio_len == 0) {
        ESP_LOGE(TAG, "Failed to get audio base64 length: %d", ret);
        return false;
    }

    uint8_t *audio = heap_caps_malloc(audio_len, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!audio) {
        ESP_LOGE(TAG, "malloc audio failed: %u bytes", (unsigned)audio_len);
        return false;
    }

    ret = mbedtls_base64_decode(audio,
                                audio_len,
                                &audio_len,
                                (const unsigned char *)encoded_audio,
                                encoded_len);
    if (ret != 0) {
        ESP_LOGE(TAG, "Audio base64 decode failed: %d", ret);
        free(audio);
        return false;
    }

    esp_err_t err = audio_play(audio, audio_len);
    free(audio);
    return err == ESP_OK;
}

static bool dispatch_play_audio_event(const char *encoded_audio)
{
    if (!encoded_audio) {
        return false;
    }

    return dispatch_play_audio_event_len(encoded_audio, strlen(encoded_audio));
}

static bool dispatch_play_audio_json_fast(const char *msg)
{
    const char *type = strstr(msg, "\"type\"");
    if (!type || !strstr(type, "\"play_audio\"")) {
        return false;
    }

    const char *data_key = strstr(msg, "\"data\"");
    if (!data_key) {
        ESP_LOGW(TAG, "Audio JSON missing data");
        return true;
    }

    const char *colon = strchr(data_key, ':');
    if (!colon) {
        ESP_LOGW(TAG, "Audio JSON missing data separator");
        return true;
    }

    const char *encoded = colon + 1;
    while (*encoded == ' ' || *encoded == '\t' || *encoded == '\r' || *encoded == '\n') {
        encoded++;
    }

    if (*encoded != '"') {
        ESP_LOGW(TAG, "Audio JSON data is not string");
        return true;
    }
    encoded++;

    const char *end = strchr(encoded, '"');
    if (!end) {
        ESP_LOGW(TAG, "Audio JSON data is incomplete");
        return true;
    }

    size_t encoded_len = (size_t)(end - encoded);
    if (dispatch_play_audio_event_len(encoded, encoded_len)) {
        ESP_LOGI(TAG, "Audio queued");
    } else {
        ESP_LOGW(TAG, "Unsupported audio payload");
    }

    return true;
}

static void dispatch_json_message(const char *msg)
{
    if (dispatch_play_audio_json_fast(msg)) {
        return;
    }

    cJSON *root = cJSON_Parse(msg);
    if (!root) {
        ESP_LOGW(TAG, "Invalid JSON");
        return;
    }

    cJSON *type = cJSON_GetObjectItem(root, "type");
    if (!cJSON_IsString(type)) {
        ESP_LOGW(TAG, "JSON missing string type");
        cJSON_Delete(root);
        return;
    }

    if (strcmp(type->valuestring, "set_face") == 0) {
        cJSON *expression = cJSON_GetObjectItem(root, "expression_id");
        if (!cJSON_IsString(expression)) {
            expression = cJSON_GetObjectItem(root, "data");
        }

        if (cJSON_IsString(expression) && dispatch_face_event(expression->valuestring)) {
            ESP_LOGI(TAG, "Face set to %s", expression->valuestring);
        } else {
            ESP_LOGW(TAG, "Unsupported face expression");
        }
    } else if (strcmp(type->valuestring, "move") == 0) {
        cJSON *direction = cJSON_GetObjectItem(root, "direction");
        if (!cJSON_IsString(direction)) {
            direction = cJSON_GetObjectItem(root, "data");
        }

        cJSON *duration = cJSON_GetObjectItem(root, "duration");
        int duration_s = cJSON_IsNumber(duration) ? duration->valueint : 1;

        if (cJSON_IsString(direction) && dispatch_move_event(direction->valuestring, duration_s)) {
            ESP_LOGI(TAG, "Move set to %s for %ds", direction->valuestring, duration_s);
        } else {
            ESP_LOGW(TAG, "Unsupported move direction");
        }
    } else if (strcmp(type->valuestring, "dance") == 0) {
        cJSON *mode = cJSON_GetObjectItem(root, "data");
        if (!cJSON_IsNumber(mode)) {
            mode = cJSON_GetObjectItem(root, "mode");
        }

        if (cJSON_IsNumber(mode)) {
            tracked_chassis_set_dance_mode((uint8_t)mode->valueint);
            ESP_LOGI(TAG, "Dance mode set to %d", mode->valueint);
        } else {
            ESP_LOGW(TAG, "Unsupported dance mode");
        }
    } else if (strcmp(type->valuestring, "rgb") == 0) {
        cJSON *mode = cJSON_GetObjectItem(root, "data");
        if (!cJSON_IsNumber(mode)) {
            mode = cJSON_GetObjectItem(root, "mode");
        }

        if (cJSON_IsNumber(mode)) {
            tracked_chassis_rgb_light_control((uint8_t)mode->valueint);
            ESP_LOGI(TAG, "RGB mode set to %d", mode->valueint);
        } else {
            ESP_LOGW(TAG, "Unsupported RGB mode");
        }
    } else if (strcmp(type->valuestring, "play_audio") == 0) {
        cJSON *audio_data = cJSON_GetObjectItem(root, "data");
        if (cJSON_IsString(audio_data) && dispatch_play_audio_event(audio_data->valuestring)) {
            ESP_LOGI(TAG, "Audio queued");
        } else {
            ESP_LOGW(TAG, "Unsupported audio payload");
        }
    } else if (strcmp(type->valuestring, "capture_images") == 0) {
        cJSON *count = cJSON_GetObjectItem(root, "count");
        cJSON *interval = cJSON_GetObjectItem(root, "interval_ms");
        int capture_count = cJSON_IsNumber(count) ? count->valueint : 3;
        int interval_ms = cJSON_IsNumber(interval) ? interval->valueint : 500;

        if (dispatch_capture_images_event(capture_count, interval_ms)) {
            ESP_LOGI(TAG, "Capture command accepted: count=%d interval=%dms", capture_count, interval_ms);
        } else {
            ESP_LOGW(TAG, "Capture command rejected");
        }
    } else {
        ESP_LOGI(TAG, "Unhandled message type: %s", type->valuestring);
    }

    cJSON_Delete(root);
}

static void reset_text_payload(void)
{
    free(s_text_payload);
    s_text_payload = NULL;
    s_text_payload_len = 0;
}

static void dispatch_complete_text_message(const char *data, int len)
{
    char *msg = calloc(1, len + 1);
    if (!msg) {
        ESP_LOGE(TAG, "calloc failed");
        return;
    }

    memcpy(msg, data, len);
    ESP_LOGI(TAG, "RX text message len=%d", len);
    dispatch_json_message(msg);

    free(msg);
}

static void handle_text_message(const char *data, int len, int payload_len, int payload_offset)
{
    if (!data || len <= 0) {
        return;
    }

    if (payload_len <= 0) {
        dispatch_complete_text_message(data, len);
        return;
    }

    if (payload_len > WS_TEXT_MAX_LEN) {
        ESP_LOGE(TAG, "Text payload too large: %d", payload_len);
        reset_text_payload();
        return;
    }

    if (payload_offset < 0 || payload_offset + len > payload_len) {
        ESP_LOGW(TAG, "Invalid text fragment offset=%d len=%d total=%d", payload_offset, len, payload_len);
        reset_text_payload();
        return;
    }

    if (payload_len == len && payload_offset == 0) {
        dispatch_complete_text_message(data, len);
        return;
    }

    if (payload_offset == 0 || !s_text_payload || s_text_payload_len != payload_len) {
        reset_text_payload();
        s_text_payload = heap_caps_calloc(1, payload_len + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (!s_text_payload) {
            ESP_LOGE(TAG, "malloc text payload failed: %d bytes", payload_len + 1);
            return;
        }
        s_text_payload_len = payload_len;
    }

    memcpy(s_text_payload + payload_offset, data, len);

    if (payload_offset + len >= s_text_payload_len) {
        s_text_payload[s_text_payload_len] = '\0';
        ESP_LOGI(TAG, "RX text message len=%d", s_text_payload_len);
        dispatch_json_message(s_text_payload);
        reset_text_payload();
    } else {
        ESP_LOGI(TAG, "RX text chunk %d/%d", payload_offset + len, s_text_payload_len);
    }
}

static void websocket_event_handler(void *handler_args,
                                    esp_event_base_t base,
                                    int32_t event_id,
                                    void *event_data)
{
    esp_websocket_event_data_t *data = (esp_websocket_event_data_t *)event_data;

    switch (event_id) {
    case WEBSOCKET_EVENT_CONNECTED:
        s_ws_connected = true;
        ESP_LOGI(TAG, "WebSocket connected");
        app_ws_send_text("{\"type\":\"hello\",\"device\":\"sparkbot\"}");
        break;

    case WEBSOCKET_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "WebSocket disconnected");
        request_websocket_reconnect();
        break;

    case WEBSOCKET_EVENT_DATA:
        ESP_LOGI(TAG,
                 "RX frame opcode=%d len=%d offset=%d total=%d",
                 data->op_code,
                 data->data_len,
                 data->payload_offset,
                 data->payload_len);
        if (data->op_code == 0x1 && data->data_len > 0) {
            handle_text_message(data->data_ptr,
                                data->data_len,
                                data->payload_len,
                                data->payload_offset);
        } else if (data->op_code == 0x8) {
            ESP_LOGW(TAG, "WebSocket close frame received");
            reset_text_payload();
            request_websocket_reconnect();
        }
        break;

    case WEBSOCKET_EVENT_ERROR:
        ESP_LOGE(TAG, "WebSocket error");
        request_websocket_reconnect();
        break;

    default:
        break;
    }
}

void app_ws_bridge_start(void)
{
    if (s_ws_client) {
        return;
    }

    const char *token = CONFIG_SPARKBOT_DEVICE_TOKEN;
    if (strlen(token) < 32 || strlen(token) > 400 || strpbrk(token, "\r\n \t")) {
        ESP_LOGE(TAG, "Configure a private device token (32-400 characters) before starting");
        return;
    }
    for (const unsigned char *p = (const unsigned char *)token; *p; ++p) {
        if (*p < 33 || *p > 126) {
            ESP_LOGE(TAG, "Device token must use printable ASCII characters without spaces");
            return;
        }
    }
    snprintf(s_auth_headers, sizeof(s_auth_headers), "Authorization: Bearer %s\r\n", token);
    esp_websocket_client_config_t config = {
        .uri = SPARKBOT_WS_URI,
        .headers = s_auth_headers,
    };

    ESP_LOGI(TAG, "Starting WebSocket: %s", SPARKBOT_WS_URI);
    s_ws_client = esp_websocket_client_init(&config);
    if (!s_ws_client) {
        ESP_LOGE(TAG, "esp_websocket_client_init failed");
        return;
    }

    esp_websocket_register_events(s_ws_client,
                                  WEBSOCKET_EVENT_ANY,
                                  websocket_event_handler,
                                  NULL);
    esp_websocket_client_start(s_ws_client);

    if (!s_status_task_started) {
        BaseType_t ret = xTaskCreate(status_report_task, "ws_status", 3072, NULL, 4, NULL);
        s_status_task_started = (ret == pdPASS);
        if (!s_status_task_started) {
            ESP_LOGE(TAG, "Create status report task failed");
        }
    }
}

bool app_ws_bridge_is_connected(void)
{
    if (!s_ws_client) {
        s_ws_connected = false;
        return false;
    }

    s_ws_connected = esp_websocket_client_is_connected(s_ws_client);
    return s_ws_connected;
}

static bool send_ws_text_timeout(const char *text, TickType_t timeout_ticks)
{
    if (!text || !app_ws_bridge_is_connected()) {
        return false;
    }

    int ret = esp_websocket_client_send_text(s_ws_client,
                                             text,
                                             strlen(text),
                                             timeout_ticks);
    if (ret <= 0) {
        s_ws_connected = false;
    }

    return ret > 0;
}

bool app_ws_send_text(const char *text)
{
    return send_ws_text_timeout(text, pdMS_TO_TICKS(1000));
}

bool app_ws_send_binary(const uint8_t *data, size_t len)
{
    if (!data || len == 0 || !app_ws_bridge_is_connected()) {
        return false;
    }

    int ret = esp_websocket_client_send_bin(s_ws_client,
                                            (const char *)data,
                                            len,
                                            pdMS_TO_TICKS(10000));
    if (ret <= 0) {
        s_ws_connected = false;
    }

    return ret > 0;
}

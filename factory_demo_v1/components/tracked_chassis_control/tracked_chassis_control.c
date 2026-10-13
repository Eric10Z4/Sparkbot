#include "tracked_chassis_control.h"

#include <stdio.h>
#include <string.h>

#include "driver/uart.h"
#include "esp_check.h"
#include "esp_log.h"
#include "sdkconfig.h"

static const char *TAG = "tracked_chassis_control";

#define ECHO_UART_PORT_NUM      (1)
#define ECHO_UART_BAUD_RATE     (115200)
#define BUF_SIZE                (1024)

static bool s_uart_started;

static void echo_uart_init(void)
{
    if (s_uart_started) {
        return;
    }

    uart_config_t uart_config = {
        .baud_rate = ECHO_UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    int intr_alloc_flags = 0;

#if CONFIG_UART_ISR_IN_IRAM
    intr_alloc_flags = ESP_INTR_FLAG_IRAM;
#endif

    ESP_ERROR_CHECK(uart_driver_install(ECHO_UART_PORT_NUM, BUF_SIZE * 2, 0, 0, NULL, intr_alloc_flags));
    ESP_ERROR_CHECK(uart_param_config(ECHO_UART_PORT_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(ECHO_UART_PORT_NUM, UART_ECHO_TXD, UART_ECHO_RXD, UART_ECHO_RTS, UART_ECHO_CTS));
    s_uart_started = true;
}

void tracked_chassis_control_start(void)
{
    echo_uart_init();
    ESP_LOGI(TAG, "Tracked chassis UART ready: TX=%d RX=%d baud=%d",
             UART_ECHO_TXD, UART_ECHO_RXD, ECHO_UART_BAUD_RATE);
}

void tracked_chassis_motion_control(const char *command_str)
{
    if (!command_str) {
        return;
    }

    echo_uart_init();
    uart_write_bytes(ECHO_UART_PORT_NUM, command_str, strlen(command_str));
    ESP_LOGI(TAG, "Sent command: %s", command_str);
}

void tracked_chassis_rgb_light_control(uint8_t rgb_mode)
{
    char data[10] = {0};
    snprintf(data, sizeof(data), "w%d", rgb_mode);
    tracked_chassis_motion_control(data);
}

void tracked_chassis_set_dance_mode(uint8_t dance_mode)
{
    char data[10] = {0};
    snprintf(data, sizeof(data), "d%d", dance_mode);
    tracked_chassis_motion_control(data);
}

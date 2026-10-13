#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

void app_ws_bridge_start(void);
bool app_ws_bridge_is_connected(void);
bool app_ws_send_text(const char *text);
bool app_ws_send_binary(const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif

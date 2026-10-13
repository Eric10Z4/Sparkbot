# 安全配置与报告

发现安全问题时请使用仓库 Security → Report a vulnerability（如可用），不要在公开 issue 中粘贴凭据。

- HTTP 默认仅监听 `127.0.0.1`，所有请求要求 `Authorization: Bearer <SPARKBOT_API_TOKEN>`。
- WebSocket 默认仅监听 `127.0.0.1`，设备连接必须发送独立的 `SPARKBOT_DEVICE_TOKEN`。
- 两种 token 必须不同，长度 32–400 字符；建议用 `python -c "import secrets; print(secrets.token_urlsafe(32))"` 分别生成。
- 设备接入时将 `SPARKBOT_WEBSOCKET_HOST` 设为服务器的指定局域网地址，并在防火墙只放行设备。明文 ws/http 仅用于可信隔离局域网；跨网访问使用带证书校验的 TLS 代理或安全隧道。
- 不提交 `.env`、`sdkconfig`、`sdkconfig.old`。曾公开的实际 Wi-Fi 密码需要在路由器上更换；本次移除当前文件不会抹除 Git 历史。

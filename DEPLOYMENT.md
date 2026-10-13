# 部署说明

## 1. Python 服务端

以下 PowerShell 命令从仓库根目录执行。Python 3.10+，可选 GPU 功能还需兼容的驱动、模型和依赖。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r SparkAgentServer/requirements.txt
```

设置本次会话环境变量。两个 token 分别生成，保存到自己的私有配置中，不粘贴到源码、公开 issue 或日志。

```powershell
$env:SPARKBOT_API_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SPARKBOT_DEVICE_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SPARKBOT_SERVER_HOST = "127.0.0.1"
$env:SPARKBOT_WEBSOCKET_HOST = "127.0.0.1"
# 按使用的服务，在本地设置 DASHSCOPE_API_KEY、SILICONFLOW_API_KEY。
# 启用微信通知时，再设置 WECHAT_TARGET_ID。
cd SparkAgentServer
python main.py
```

`SparkAgentServer/.env.example` 只列出变量，不会被程序自动加载。新终端和 OpenClaw 进程需要单独加载同一组私有变量；每次重新生成 token 后，客户端和设备配置也要更新。

默认 HTTP 地址为 `http://127.0.0.1:5000`，WebSocket 地址为 `ws://127.0.0.1:8765`。

## 2. 验证 HTTP 认证

在已设置同一 API token 的另一终端中运行：

```powershell
$headers = @{ Authorization = "Bearer $env:SPARKBOT_API_TOKEN" }
Invoke-RestMethod -Uri http://127.0.0.1:5000/api/status -Headers $headers
```

缺少 token 或 token 错误时应返回 401；合法请求返回机器人状态。状态查询不会发出运动指令。`/docs` 和 `/openapi.json` 同样受保护，浏览器直接访问会得到 401。

## 3. OpenClaw

将 `openclaw/openclaw.json` 作为示例复制到自己的 OpenClaw 配置目录，按本机环境替换路径和占位符；工作区与技能目录也使用本地副本。配置实际使用的模型、网关、搜索服务与通道。

启动 OpenClaw 的环境需要包含 `SPARKBOT_API_TOKEN`。调用脚本依赖 `requests`，随服务端依赖一起安装，不再在运行时自动安装软件。若 Python 环境独立，请先安装 `requests`。

```powershell
python openclaw/skills/robot_api.py status
```

需要连接非默认 API 地址时设置 `SPARKBOT_API_URL`，例如自己的受信任 HTTPS 服务地址并包含 `/api`。不要将 token 放入 URL。

## 4. ESP32-S3 固件

使用 ESP-IDF 5.2.3 环境。在 `factory_demo_v1` 下准备有使用权的 `audio/echo.wav` 和 `audio/muyu.wav`；仓库不分发这些音频，缺失时构建会失败。

```text
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
idf.py flash monitor
```

在 `Example Configuration` 中填写 Wi-Fi、`SPARKBOT_WS_URI` 和 `SPARKBOT_DEVICE_TOKEN`。设备 token 必须与服务端完全一致，并与 API token 不同。

实体设备不能访问 PC 的 `127.0.0.1`。将服务端 `SPARKBOT_WEBSOCKET_HOST` 改为 PC 实际局域网地址，将固件 URL 设置为 `ws://<服务器局域网地址>:8765`，防火墙只允许需要的设备访问。明文连接仅用于可信隔离网络，跨网访问需配置带证书校验的 TLS 代理或安全隧道。

生成的 `sdkconfig`、`sdkconfig.old` 已被忽略，原提交中的设备配置不再分发。不要修改 Kconfig 默认值来保存凭据。旧设备配置可由 `sdkconfig.defaults` 和 menuconfig 重新生成。

## 5. 本地模型与视觉测试

启用 `USE_LOCAL_GPU` 前，按相应服务要求安装 FunASR、ModelScope、GPT-SoVITS 等；准备自己的模型和获授权参考音频。视觉部分按 [view 说明](view/README.md) 准备依赖与本地测试图片。

自动检查不启动真实机器人或发送微信消息。完成部署后，应在可安全停止设备的环境中逐项验证语音、画面和动作。

## 6. 隐私与授权

密钥、Wi-Fi 配置、真实照片、识别记录、个人位置和机器用户目录不进入公开提交。曾公开的真实密码需要更换；从当前版本删除文件不会消除旧提交中的副本。参见 [安全说明](SECURITY.md) 和 [授权说明](AUTHORIZATION.md)。

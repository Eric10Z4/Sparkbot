# Sparkbot 桌面机器人

基于 ESP32-S3、Python 和 OpenClaw 的桌面机器人实验项目。ESP32 负责采集与硬件执行，PC 服务端处理语音、视觉和控制请求。

这是开发中的原型。硬件、模型和外部服务需要分别配置，仓库中的历史报告不代表当前设备已经完成验收。

## 主要模块

| 目录 | 用途 |
| --- | --- |
| `SparkAgentServer/` | FastAPI HTTP 接口、设备 WebSocket、语音及视觉服务 |
| `factory_demo_v1/` | ESP32-S3 固件与随附组件 |
| `openclaw/` | Agent 配置示例、提示词和 HTTP 调用脚本 |
| `view/` | 独立视觉模块和手动集成测试 |
| `docs/hardware_apis/` | 硬件接口参考 |

```text
OpenClaw → 带 API token 的 HTTP 请求 → Python 服务端
                                        ↕ 带设备 token 的 WebSocket
                                     ESP32-S3
```

## 快速开始

完整步骤见 [部署说明](DEPLOYMENT.md)，凭据与网络配置见 [安全说明](SECURITY.md)。

1. 使用 Python 3.10 或更高版本建立独立环境，安装 `SparkAgentServer/requirements.txt`。
2. 在本地设置不同的 `SPARKBOT_API_TOKEN` 和 `SPARKBOT_DEVICE_TOKEN`，分别使用随机生成的 32–400 位可打印 ASCII 字符（不含空格）。配置需要的语音服务密钥。
3. 在 `SparkAgentServer` 目录运行 `python main.py`。默认 HTTP 和 WebSocket 都只监听本机。
4. 给 OpenClaw 进程设置同一份 API token；设备使用独立的设备 token。实体设备接入还需按部署说明配置服务器局域网监听地址、Wi-Fi 和固件。

```powershell
# 在仓库根目录，完成部署说明中的环境与凭据设置后执行
python openclaw/skills/robot_api.py status
```

所有 HTTP 请求（包括 `/docs`、`/openapi.json`）都需要 Bearer 认证；直接在浏览器打开文档会返回 401。未认证的 WebSocket 连接会被关闭。

## 服务选择

`SparkAgentServer/config.py` 中的 `USE_LOCAL_GPU` 控制语音处理模式。

| 功能 | 默认配置 | 可选本地配置 |
| --- | --- | --- |
| 语音识别 | DashScope，需 `DASHSCOPE_API_KEY` | FunASR / ModelScope，需额外模型和依赖 |
| 语音合成 | Edge-TTS，需联网 | GPT-SoVITS 本地 API 及有使用权的参考音频 |
| 模型调用 | SiliconFlow 或 OpenClaw 中配置的服务 | 按实际部署配置 |
| 视觉识别 | OpenCV；部分功能需模型 | InsightFace、YOLO 及对应依赖和权重 |

仅安装默认依赖不代表所有本地模型均已就绪。人脸照片、识别数据库、参考音频、私有配置及模型权重不应提交。

## 检查与限制

自动检查覆盖 HTTP / WebSocket 认证和 Python 语法。视觉、语音、真实硬件需要在对应环境中手动验证。固件构建还需要自行准备有授权的 `audio/echo.wav` 与 `audio/muyu.wav`，详见 [固件说明](factory_demo_v1/README.md)。

本次整理保留原有运动控制逻辑；认证只限制连接和接口访问，不能替代硬件急停或真实设备验证。

## 授权与来源

项目原创部分暂不新增统一开源许可证，详见 [授权说明](AUTHORIZATION.md)。随附第三方许可证和版权声明保持原样。历史设计材料保存在 [项目报告](PROJECT_REPORT_A.md)，其中性能描述需要结合具体测试环境理解。

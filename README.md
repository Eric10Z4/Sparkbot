# SparkBot：多模态具身智能桌面伴侣

融合语音交互、视觉感知和设备状态的桌面机器人项目。以 **ESP32-S3 履带式机器人**为交互载体，通过 **Python 中枢服务 + OpenClaw Agent + 本地语音模型**，把感知输入、语言决策、语音回复、屏幕表情和底盘动作串接起来。

**技术栈：** Python · FastAPI · WebSocket · ESP-IDF · OpenClaw · FunASR / SenseVoice · GPT-SoVITS · OpenCV · LVGL

## 项目背景与核心工作

面向桌面陪伴、语音交互和远程看护场景，项目关注三个问题：如何连接实体设备与 Agent，如何组织本地多模态处理，以及如何把模型输出转化为设备动作。

### 1. 软硬件协同与中枢架构

采用“端侧采集与执行、PC 侧感知与决策”的分工。`SparkAgentServer` 通过 WebSocket 接收设备音频、图像与状态信息，通过 HTTP 向 Agent 暴露语音、表情、运动和视觉接口；回复音频与动作指令再由中枢下发到设备。

链路包含 PCM 音频处理、RGB565 图像转换、设备状态更新和执行事件分发。核心入口见 [main.py](SparkAgentServer/main.py)，设备侧通信见 [app_ws_bridge.c](factory_demo_v1/main/app/app_ws_bridge.c)。

### 2. 本地语音处理与个性化合成

本地模式并发调用 **Paraformer-Large** 和 **SenseVoiceSmall**，分别处理语音转写与情感标签；语音输出接入 **GPT-SoVITS**，使用参考音频提供个性化音色，并转换为设备可播放的音频格式。云端模式作为另一种部署选择。

相关实现见 [语音识别服务](SparkAgentServer/services/stt_service.py) 和 [语音合成服务](SparkAgentServer/services/tts_service.py)。本地模型用于减少语音处理环节对云端网络的依赖；实际模型选择与运行环境见下方部署说明。

### 3. Agent 决策与具身交互

通过 OpenClaw 的工具调用，将对话意图映射到语音、表情和移动接口，并结合视觉识别、异常事件及设备状态组织交互。表情事件由固件接入 LVGL，运动事件下发到底盘；告警可经配置好的消息通道发送到用户端。

调用封装见 [robot_api.py](openclaw/skills/robot_api.py)，视觉接口见 [visual.py](SparkAgentServer/services/visual.py)。HTTP 与设备 WebSocket 分别使用独立 token，私有配置留在本地。

## 主要贡献与团队分工

本仓库重点展示架构负责人在 **整体技术方案、SparkAgentServer 核心中枢、语音链路和 Agent / 硬件接口集成**方面的工作。嵌入式固件与视觉模块由团队协作完成，随附组件保留各自来源和许可证。详细分工见 [项目架构与个人贡献报告](PROJECT_REPORT_A.md)。

## 阶段成果

作者报告的 **2026.03–2026.06 阶段结果**：完成真机语音、表情和底盘动作联调，本地部署下端到端双向语音交互延迟在 **850 ms 以内**。

该数值来自作者的阶段成果描述；原始计时日志、采样规模、完整硬件 / 模型配置与计时起止口径尚未随仓库发布。它用于说明当时的部署结果，复现时需补齐同条件测量，不作为当前自动检查的结论。

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

当前语音识别入口处理接收到的音频片段；双向通信不等同于已经完成连续流式识别或全双工打断验收。真实语音延迟、设备动作和异常恢复应在目标硬件上单独验证。

## 授权与来源

代码已公开用于项目展示与交流，项目原创部分尚未提供统一开源许可证，详见 [授权说明](AUTHORIZATION.md)。随附第三方许可证和版权声明保持原样。历史设计材料保存在 [项目报告](PROJECT_REPORT_A.md)，其中性能描述需要结合具体测试环境理解。

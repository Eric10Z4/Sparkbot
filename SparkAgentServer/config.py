# ==========================================
# 🔑 全局配置中心 (Config Center)
# ==========================================
# 所有 API Key、服务地址、模型选择都集中在这里。
# 凭据通过环境变量提供，不写入源码。
# ==========================================

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ------------------------------------------
# 📡 阿里 DashScope（语音识别 STT）
# ------------------------------------------
# 控制台：https://dashscope.console.aliyun.com/
DASHSCOPE_API_KEY = os.environ.get(
    "DASHSCOPE_API_KEY",
    ""  # 在本地环境设置 DASHSCOPE_API_KEY
)

# STT 模型选择（按需切换，取消注释即可）
STT_MODEL = "sensevoice-v1"              # 语音识别 + 情感检测（当前使用）
# STT_MODEL = "fun-asr-realtime"         # 最新实时版，精度最高（无情感）
# STT_MODEL = "qwen3-asr-flash-realtime" # Qwen3 大模型实时版（无情感）
# STT_MODEL = "paraformer-realtime-v2"   # 经典实时版，稳定可靠（无情感）

# ------------------------------------------
# 🧠 硅基流动 SiliconFlow（大模型 LLM）
# ------------------------------------------
# 控制台：https://cloud.siliconflow.cn/
SILICONFLOW_API_KEY = os.environ.get(
    "SILICONFLOW_API_KEY",
    ""  # 在本地环境设置 SILICONFLOW_API_KEY
)
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
LLM_MODEL = "Qwen/Qwen2.5-72B-Instruct"  # 角色扮演能力最强的开源模型

# ------------------------------------------
# 📱 微信目标用户配置
# ------------------------------------------
# 接受通知的微信用户的 ID（如果你启用了微信通道）
WECHAT_TARGET_ID = os.environ.get("WECHAT_TARGET_ID", "")

# ------------------------------------------
# 🗣️ TTS 语音合成（文字转语音）
# ------------------------------------------
# 轻薄本方案：Edge-TTS（微软免费，无需 API Key）
# 游戏本方案：GPT-SoVITS 本地推理

# Edge-TTS 声音选择（轻薄本使用）
# 完整列表运行：edge-tts --list-voices
EDGE_TTS_VOICE = "zh-CN-XiaoyiNeural"    # 年轻女声，适合傲娇人设
# EDGE_TTS_VOICE = "zh-CN-YunxiNeural"   # 年轻男声

# GPT-SoVITS 本地服务地址（游戏本部署时填写）
GPTSOVITS_API_URL = "http://127.0.0.1:9880/tts"
# GPT-SoVITS 配置
GPTSOVITS_REF_AUDIO = str(BASE_DIR / "ref_audio_clean.mp3")
GPTSOVITS_PROMPT_TEXT = "所有系统检查完毕，我又回到战斗了，现在让他们瞧瞧我的厉害。"

# ------------------------------------------
# 🤖 SparkAgentServer 本体配置
# ------------------------------------------
# FastAPI 端口（给 QClaw 技能调用的 HTTP 接口）
SERVER_HOST = os.environ.get("SPARKBOT_SERVER_HOST", "127.0.0.1")
SERVER_PORT = 5000

# WebSocket 端口（给 ESP32 机器人连接的通道）
WEBSOCKET_HOST = os.environ.get("SPARKBOT_WEBSOCKET_HOST", "127.0.0.1")
WEBSOCKET_PORT = 8765

# ------------------------------------------
# 🎮 部署模式切换（一键切换轻薄本/游戏本）
# ------------------------------------------
# 改成 True 就会自动启用所有本地 GPU 方案
# （本地 SenseVoice STT + 本地 GPT-SoVITS TTS）
USE_LOCAL_GPU = False

# Private environment only; never commit credentials.
API_TOKEN = os.environ.get("SPARKBOT_API_TOKEN", "")
DEVICE_TOKEN = os.environ.get("SPARKBOT_DEVICE_TOKEN", "")

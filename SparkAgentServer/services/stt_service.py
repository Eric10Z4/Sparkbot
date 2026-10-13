# ==========================================
# 听觉解析模块 (STT / Speech-to-Text)
# 负责把硬件传来的二进制音频流转换成文字 + 情感标签
# ==========================================
#
# 📌 架构说明：
# 本模块对外暴露一个函数 audio_to_text(audio_bytes) -> dict
# 返回值包含两个字段：
#   - "text": 识别出的纯文本
#   - "emotion": 检测到的说话人情绪（如 "happy", "angry", "sad", "neutral"）
#
# 上层可以利用 emotion 字段，在发给 QClaw 大脑时注入额外上下文，例如：
#   "[麦克风][用户情绪：愤怒] 你在搞什么啊！"
# 这样 QClaw 不仅知道你说了啥，还知道你的语气，回复会更有灵魂。
#
# 📌 当前方案（轻薄本开发期）：
# 使用阿里 DashScope 云端 SenseVoice-v1 模型（自带情感识别）
#
# 📌 游戏本部署方案（已注释，周末切换）：
# 使用 FunASR + SenseVoice 本地推理（4080 显卡，延迟约 50ms）
# ==========================================

import os
import re
import io
import tempfile
import logging
import wave

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("STT")

# ==========================================
# 🔑 从全局配置中心导入（所有 Key 统一在 config.py 管理）
# ==========================================
from config import DASHSCOPE_API_KEY, STT_MODEL, USE_LOCAL_GPU

# SenseVoice 会在识别结果中插入各种标签，格式如：
# "<|HAPPY|>你好啊<|HAPPY|>" 或 "<|ANGRY|>你烦不烦<|ANGRY|>"
# 也会出现 "<|Speech|>", "<|/Speech|>", "<|zh|>" 等语种/事件标签
# 下面这个正则用来提取所有 <|xxx|> 标签
_EMOTION_PATTERN = re.compile(r"<\|/?(\w+)\|>")

# 情感标签到中文的映射表（用于注入 QClaw 大脑的上下文）
EMOTION_MAP = {
    "HAPPY":       "开心",
    "SAD":         "难过",
    "ANGRY":       "愤怒",
    "NEUTRAL":     "平静",
    "FEARFUL":     "害怕",
    "DISGUSTED":   "嫌恶",
    "SURPRISED":   "惊讶",
    "EMO_UNKNOWN": "平静",   # 未识别时默认平静
}


def audio_to_text(audio_bytes: bytes) -> dict:
    """
    将原始音频二进制流转换为文字和情感标签。

    这是整个系统的"耳朵"——ESP32 机器人录下的声音经过 WebSocket 传到这里，
    由本函数负责"听懂"并返回纯文本和情感，随后送给 QClaw 大脑。

    参数:
        audio_bytes (bytes): 从 ESP32 麦克风采集到的原始音频数据。
                             通常是 16kHz、16bit、单声道的 PCM 或 WAV 格式。

    返回:
        dict: {
            "text": "你好蠢啊",         # 识别出的纯文本（已去除情感标签）
            "emotion": "愤怒",           # 说话人的情绪（中文）
            "emotion_raw": "ANGRY",     # 原始情感标签（英文，用于程序判断）
        }
        如果识别失败则返回 {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}

    使用示例:
        >>> with open("test.wav", "rb") as f:
        ...     result = audio_to_text(f.read())
        >>> print(result["text"])        # "你好蠢啊"
        >>> print(result["emotion"])     # "愤怒"
    """
    # 默认返回值（识别失败时使用）
    default_result = {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}

    if not audio_bytes or len(audio_bytes) < 100:
        logger.warning("[STT] 收到的音频数据过短，跳过识别")
        return default_result

    if not audio_bytes.startswith(b"RIFF"):
        logger.info("[STT] 收到 PCM 原始音频，自动封装为 16kHz/16bit/mono WAV")
        audio_bytes = _pcm16_mono_to_wav(audio_bytes)

    logger.info(f"[STT] 收到音频流，大小: {len(audio_bytes)} 字节")

    try:
        # 根据配置自动选择本地 GPU 或云端方案
        if USE_LOCAL_GPU:
            result = _recognize_via_dual_local(audio_bytes)
        else:
            result = _recognize_via_sensevoice(audio_bytes)
        logger.info(f"[STT] 识别结果: text='{result['text']}', emotion={result['emotion']}")
        return result
    except Exception as e:
        logger.error(f"[STT] 识别失败: {e}")
        return default_result


def _pcm16_mono_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw 16-bit mono PCM bytes in a WAV container for STT services."""
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return wav_buffer.getvalue()


def _parse_sensevoice_output(raw_text: str) -> dict:
    """
    解析 SenseVoice 模型返回的带标签文本。

    SenseVoice 的输出格式示例：
      "<|HAPPY|>今天天气真好啊<|HAPPY|>"
      "<|ANGRY|>你到底在搞什么<|ANGRY|>"
      "<|EMO_UNKNOWN|>帮我查一下明天天气<|EMO_UNKNOWN|>"

    本函数会：
    1. 提取情感标签（取第一个出现的标签作为主情感）
    2. 去除所有标签，返回干净的纯文本
    """
    # 提取所有情感标签
    emotions_found = _EMOTION_PATTERN.findall(raw_text)

    # 取第一个有效的情感标签
    emotion_raw = "NEUTRAL"
    for e in emotions_found:
        if e in EMOTION_MAP:
            emotion_raw = e
            break

    # 去除所有 <|xxx|> 标签，只保留纯文本
    clean_text = _EMOTION_PATTERN.sub("", raw_text).strip()

    return {
        "text": clean_text,
        "emotion": EMOTION_MAP.get(emotion_raw, "平静"),
        "emotion_raw": emotion_raw,
    }


# ==========================================
# ☁️ 方案 A：阿里 DashScope + SenseVoice（轻薄本使用）
# ==========================================
# 依赖安装：pip install dashscope
# SenseVoice 优势：在语音识别的同时，自动输出说话人的情感标签
# 这样 QClaw 大脑不仅知道你说了什么，还知道你的语气

def _recognize_via_sensevoice(audio_bytes: bytes) -> dict:
    """
    通过阿里 DashScope REST API 进行语音识别 + 情感检测。

    使用 requests 直接调用 HTTP 接口，避免 SDK 版本兼容性问题。
    流程：上传音频 → 提交转写任务 → 轮询结果 → 解析文本和情感
    """
    import requests
    import time
    import json
    import base64

    headers = {
        "Authorization": f"bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",     # 必须开启异步模式
    }

    # 将音频转为 base64 编码，通过 data URL 的方式传递
    # 这样就不需要先上传文件到 OSS 了
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    data_url = f"data:audio/wav;base64,{audio_b64}"

    # 提交转写任务
    logger.info("[STT] 正在提交转写任务到 DashScope...")
    submit_body = {
        "model": STT_MODEL,
        "input": {
            "file_urls": [data_url],
        },
        "parameters": {
            "language_hints": ["zh"],
        },
    }

    resp = requests.post(
        "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription",
        headers=headers,
        json=submit_body,
    )

    if resp.status_code != 200:
        logger.error(f"[STT] 提交任务失败: {resp.status_code} {resp.text}")
        return {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}

    task_data = resp.json()
    task_id = task_data.get("output", {}).get("task_id", "")
    if not task_id:
        logger.error(f"[STT] 未获取到 task_id: {task_data}")
        return {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}

    logger.info(f"[STT] 任务已提交, task_id: {task_id}")

    # 轮询等待结果（短音频通常 2~5 秒）
    check_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    max_wait = 30
    for i in range(max_wait):
        time.sleep(1)
        check_resp = requests.get(check_url, headers=headers)
        check_data = check_resp.json()
        status = check_data.get("output", {}).get("task_status", "")

        if status == "SUCCEEDED":
            logger.info("[STT] 转写完成！正在解析结果...")
            results = check_data.get("output", {}).get("results", [])
            raw_text = ""
            for r in results:
                # 结果可能包含 transcription_url 需要二次请求
                trans_url = r.get("transcription_url", "")
                if trans_url:
                    trans_resp = requests.get(trans_url)
                    trans_data = trans_resp.json()
                    for t in trans_data.get("transcripts", []):
                        raw_text += t.get("text", "")
                        # 也检查 sentences 层级
                        for s in t.get("sentences", []):
                            if not raw_text:
                                raw_text += s.get("text", "")
                else:
                    raw_text += r.get("text", "")

            if raw_text:
                return _parse_sensevoice_output(raw_text)
            return {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}

        elif status == "FAILED":
            msg = check_data.get("output", {}).get("message", "未知错误")
            logger.error(f"[STT] 转写失败: {msg}")
            return {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}

        # PENDING / RUNNING，继续等
        logger.info(f"[STT] 等待转写中... ({i+1}s)")

    logger.error("[STT] 转写任务超时（30秒）")
    return {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}


# ==========================================
# 🎮 方案 B：本地双模型（游戏本部署，USE_LOCAL_GPU=True 时启用）
# ==========================================
# 双模型架构：
#   📝 Paraformer-Large（paraformer-zh）：高精度中文语音识别
#      - 附带 VAD（语音活动检测）和标点恢复
#      - 精度 ★★★★★，中文 ASR 最强开源模型
#   😊 SenseVoiceSmall：专门做情感检测
#      - 支持 Happy/Sad/Angry/Neutral 等情感标签
#      - 轻量级，显存占用仅 ~900MB
#
# 工作流程：
#   音频 → [Paraformer-Large] → 精准文字
#        → [SenseVoiceSmall]  → 情感标签
#   合并 → {"text": 精准文字, "emotion": 情感}
#
# 总显存占用约 2.1GB（4080 的 12GB 显存绰绰有余）
# ==========================================

from funasr import AutoModel
import concurrent.futures

# 双模型实例（懒加载，首次调用时才初始化）
_paraformer_model = None    # 精准文字识别
_sensevoice_model = None    # 情感检测

def _get_paraformer_model():
    """
    懒加载 Paraformer-Large 模型到 GPU 显存。
    包含 VAD（语音端点检测）+ 标点恢复，识别精度最高。
    """
    global _paraformer_model
    if _paraformer_model is None:
        logger.info("[STT] 🔄 正在加载 Paraformer-Large 到 GPU（精准文字识别）...")
        _paraformer_model = AutoModel(
            model="paraformer-zh",
            vad_model="fsmn-vad",
            punc_model="ct-punc",
            device="cuda:0",
        )
        logger.info("[STT] ✅ Paraformer-Large 加载完毕，常驻 GPU 显存")
    return _paraformer_model


def _get_sensevoice_model():
    """
    懒加载 SenseVoiceSmall 模型到 GPU 显存。
    专门用于情感检测，输出带情感标签的文本。
    """
    global _sensevoice_model
    if _sensevoice_model is None:
        logger.info("[STT] 🔄 正在加载 SenseVoiceSmall 到 GPU（情感检测）...")
        _sensevoice_model = AutoModel(
            model="iic/SenseVoiceSmall",
            trust_remote_code=True,
            device="cuda:0",
        )
        logger.info("[STT] ✅ SenseVoiceSmall 加载完毕，常驻 GPU 显存")
    return _sensevoice_model


def _recognize_via_dual_local(audio_bytes: bytes) -> dict:
    """
    双模型本地识别：
      - Paraformer-Large：负责精准的文字识别（带 VAD + 标点）
      - SenseVoiceSmall：负责情感检测
    两个模型并行推理，合并结果返回。

    返回格式与云端版完全一致：{"text": ..., "emotion": ..., "emotion_raw": ...}
    """
    tmp_path = None
    try:
        # 写临时 WAV 文件（FunASR 需要文件路径输入）
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # 确保两个模型都已加载
        paraformer = _get_paraformer_model()
        sensevoice = _get_sensevoice_model()

        # 并行推理：两个模型同时跑，节省时间
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future_text = executor.submit(
                paraformer.generate,
                input=tmp_path,
                batch_size_s=300,
            )
            future_emotion = executor.submit(
                sensevoice.generate,
                input=tmp_path,
                language="zh",
                use_itn=True,
            )

            # 获取 Paraformer-Large 的精准文字结果
            text_result = future_text.result()
            text = ""
            if text_result and len(text_result) > 0:
                text = text_result[0].get("text", "")

            # 获取 SenseVoiceSmall 的情感结果
            emotion_result = future_emotion.result()
            emotion_raw = "NEUTRAL"
            if emotion_result and len(emotion_result) > 0:
                raw_emo_text = emotion_result[0].get("text", "")
                # 从 SenseVoice 输出中提取情感标签
                emotions_found = _EMOTION_PATTERN.findall(raw_emo_text)
                for e in emotions_found:
                    if e in EMOTION_MAP:
                        emotion_raw = e
                        break

        logger.info(f"[STT] 🎯 双模型结果 — Paraformer: '{text}' | 情感: {emotion_raw}")

        return {
            "text": text,
            "emotion": EMOTION_MAP.get(emotion_raw, "平静"),
            "emotion_raw": emotion_raw,
        }

    except Exception as e:
        logger.error(f"[STT] 本地双模型识别失败: {e}")
        # 降级：尝试只用 SenseVoiceSmall 单模型
        logger.info("[STT] ⚠️ 降级为 SenseVoiceSmall 单模型模式...")
        try:
            return _recognize_via_local_sensevoice_only(audio_bytes, tmp_path)
        except Exception as e2:
            logger.error(f"[STT] 降级识别也失败: {e2}")
            return {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


def _recognize_via_local_sensevoice_only(audio_bytes: bytes, tmp_path: str = None) -> dict:
    """
    降级方案：仅用 SenseVoiceSmall 同时做文字识别和情感检测。
    当 Paraformer-Large 出错时自动切换到此方案。
    """
    need_cleanup = False
    try:
        if tmp_path is None:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
                need_cleanup = True

        model = _get_sensevoice_model()
        result = model.generate(
            input=tmp_path,
            language="zh",
            use_itn=True,
        )

        if result and len(result) > 0:
            raw_text = result[0].get("text", "")
            return _parse_sensevoice_output(raw_text)

        return {"text": "", "emotion": "平静", "emotion_raw": "NEUTRAL"}

    finally:
        if need_cleanup and tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


# ==========================================
# 🧪 本地快速测试
# ==========================================
# 用法：python services/stt_service.py test.wav

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python stt_service.py <音频文件路径>")
        print("示例: python stt_service.py test.wav")
        sys.exit(1)

    audio_file = sys.argv[1]

    if not os.path.exists(audio_file):
        print(f"❌ 文件不存在: {audio_file}")
        sys.exit(1)

    with open(audio_file, "rb") as f:
        audio_data = f.read()

    print(f"📂 读取音频文件: {audio_file} ({len(audio_data)} 字节)")
    print(f"🔧 模式: {'本地 GPU 双模型' if USE_LOCAL_GPU else '云端 DashScope'}")
    print("🔄 正在识别...")

    result = audio_to_text(audio_data)

    if result["text"]:
        print(f"✅ 识别文本: {result['text']}")
        print(f"😊 说话人情绪: {result['emotion']} ({result['emotion_raw']})")
    else:
        print("❌ 识别失败，请检查配置")

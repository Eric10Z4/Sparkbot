# ==========================================
# 发声合成模块 (TTS / Text-to-Speech)
# 负责把大模型生成的毒舌文字转为音频字节流
# ==========================================
#
# 📌 架构说明：
# 本模块对外暴露两个函数：
#   - text_to_audio(text) -> bytes      : 异步版，返回 WAV 音频字节
#   - text_to_audio_sync(text) -> bytes  : 同步版包装，方便非 async 场景调用
#
# 📌 当前方案（轻薄本开发期）：
# 使用微软 Edge-TTS（完全免费，无需 API Key，无需 GPU）
# 通过微软服务器在线合成，延迟约 1~2 秒，音质优秀
#
# 📌 游戏本部署方案（已注释，周末切换）：
# 使用 GPT-SoVITS 本地推理（可克隆专属音色）
# ==========================================

import asyncio
import io
import logging
import math
import os
import subprocess
import struct
import tempfile
import wave

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TTS")

# ==========================================
# 🔑 从全局配置中心导入
# ==========================================
from config import EDGE_TTS_VOICE, GPTSOVITS_API_URL, USE_LOCAL_GPU, GPTSOVITS_REF_AUDIO, GPTSOVITS_PROMPT_TEXT


# Edge-TTS 支持的 SSML 情绪风格映射
# 微软的 XiaoyiNeural 声音支持以下 express-as 风格
EMOTION_STYLE_MAP = {
    "angry":   "angry",         # 生气
    "happy":   "cheerful",      # 开心（微软叫 cheerful）
    "sad":     "sad",           # 难过
    "neutral": "default",       # 平静
}


async def text_to_audio(text: str, emotion: str = "neutral") -> bytes:
    """
    将文本转换为带情绪语气的音频字节流。

    这是整个系统的"嘴巴"——QClaw 大脑决定要说什么之后，
    由本函数负责把文字变成真实的声音，再推送给 ESP32 扬声器播放。

    参数:
        text (str): 要合成的文本，如 "你好蠢啊"
        emotion (str): 情绪标签，控制说话语气。
                       可选值："angry", "happy", "sad", "neutral"

    返回:
        bytes: 音频二进制数据，可直接推送给 ESP32 播放

    使用示例:
        >>> audio = await text_to_audio("你烦不烦！", emotion="angry")
        >>> audio = await text_to_audio("哼，才没有开心呢", emotion="happy")
    """
    if not text or not text.strip():
        logger.warning("[TTS] 收到空文本，跳过合成")
        return b""

    logger.info(f"[TTS] 开始合成: '{text}' (emotion={emotion})")

    try:
        if USE_LOCAL_GPU:
            logger.info("[TTS] Using local GPT-SoVITS API")
            audio_data = await asyncio.to_thread(_synthesize_via_gptsovits, text)
        else:
            logger.info("[TTS] Using Windows SAPI fallback")
            audio_data = await asyncio.to_thread(_synthesize_via_windows_sapi, text)
            
        # 🔊 增加响度，解决机器人端声音太小的问题
        try:
            if audio_data:
                from pydub import AudioSegment
                from pydub.effects import normalize
                import io
                audio_seg = AudioSegment.from_file(io.BytesIO(audio_data))
                # 先把波形拉满，然后再硬性放大 10 dB，专门对付 ESP32 这种小功率喇叭
                audio_seg = normalize(audio_seg) + 10
                out_buffer = io.BytesIO()
                audio_seg.export(out_buffer, format="wav")
                audio_data = out_buffer.getvalue()
                logger.info("[TTS] 已强行放大音频响度 (+10 dB)")
        except ImportError:
            logger.warning("[TTS] pydub 未安装，无法增强音量。请在终端运行: pip install pydub")
        except Exception as e:
            logger.warning(f"[TTS] 响度增强失败 (可忽略): {e}")

        logger.info(f"[TTS] 合成完成，音频大小: {len(audio_data)} 字节")
        return audio_data
    except Exception as e:
        logger.error(f"[TTS] 本地语音合成失败: {e}")
        logger.warning("[TTS] Using local fallback tone")
        return _fallback_tone_wav()


def _synthesize_via_windows_sapi(text: str) -> bytes:
    """Use Windows built-in SAPI to generate 16 kHz mono PCM WAV without network."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="sparkbot_tts_")
    os.close(fd)

    env = os.environ.copy()
    env["SPARKBOT_TTS_TEXT"] = text
    env["SPARKBOT_TTS_PATH"] = wav_path

    script = r"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    16000,
    [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
    [System.Speech.AudioFormat.AudioChannel]::Mono
)
$synth.Rate = 0
$synth.Volume = 100
$synth.SetOutputToWaveFile($env:SPARKBOT_TTS_PATH, $format)
$synth.Speak($env:SPARKBOT_TTS_TEXT)
$synth.Dispose()
"""

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "PowerShell TTS failed").strip())

        with open(wav_path, "rb") as f:
            data = f.read()

        if len(data) <= 44 or not data.startswith(b"RIFF"):
            raise RuntimeError("Windows TTS produced invalid WAV")

        return data
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass


def _fallback_tone_wav(duration_s: float = 0.8, sample_rate: int = 16000, freq: int = 660) -> bytes:
    """Generate a small 16 kHz mono PCM WAV tone for hardware playback tests."""
    frame_count = int(duration_s * sample_rate)
    amplitude = 9000
    frames = bytearray()

    for i in range(frame_count):
        sample = int(amplitude * math.sin(2.0 * math.pi * freq * i / sample_rate))
        frames.extend(struct.pack("<h", sample))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))

    return buffer.getvalue()


def text_to_audio_sync(text: str, emotion: str = "neutral") -> bytes:
    """
    同步版本的 text_to_audio，方便在非 async 代码中调用。
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, text_to_audio(text, emotion))
                return future.result()
        else:
            return loop.run_until_complete(text_to_audio(text, emotion))
    except RuntimeError:
        return asyncio.run(text_to_audio(text, emotion))


# ==========================================
# ☁️ 方案 A：微软 Edge-TTS（轻薄本使用）
# ==========================================
# 完全免费，无需 API Key，无需 GPU
# 音质非常好，支持多种中文声音
# 延迟约 1~2 秒（取决于网络）
#
# 可用声音列表（运行 edge-tts --list-voices 查看全部）：
#   zh-CN-XiaoyiNeural   : 年轻女声（活泼，适合傲娇人设）
#   zh-CN-XiaoxiaoNeural : 标准女声（温柔）
#   zh-CN-YunxiNeural    : 年轻男声
#   zh-CN-YunjianNeural  : 成熟男声

async def _synthesize_via_edge_tts(text: str, emotion: str = "neutral") -> bytes:
    """
    通过微软 Edge-TTS 在线合成语音（带情绪语气）。

    当 emotion 不是 neutral 时，使用 SSML 标记让微软的神经网络
    用对应的情绪风格来朗读文本，实现有感情的语音输出。
    """
    import edge_tts

    # 根据情绪决定是否使用 SSML
    style = EMOTION_STYLE_MAP.get(emotion, "default")

    if style != "default":
        # 使用 SSML 注入情绪风格
        # mstts:express-as 是微软专有的情绪控制标签
        ssml = f"""<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis'
            xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='zh-CN'>
            <voice name='{EDGE_TTS_VOICE}'>
                <mstts:express-as style='{style}'>
                    {text}
                </mstts:express-as>
            </voice>
        </speak>"""
        logger.info(f"[TTS] 使用 SSML 情绪风格: {style}")
        communicate = edge_tts.Communicate(ssml, EDGE_TTS_VOICE)
    else:
        # 普通合成，不加情绪修饰
        communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)

    # 流式接收音频数据（Edge-TTS 返回的是 MP3 格式）
    audio_chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])

    if not audio_chunks:
        logger.error("[TTS] Edge-TTS 未返回任何音频数据")
        return b""

    mp3_data = b"".join(audio_chunks)
    logger.info(f"[TTS] Edge-TTS 返回 MP3 数据: {len(mp3_data)} 字节")

    # 将 MP3 转为 WAV（ESP32 的 audio_play 更喜欢 WAV 格式）
    wav_data = _mp3_to_wav(mp3_data)
    return wav_data


def _mp3_to_wav(mp3_data: bytes) -> bytes:
    """
    将 MP3 音频数据转换为 WAV 格式。

    ESP32 的 audio_play() 函数播放 WAV 更稳定。
    使用 pydub 或 ffmpeg 进行转换。如果都没装，直接返回 MP3。
    """
    try:
        from pydub import AudioSegment

        # 从 MP3 字节加载
        audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
        # 转换为 ESP32 友好的格式：16kHz、16bit、单声道
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

        # 导出为 WAV
        wav_buffer = io.BytesIO()
        audio.export(wav_buffer, format="wav")
        return wav_buffer.getvalue()

    except ImportError:
        # pydub 未安装，直接返回 MP3（大部分场景也能用）
        logger.warning("[TTS] pydub 未安装，直接返回 MP3 格式。"
                       "如需 WAV 请运行: pip install pydub")
        return mp3_data
    except Exception as e:
        logger.warning(f"[TTS] MP3→WAV 转换失败: {e}，返回原始 MP3")
        return mp3_data


# ==========================================
# 🎮 方案 B：GPT-SoVITS 本地推理（游戏本部署时启用）
# ==========================================
# 当你回到 14900HX + 4080 游戏本时：
# 1. 先启动 GPT-SoVITS 的 API 服务（默认端口 9880）
# 2. 把 config.py 中的 USE_LOCAL_GPU 改为 True
# 3. 本模块会自动切换到本地推理
#
# GPT-SoVITS 优势：
#   - 只需要 3~10 秒的参考音频就能克隆任意音色
#   - 完全离线，隐私安全
#   - 延迟约 200~500ms（取决于文本长度）
#
# 启动命令（在 GPT-SoVITS 目录下）：
#   python api.py -a 127.0.0.1 -p 9880

# ----- 以下为游戏本部署代码（当前已注释）-----

import requests

def _synthesize_via_gptsovits(text: str) -> bytes:
    """
    通过本地 GPT-SoVITS API 合成语音。

    前提：GPT-SoVITS 的 api.py 已在本地 9880 端口启动。
    """
    try:
        # GPT-SoVITS v2 api endpoint is /tts or root depending on the api_v2.py implementation
        # usually text, text_lang, etc. are passed. 
        logger.info("[TTS] Sending GET / to GPT-SoVITS...")
        resp = requests.get(
            "http://127.0.0.1:9880/",  # api_v2.py default uses / (or /tts if specified in config, but let's try root first as per v2)
            params={
                "text": text,
                "text_lang": "zh", # V2
                "text_language": "zh", # V1
                "prompt_lang": "zh", # 因为没有C++环境，改回纯中文
                "prompt_language": "zh", # V1
                "prompt_text": GPTSOVITS_PROMPT_TEXT,
                "ref_audio_path": GPTSOVITS_REF_AUDIO, # V2
                "refer_wav_path": GPTSOVITS_REF_AUDIO, # V1
                "speed": 1.0, # 恢复正常速度，解决电音和糊的问题
                "speed_factor": 1.0 # 恢复正常速度
            },
            timeout=120,
        )
        logger.info(f"[TTS] GET / returned {resp.status_code}")

        if resp.status_code == 200:
            logger.info(f"[TTS] GPT-SoVITS 合成完成: {len(resp.content)} 字节")
            return resp.content
        elif resp.status_code == 404:
            # Maybe it uses /tts
            resp = requests.get(
                "http://127.0.0.1:9880/tts",
                params={
                    "text": text,
                    "text_lang": "zh",
                    "text_language": "zh",
                    "prompt_lang": "zh",
                    "prompt_language": "zh",
                    "prompt_text": GPTSOVITS_PROMPT_TEXT,
                    "ref_audio_path": GPTSOVITS_REF_AUDIO,
                    "refer_wav_path": GPTSOVITS_REF_AUDIO,
                    "speed": 1.0,
                    "speed_factor": 1.0
                },
                timeout=120,
            )
            if resp.status_code == 200:
                logger.info(f"[TTS] GPT-SoVITS 合成完成: {len(resp.content)} 字节")
                return resp.content
            else:
                logger.error(f"[TTS] GPT-SoVITS 返回错误: {resp.status_code} - {resp.text}")
                return b""
        else:
            logger.error(f"[TTS] GPT-SoVITS 返回错误: {resp.status_code} - {resp.text}")
            return b""

    except requests.ConnectionError:
        logger.error("[TTS] 无法连接 GPT-SoVITS，请确认 api.py 是否已启动")
        return b""
    except Exception as e:
        logger.error(f"[TTS] GPT-SoVITS 合成失败: {e}")
        return b""

# ----- 游戏本部署代码结束 -----

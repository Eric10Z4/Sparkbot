# ==========================================
# 🧪 STT 语音识别测试
# ==========================================
# 两种测试模式：
#   1. 用麦克风实时录音测试：python tests/test_stt.py
#   2. 用现有音频文件测试：  python tests/test_stt.py path/to/audio.wav
# ==========================================

import sys
import os
import io

# 修复 Windows 控制台 GBK 编码问题，确保 emoji 能正常输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 把项目根目录加入 Python 路径，这样才能 import 我们的模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.stt_service import audio_to_text


def record_from_microphone(duration: int = 5, sample_rate: int = 16000) -> bytes:
    """
    用电脑麦克风录音指定秒数，返回 WAV 格式的字节流。

    参数:
        duration: 录音时长（秒），默认 5 秒
        sample_rate: 采样率，DashScope 推荐 16000Hz

    返回:
        bytes: WAV 格式的音频二进制数据
    """
    try:
        import pyaudio
        import wave
        import io
    except ImportError:
        print("❌ 缺少录音依赖，正在安装 pyaudio...")
        os.system("python -m pip install pyaudio")
        import pyaudio
        import wave
        import io

    # 录音参数
    CHANNELS = 1          # 单声道（机器人麦克风也是单声道）
    FORMAT = pyaudio.paInt16   # 16bit 量化
    CHUNK = 1024          # 每次读取的采样点数

    p = pyaudio.PyAudio()

    print(f"🎤 准备录音，请在 {duration} 秒内对着麦克风说话...")
    print("=" * 40)

    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=sample_rate,
        input=True,
        frames_per_buffer=CHUNK,
    )

    frames = []
    for i in range(0, int(sample_rate / CHUNK * duration)):
        data = stream.read(CHUNK)
        frames.append(data)
        # 每秒打印一个进度点
        if i % int(sample_rate / CHUNK) == 0:
            elapsed = i // int(sample_rate / CHUNK)
            remaining = duration - elapsed
            print(f"  ⏱️ 录音中... 剩余 {remaining} 秒")

    print("=" * 40)
    print("🔇 录音结束！")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # 将 PCM 数据封装成 WAV 格式（DashScope 需要 WAV 头）
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(frames))

    return wav_buffer.getvalue()


def test_with_file(file_path: str):
    """用已有的音频文件进行测试"""
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return

    with open(file_path, "rb") as f:
        audio_data = f.read()

    print(f"📂 读取音频文件: {file_path} ({len(audio_data)} 字节)")
    _run_recognition(audio_data)


def test_with_microphone(duration: int = 5):
    """用麦克风录音进行测试"""
    audio_data = record_from_microphone(duration)
    print(f"📦 录音数据大小: {len(audio_data)} 字节")

    # 可选：保存录音到文件（方便反复测试，不用每次都重新录）
    save_path = os.path.join(os.path.dirname(__file__), "last_recording.wav")
    with open(save_path, "wb") as f:
        f.write(audio_data)
    print(f"💾 录音已保存到: {save_path}")

    _run_recognition(audio_data)


def _run_recognition(audio_data: bytes):
    """执行识别并漂亮地打印结果"""
    print("\n🔄 正在发送到云端进行识别...\n")

    result = audio_to_text(audio_data)

    print("=" * 50)
    if result["text"]:
        print(f"  ✅ 识别文本:   {result['text']}")
        print(f"  😊 说话人情绪: {result['emotion']} ({result['emotion_raw']})")

        # 模拟实际注入给 QClaw 大脑的格式
        injected = f"[麦克风][用户情绪：{result['emotion']}] {result['text']}"
        print(f"\n  📝 注入 QClaw 的格式:")
        print(f"     {injected}")
    else:
        print("  ❌ 识别失败！")
        print("  🔍 请检查:")
        print("     1. config.py 中的 DASHSCOPE_API_KEY 是否正确")
        print("     2. 网络连接是否正常")
        print("     3. DashScope 控制台是否已开通 SenseVoice 服务")
    print("=" * 50)


if __name__ == "__main__":
    print("🧪 SparkBot STT 语音识别测试")
    print("=" * 50)

    if len(sys.argv) >= 2:
        # 模式 1：用指定的音频文件测试
        test_with_file(sys.argv[1])
    else:
        # 模式 2：用麦克风实时录音测试
        print("📌 未指定音频文件，将使用麦克风录音")
        print("📌 如需用文件测试: python tests/test_stt.py your_audio.wav\n")

        try:
            duration = 5
            test_with_microphone(duration)
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断录音")
        except Exception as e:
            print(f"\n❌ 录音失败: {e}")
            print("💡 如果 PyAudio 安装失败，可以手动录一段 WAV 文件后运行:")
            print("   python tests/test_stt.py your_audio.wav")

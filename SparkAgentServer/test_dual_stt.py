"""双模型 STT 测试脚本"""
import sys, os, io, wave, struct, math, time
sys.path.insert(0, '.')
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 生成测试 WAV（440Hz 正弦波，2秒）
sample_rate = 16000
duration = 2.0
freq = 440
samples = int(sample_rate * duration)
wav_buffer = io.BytesIO()
with wave.open(wav_buffer, 'wb') as wf:
    wf.setnchannels(1)
    wf.setsampwidth(2)
    wf.setframerate(sample_rate)
    for i in range(samples):
        sample = int(32767 * 0.5 * math.sin(2 * math.pi * freq * i / sample_rate))
        wf.writeframes(struct.pack('<h', sample))

audio_bytes = wav_buffer.getvalue()
print(f"Generated test audio: {len(audio_bytes)} bytes")

# 测试双模型
start = time.time()
from services.stt_service import audio_to_text
result = audio_to_text(audio_bytes)
elapsed = time.time() - start

print(f"Result: {result}")
print(f"Time: {elapsed:.2f}s (includes model loading on first call)")
print(f"Text: [{result['text']}]")
print(f"Emotion: {result['emotion']} ({result['emotion_raw']})")

# 第二次调用（模型已加载，测真实延迟）
start2 = time.time()
result2 = audio_to_text(audio_bytes)
elapsed2 = time.time() - start2
print(f"\n=== Second call (models already loaded) ===")
print(f"Time: {elapsed2:.3f}s")
print(f"Text: [{result2['text']}]")
print(f"Emotion: {result2['emotion']} ({result2['emotion_raw']})")

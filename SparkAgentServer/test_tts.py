import sys
import os
sys.path.insert(0, '.')
import time
from services.tts_service import text_to_audio_sync

os.environ['PYTHONIOENCODING'] = 'utf-8'

print("=== Testing Local GPT-SoVITS TTS ===")
start = time.time()
audio_bytes = text_to_audio_sync("没问题！系统已经全面升级完毕，随时可以开始执行任务。别小看我哦，我可是非常厉害的！")
elapsed = time.time() - start

print(f"Generated audio: {len(audio_bytes)} bytes in {elapsed:.3f}s")
if len(audio_bytes) > 0:
    with open("tts_test_output.wav", "wb") as f:
        f.write(audio_bytes)
    print("Saved audio to tts_test_output.wav")
else:
    print("Failed to generate audio!")

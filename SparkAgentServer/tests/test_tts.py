# ==========================================
# 🧪 TTS 语音合成测试
# ==========================================
# 用法：
#   python tests/test_tts.py                  → 合成默认测试语句
#   python tests/test_tts.py "你好蠢啊"        → 合成指定文本
#   python tests/test_tts.py "你好蠢啊" --play → 合成并播放
# ==========================================

import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from services.tts_service import text_to_audio


async def main():
    # 确定要合成的文本
    text = "你好蠢啊，这种问题也要问我？"
    should_play = False

    for arg in sys.argv[1:]:
        if arg == "--play":
            should_play = True
        else:
            text = arg

    print(f"🗣️ 要合成的文本: {text}")
    print("=" * 50)
    print("🔄 正在合成...")

    audio_data = await text_to_audio(text)

    if not audio_data:
        print("❌ 合成失败！")
        return

    print(f"✅ 合成成功！音频大小: {len(audio_data)} 字节")

    # 保存到文件
    save_dir = os.path.dirname(__file__)
    save_path = os.path.join(save_dir, "last_tts_output.wav")
    with open(save_path, "wb") as f:
        f.write(audio_data)
    print(f"💾 已保存到: {save_path}")

    # 如果指定了 --play，尝试播放
    if should_play:
        print("🔊 正在播放...")
        try:
            # Windows 下用系统自带播放器
            if sys.platform == "win32":
                os.startfile(save_path)
            else:
                os.system(f"aplay {save_path} 2>/dev/null || afplay {save_path} 2>/dev/null")
            print("✅ 播放完毕")
        except Exception as e:
            print(f"⚠️ 播放失败: {e}")
            print(f"💡 请手动打开文件播放: {save_path}")
    else:
        print(f"\n💡 加 --play 参数可直接播放:")
        print(f'   python tests/test_tts.py "{text}" --play')

    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())

# ==========================================
# 供 QClaw 等 Agent 调用的专属功能库 (Tool Use / MCP Hook)
# ==========================================
#
# 这些函数是 QClaw SKILL.md 里定义的 curl 指令的"本地直调"版本。
# main.py 的 API 端点内部会调用这些函数。
#
# 注意：这些函数不直接操控硬件，
# 它们通过 main.py 暴露的全局 _push_xxx 函数间接下发指令。
# ==========================================

import logging
from services.tts_service import text_to_audio

logger = logging.getLogger("SKILLS")


async def physical_speak(text: str, emotion: str = "neutral") -> bytes:
    """
    让机器人用扬声器说出一句话（带情绪语气）。

    返回合成的音频数据，由调用方决定如何下发给硬件。
    """
    logger.info(f"[Skill] physical_speak: text='{text}', emotion={emotion}")
    audio_data = await text_to_audio(text, emotion=emotion)
    logger.info(f"[Skill] TTS 合成完毕: {len(audio_data)} 字节")
    return audio_data


async def change_face(expression_id: str) -> dict:
    """
    切换机器人表情。

    返回要下发给 ESP32 的指令 dict，由调用方负责推送。
    """
    logger.info(f"[Skill] change_face: expression_id={expression_id}")
    return {"type": "set_face", "expression_id": expression_id}


async def robot_move(direction: str, duration: int) -> dict:
    """
    控制机器人履带移动。

    安全限制：duration 最大 5 秒。
    返回要下发给 ESP32 的指令 dict，由调用方负责推送。
    """
    duration = min(duration, 5)  # 硬限制
    logger.info(f"[Skill] robot_move: direction={direction}, duration={duration}s")
    return {"type": "move", "direction": direction, "duration": duration}

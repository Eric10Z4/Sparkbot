# ==========================================
# SparkBot 神经中枢 (main.py)
# ==========================================
# 【启动指令】每次重启电脑后，你需要开一个终端运行以下命令来启动本服务：
# python main.py 或者通过绝对路径调用你的 python 解释器
# ==========================================
#
# 这是整个系统的大脑枢纽，负责：
# 1. 对外暴露 HTTP API（给 QClaw Agent 的技能调用）
# 2. 管理与 ESP32 机器人的 WebSocket 双向通道
# 3. 串联 STT、TTS、视觉感知等所有软件模块
#
# 当前阶段：纯软件联调（硬件 B 同学还没开工）
# 所有 WebSocket 下发暂时只做日志打印，等硬件接入后直接启用
# ==========================================

import asyncio
import json
import base64
import logging
import time
import httpx
import websockets

# --- SSL Patch for Windows Broken Certificates ---
import ssl
import certifi
_orig_create_default_context = ssl.create_default_context
def _patched_create_default_context(*args, **kwargs):
    if "cafile" not in kwargs:
        kwargs["cafile"] = certifi.where()
    return _orig_create_default_context(*args, **kwargs)
ssl.create_default_context = _patched_create_default_context
# -------------------------------------------------
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import uvicorn
import cv2
import numpy as np

# ==========================================
# 🔑 从配置中心导入
# ==========================================
from config import SERVER_HOST, SERVER_PORT, WEBSOCKET_HOST, WEBSOCKET_PORT, WECHAT_TARGET_ID, API_TOKEN, DEVICE_TOKEN
from security import install_http_auth, authenticate_device, validate_tokens

import os

# ==========================================
# 🔔 哨兵→OpenClaw→微信通知配置
# ==========================================
GATEWAY_URL = "http://127.0.0.1:18789"
# ✅ 修正：全部小写（实际 session key 就是小写）
WECHAT_SESSION = f"agent:main:openclaw-weixin:direct:{WECHAT_TARGET_ID.lower()}@im.wechat"
# 机器人麦克风听到的话 → 转发到微信 session（主人在微信上聊）
ROBOT_SPEECH_SESSION = WECHAT_SESSION

def _get_openclaw_token():
    try:
        # 尝试从 openclaw.json 读取 token
        config_path = Path(os.path.expanduser("~/.openclaw/openclaw.json"))
        if not config_path.exists():
            config_path = Path(__file__).resolve().parent.parent / "openclaw" / "openclaw.json"
        
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gateway", {}).get("auth", {}).get("token", "")
    except Exception as e:
        logger.warning(f"[AGENT] 读取 OpenClaw Token 失败: {e}")
    return ""

OPENCLAW_TOKEN = _get_openclaw_token()

async def forward_to_agent(user_text: str):
    """
    将机器人麦克风听到的内容通过 openclaw CLI 转发到微信 session。
    HTTP 注入路径不稳定，CLI 已验证可用。
    """
    import shutil
    tagged = f"[麦克风] {user_text}"
    exe = shutil.which("openclaw") or ("openclaw.cmd" if os.name == "nt" else "openclaw")
    proc = await asyncio.create_subprocess_exec(
        exe, "agent", "--session-key", ROBOT_SPEECH_SESSION, "--message", tagged,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        logger.info(f"[AGENT] 已转发给大脑(微信): {user_text[:50]}…")
    else:
        logger.warning(f"[AGENT] 转发失败 (exit={proc.returncode}): {stderr.decode()[:200]}")


async def notify_agent(alert_text: str):
    """
    把哨兵告警注入，通过微信通知主人。
    """
    try:
        import shutil, os
        exe = shutil.which("openclaw") or ("openclaw.cmd" if os.name == "nt" else "openclaw")
        proc = await asyncio.create_subprocess_exec(
            exe, "message", "send", 
            "--channel", "openclaw-weixin", 
            "--target", f"{WECHAT_TARGET_ID}@im.wechat", 
            "--message", f"[哨兵警报] {alert_text}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            logger.info(f"[NOTIFY] 告警已发往微信: {alert_text[:50]}…")
        else:
            logger.warning(f"[NOTIFY] 微信发送失败: {stderr.decode()[:100]}")
    except Exception as e:
        logger.error(f"[NOTIFY] 执行 openclaw message send 失败: {e}")

# ==========================================
# 📦 导入各软件模块
# ==========================================
from services.stt_service import audio_to_text, _pcm16_mono_to_wav  # 听觉：音频 → 文字+情绪
from services.tts_service import text_to_audio          # 发声：文字+情绪 → 音频
from services.visual import (                           # 视觉：图片 → 识别结果
    face_recognize,
    detect_anomaly,
    register_face,
    remove_face,
    list_faces,
    detect_objects,
)

# ==========================================
# 📝 日志配置
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("MAIN")

# ==========================================
# 🚀 FastAPI 应用实例
# ==========================================
app = FastAPI(
    title="SparkBot Backend",
    description="桌面机器人 AI 大脑枢纽：STT + LLM + TTS + 视觉感知",
    version="0.2.0",
)
install_http_auth(app, API_TOKEN)


# ==========================================
# 📋 请求体模型（Pydantic）
# ==========================================
class SpeakRequest(BaseModel):
    """physical-speak 技能的请求体"""
    text: str = Field(..., description="要说的话")
    emotion: str = Field("neutral", description="情绪：angry/happy/sad/neutral")

class FaceRequest(BaseModel):
    """change-face 技能的请求体"""
    expression_id: str = Field(..., description="表情 ID：speak/angry/look/sleep 等")

class MoveRequest(BaseModel):
    """robot-move 技能的请求体"""
    direction: str = Field(..., description="方向：forward/backward/left/right/spin")
    duration: int = Field(1, description="持续时间（秒），安全限制 <5s")

class CameraCaptureRequest(BaseModel):
    """camera-capture 技能的请求体"""
    count: int = Field(3, description="连续拍照张数，最多 10 张")
    interval_ms: int = Field(500, description="每张之间的间隔，毫秒")

class FaceRegisterRequest(BaseModel):
    """人脸注册的请求体"""
    name: str = Field(..., description="要注册的人名")
    image_base64: str = Field(..., description="JPEG 图片的 base64 编码")

class VisualRequest(BaseModel):
    """视觉识别的请求体（手动触发用）"""
    image_base64: str = Field(..., description="JPEG 图片的 base64 编码")


# ==========================================
# 🤖 全局状态：ESP32 硬件连接
# ==========================================
connected_hardware = None  # WebSocket 连接对象
websocket_server_task = None
robot_status = {           # 机器人最新状态（由 ESP32 定期上报）
    "connected": False,
    "battery": -1,
    "pitch": 0.0,
    "roll": 0.0,
    "last_image": None,
}

last_face_seen = {}
FACE_COOLDOWN = 30  # 人脸检测防抖冷却时间（秒）

CAPTURE_DIR = Path(__file__).resolve().parent / "captured_images"
AUDIO_CAPTURE_DIR = Path(__file__).resolve().parent / "captured_audio"


def save_rgb565_as_jpg(raw: bytes, width: int, height: int, jpg_path: Path) -> Optional[bytes]:
    """Save RGB565 big-endian raw frame as a JPEG image, rotating 180 degrees. Returns JPG bytes."""
    try:
        expected = width * height * 2
        if len(raw) != expected:
            logger.warning(f"Image length mismatch: expected {expected}, got {len(raw)}")
            return None

        pixels = np.frombuffer(raw, dtype=">u2").reshape((height, width))
        r5 = (pixels >> 11) & 0x1F
        g6 = (pixels >> 5) & 0x3F
        b5 = pixels & 0x1F

        r8 = ((r5 << 3) | (r5 >> 2)).astype(np.uint8)
        g8 = ((g6 << 2) | (g6 >> 4)).astype(np.uint8)
        b8 = ((b5 << 3) | (b5 >> 2)).astype(np.uint8)
        
        # Merge into BGR for OpenCV
        bgr = np.dstack((b8, g8, r8))
        
        # SparkBot camera is mounted upside down, rotate 180
        bgr = cv2.rotate(bgr, cv2.ROTATE_180)
        
        jpg_path.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        if ok:
            jpg_bytes = encoded.tobytes()
            jpg_path.write_bytes(jpg_bytes)
            return jpg_bytes
        return None
    except Exception as e:
        logger.error(f"Failed to convert RGB565 to JPG: {e}")
        return None


# ==========================================
# 📡 第一部分：HTTP API 接口（给 QClaw Agent 技能调用）
# ==========================================

@app.post("/api/speak")
async def api_speak(request: Request, text: str = None, emotion: str = "neutral"):
    """
    让机器人说话（带情绪语气）。

    QClaw 的 physical_speak 技能会 curl 这个接口。
    支持两种调用方式：
    1. JSON body: {"text": "xxx", "emotion": "angry"}
    2. Query params: ?text=xxx&emotion=angry
    """
    # 优先从 JSON body 中取参数，失败则用 query params
    if text is None:
        try:
            body = await request.json()
            text = body.get("text", "")
            emotion = body.get("emotion", emotion)
        except Exception:
            # 如果 JSON 也解析失败，尝试读取原始 body
            raw = await request.body()
            logger.warning(f"[API] /api/speak 无法解析请求体: {raw[:200]}")
            return {"status": "error", "msg": "无法解析请求，缺少 text 参数"}

    if not text:
        return {"status": "error", "msg": "text 参数为空"}

    logger.info(f"[API] /api/speak 被调用: text='{text}', emotion={emotion}")

    # 1. TTS 合成（带情绪）
    audio_data = await text_to_audio(text, emotion=emotion)
    if not audio_data:
        return {"status": "error", "msg": "TTS 合成失败"}

    # === [Debug] 将最后一次合成出的音频强制存盘，方便你试听 ===
    try:
        debug_path = Path(__file__).resolve().parent / "debug_last_speak.wav"
        debug_path.write_bytes(audio_data)
        logger.info(f"[API] 截获生成的音频流，已强行备份到 {debug_path}")
    except Exception as e:
        logger.error(f"[API] 备份音频失败: {e}")

    # 2. 推送给 ESP32（如果已连接）
    pushed = await _push_audio_to_hardware(audio_data)

    return {
        "status": "success",
        "msg": f"已合成并{'推送' if pushed else '暂存'}：{text}",
        "audio_size": len(audio_data),
        "emotion": emotion,
    }


@app.post("/api/face")
async def api_face(request: Request, expression_id: str = None):
    """
    切换机器人表情。
    """
    if expression_id is None:
        try:
            body = await request.json()
            expression_id = body.get("expression_id", "")
        except Exception:
            return {"status": "error", "msg": "无法解析请求，缺少 expression_id 参数"}

    if not expression_id:
        return {"status": "error", "msg": "expression_id 不能为空"}

    logger.info(f"[API] /api/face 被调用: expression_id={expression_id}")

    pushed = await _push_command_to_hardware({
        "type": "set_face",
        "expression_id": expression_id,
    })

    return {
        "status": "success" if pushed else "pending",
        "msg": f"表情已{'下发' if pushed else '暂存（硬件未连接）'}：{expression_id}",
    }


@app.post("/api/move")
async def api_move(request: Request, direction: str = None, duration: int = 1):
    """
    控制机器人履带移动。
    """
    if direction is None:
        try:
            body = await request.json()
            direction = body.get("direction", "")
            duration = int(body.get("duration", 1))
        except Exception:
            return {"status": "error", "msg": "无法解析请求，缺少 direction 参数"}

    if not direction:
        return {"status": "error", "msg": "direction 不能为空"}

    # 安全限制
    if duration > 5:
        return {"status": "error", "msg": "安全限制：duration 不能超过 5 秒，防止掉桌子"}

    logger.info(f"[API] /api/move 被调用: direction={direction}, duration={duration}")

    pushed = await _push_command_to_hardware({
        "type": "move",
        "direction": direction,
        "duration": duration,
    })

    return {
        "status": "success" if pushed else "pending",
        "msg": f"移动已{'下发' if pushed else '暂存（硬件未连接）'}：{direction} {duration}s",
    }


@app.post("/api/camera/capture")
async def api_camera_capture(req: CameraCaptureRequest):
    """让 ESP32 连续拍摄多张图片并上传。"""
    count = max(1, min(int(req.count), 10))
    interval_ms = max(100, min(int(req.interval_ms), 5000))

    logger.info(f"[API] /api/camera/capture 被调用: count={count}, interval_ms={interval_ms}")
    pushed = await _push_command_to_hardware({
        "type": "capture_images",
        "count": count,
        "interval_ms": interval_ms,
    })

    return {
        "status": "success" if pushed else "pending",
        "msg": f"拍照指令已{'下发' if pushed else '暂存（硬件未连接）'}：{count} 张",
        "count": count,
        "interval_ms": interval_ms,
    }


@app.get("/api/status")
async def api_status():
    """返回机器人当前状态（是否连接、电量等）"""
    return {
        "status": "success",
        "robot": robot_status,
    }


# ==========================================
# 👁️ 第二部分：视觉感知 API（C 同学模块对接）
# ==========================================

@app.post("/api/visual/recognize")
async def api_visual_recognize(req: VisualRequest):
    """
    手动触发人脸识别。

    上传一张图片（base64），调用 C 同学的 face_recognize 函数。
    返回识别结果，同时可以作为上下文注入 QClaw 大脑。
    """
    try:
        image_bytes = base64.b64decode(req.image_base64)
    except Exception as e:
        return {"status": "error", "msg": f"Base64解码失败: {str(e)}"}
        
    result = face_recognize(image_bytes)
    logger.info(f"[VISUAL] 人脸识别结果: {result}")

    # 格式化为可注入 QClaw 的上下文字符串
    if result["detected"]:
        context = f"[视觉感知] 检测到 {result['count']} 张人脸，识别为: {result['name']}（置信度 {result['confidence']:.0%}）"
    else:
        context = "[视觉感知] 画面中未检测到人脸"

    return {"status": "success", "result": result, "context_for_agent": context}


@app.post("/api/visual/anomaly")
async def api_visual_anomaly(req: VisualRequest):
    """手动触发异常检测。"""
    try:
        image_bytes = base64.b64decode(req.image_base64)
    except Exception as e:
        return {"status": "error", "msg": f"Base64解码失败: {str(e)}"}
        
    result = detect_anomaly(image_bytes)
    logger.info(f"[VISUAL] 异常检测结果: {result}")

    if result["is_anomaly"]:
        context = f"[视觉感知][⚠️异常] {result['anomaly_type']}: {result['description']}"
    else:
        context = "[视觉感知] 环境正常，无异常"

    return {"status": "success", "result": result, "context_for_agent": context}


@app.post("/api/visual/objects")
async def api_visual_objects(req: VisualRequest):
    """手动触发物体识别。"""
    try:
        image_bytes = base64.b64decode(req.image_base64)
    except Exception as e:
        return {"status": "error", "msg": f"Base64解码失败: {str(e)}"}
        
    result = detect_objects(image_bytes)
    logger.info(f"[VISUAL] 物体识别结果: {result}")

    context = f"[视觉感知] {result['description']}"
    return {"status": "success", "result": result, "context_for_agent": context}


@app.post("/api/visual/register")
async def api_visual_register(req: FaceRegisterRequest):
    """注册一张新人脸到底库。"""
    try:
        image_bytes = base64.b64decode(req.image_base64)
    except Exception as e:
        return {"status": "error", "msg": f"Base64解码失败: {str(e)}"}
        
    result = register_face(req.name, image_bytes)
    logger.info(f"[VISUAL] 人脸注册结果: {result}")
    return {"status": "success" if result["success"] else "error", "result": result}


@app.delete("/api/visual/face/{name}")
async def api_visual_remove(name: str):
    """从底库中删除一个人。"""
    result = remove_face(name)
    logger.info(f"[VISUAL] 人脸删除结果: {result}")
    return {"status": "success" if result["success"] else "error", "result": result}


@app.get("/api/visual/faces")
async def api_visual_list():
    """列出底库中所有已注册的人名。"""
    faces = list_faces()
    return {"status": "success", "faces": faces, "count": len(faces)}


# ==========================================
# 🔌 第三部分：WebSocket 硬件通道（等 B 同学接入）
# ==========================================

async def handle_robot_connection(websocket):
    """
    处理 ESP32 机器人的 WebSocket 连接。

    ESP32 连上后会持续发送数据：
    - bytes 类型 → 音频流（麦克风录音）
    - str 类型 → JSON 状态/图片数据
    """
    global connected_hardware, robot_status
    if not await authenticate_device(websocket, DEVICE_TOKEN):
        return
    if connected_hardware is not None:
        await websocket.close(code=1008, reason="A robot is already connected")
        return
    connected_hardware = websocket
    robot_status["connected"] = True

    logger.info("=" * 50)
    logger.info("🤖 ESP32 机器人已连接！神经中枢对通！")
    logger.info("=" * 50)

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # ===== 收到音频流 → STT 识别 =====
                logger.info(f"[WS] 收到硬件音频流: {len(message)} 字节")
                audio_for_stt = message if message.startswith(b"RIFF") else _pcm16_mono_to_wav(message)
                AUDIO_CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
                audio_path = AUDIO_CAPTURE_DIR / f"sparkbot_{time.strftime('%Y%m%d_%H%M%S')}.wav"
                audio_path.write_bytes(audio_for_stt)
                logger.info(f"[WS] 麦克风音频已保存: {audio_path}")

                stt_result = await asyncio.to_thread(audio_to_text, audio_for_stt)
                if stt_result["text"]:
                    # 格式化为 QClaw 可用的上下文
                    agent_input = f"[麦克风][用户情绪：{stt_result['emotion']}] {stt_result['text']}"
                    logger.info(f"[WS] 听力解析 → {agent_input}")
                    # 方案 A: 异步转发给 QClaw 大脑，让大脑通过 physical_speak 技能自行回调
                    asyncio.create_task(forward_to_agent(agent_input))
                else:
                    logger.info("[WS] 音频识别结果为空（可能是噪音）")

            else:
                # ===== 收到 JSON 数据 =====
                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "unknown")

                    if msg_type == "image":
                        # 图片数据：ESP32 当前上传 RGB565 原始帧，先保存用于联调确认
                        image_bytes = base64.b64decode(data.get("data", ""))
                        image_format = data.get("format", "unknown")
                        width = int(data.get("width", 0))
                        height = int(data.get("height", 0))
                        index = int(data.get("index", 1))
                        total = int(data.get("total", 1))
                        suffix = "rgb565" if image_format == "rgb565" else image_format

                        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        image_path = CAPTURE_DIR / f"sparkbot_{timestamp}_{index:02d}_of_{total:02d}.{suffix}"
                        image_path.write_bytes(image_bytes)
                        display_path = image_path

                        if image_format == "rgb565":
                            jpg_path = image_path.with_suffix(".jpg")
                            jpg_bytes = save_rgb565_as_jpg(image_bytes, width, height, jpg_path)
                            if jpg_bytes is not None:
                                display_path = jpg_path
                                # Replace raw data with JPG bytes so vision models can read it
                                image_bytes = jpg_bytes
                                image_format = "jpg"

                        robot_status["last_image"] = str(display_path)

                        logger.info(
                            f"[WS] 收到图片 {index}/{total}: "
                            f"{image_format} {width}x{height}, {len(image_bytes)} 字节, 已保存: {display_path}"
                        )

                        if image_format in ("jpeg", "jpg"):
                            face_result = face_recognize(image_bytes)
                            anomaly_result = detect_anomaly(image_bytes)

                            if face_result["detected"]:
                                name = face_result.get("name", "未知")
                                now = time.time()
                                if now - last_face_seen.get(name, 0) > FACE_COOLDOWN:
                                    last_face_seen[name] = now
                                    logger.info(f"[WS] 视觉感知: 检测到 {name} (触发大模型提醒)")
                                    # 注入 OpenClaw → Agent
                                    asyncio.create_task(forward_to_agent(f"[视觉感知] 画面中出现了 {name}。"))

                            if anomaly_result["is_anomaly"]:
                                logger.warning(f"[WS] ⚠️ 异常检测: {anomaly_result['description']}")
                                # 注入 OpenClaw → Agent 自动微信通知主人
                                await notify_agent(
                                    f"检测到异常：{anomaly_result['description']} | "
                                    f"检测到人脸：{face_result.get('name', '未知') if face_result.get('detected') else '无'}"
                                )

                    elif msg_type == "status":
                        # 状态上报 → 更新全局状态
                        robot_status["battery"] = data.get("battery", -1)
                        robot_status["pitch"] = data.get("pitch", 0.0)
                        robot_status["roll"] = data.get("roll", 0.0)
                        robot_status["yaw"] = data.get("yaw", 0.0)
                        logger.info(
                            f"[WS] 机器人状态: 电量={robot_status['battery']}%, "
                            f"pitch={robot_status['pitch']:.2f}, "
                            f"roll={robot_status['roll']:.2f}, "
                            f"yaw={robot_status['yaw']:.2f}"
                        )

                    else:
                        logger.info(f"[WS] 收到未知类型消息: {message[:200]}")

                except json.JSONDecodeError:
                    logger.warning(f"[WS] 收到非 JSON 文本: {message[:100]}")

    except websockets.exceptions.ConnectionClosed:
        logger.warning("❌ 机器人断开连接")
    finally:
        if connected_hardware is websocket:
            connected_hardware = None
            robot_status["connected"] = False


# ==========================================
# 📤 硬件下发工具函数
# ==========================================

async def _push_audio_to_hardware(audio_data: bytes) -> bool:
    """将合成的音频推送给 ESP32 播放。"""
    if connected_hardware is None:
        logger.warning("[PUSH] 硬件未连接，音频暂存（等待硬件接入后启用）")
        return False

    try:
        # 封装为 JSON + base64 发送
        payload = json.dumps({
            "type": "play_audio",
            "data": base64.b64encode(audio_data).decode("utf-8"),
        })
        await connected_hardware.send(payload)
        logger.info(f"[PUSH] 音频已推送给硬件: {len(audio_data)} 字节")
        return True
    except Exception as e:
        logger.error(f"[PUSH] 音频推送失败: {e}")
        return False


async def _push_command_to_hardware(command: dict) -> bool:
    """将控制指令推送给 ESP32 执行。"""
    if connected_hardware is None:
        logger.warning(f"[PUSH] 硬件未连接，指令暂存: {command}")
        return False

    try:
        await connected_hardware.send(json.dumps(command))
        logger.info(f"[PUSH] 指令已下发: {command}")
        return True
    except Exception as e:
        logger.error(f"[PUSH] 指令下发失败: {e}")
        return False


# ==========================================
# 🏁 启动入口
# ==========================================

async def start_websocket_server():
    """启动 WebSocket 服务器，等待 ESP32 机器人连接。"""
    logger.info(f"=> 启动硬件挂载点 WebSocket (监听 ws://{WEBSOCKET_HOST}:{WEBSOCKET_PORT})...")
    async with websockets.serve(handle_robot_connection, WEBSOCKET_HOST, WEBSOCKET_PORT):
        await asyncio.Future()  # 永久运行


@app.on_event("startup")
async def startup_event():
    """FastAPI 启动时同时拉起 WebSocket 服务器。"""
    global websocket_server_task
    validate_tokens(API_TOKEN, DEVICE_TOKEN)
    websocket_server_task = asyncio.create_task(start_websocket_server())
    logger.info("=" * 50)
    logger.info("🚀 SparkBot 神经中枢已启动！")
    logger.info(f"📡 QClaw 技能接口: http://127.0.0.1:{SERVER_PORT}")
    logger.info(f"📡 自动文档:       http://127.0.0.1:{SERVER_PORT}/docs")
    logger.info(f"🔌 硬件 WebSocket: ws://0.0.0.0:{WEBSOCKET_PORT}")
    logger.info("=" * 50)


@app.on_event("shutdown")
async def shutdown_event():
    """FastAPI 关闭时再主动取消 WebSocket 服务器任务。"""
    global websocket_server_task
    if websocket_server_task is not None:
        websocket_server_task.cancel()
        try:
            await websocket_server_task
        except asyncio.CancelledError:
            pass
        websocket_server_task = None


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
    )

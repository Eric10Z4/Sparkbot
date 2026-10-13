"""
SparkBot — 视觉感知模块
Member C 交付文件：services/visual.py

对外接口：
    face_recognize(image_bytes: bytes) -> dict
    register_face(name: str, image_bytes: bytes) -> dict
    remove_face(name: str) -> dict
    list_faces() -> list
    detect_anomaly(image_bytes: bytes) -> dict
    detect_objects(image_bytes: bytes) -> dict

注意事项：
    - 所有函数处理无效输入时返回安全默认值，不抛异常
    - 不调用 cv2.imshow（服务器无显示器）
    - 底库路径使用相对路径，不硬编码
    - 大模型文件（yolov8n.pt）不纳入 git，需告知 A 同学下载地址
"""
from __future__ import annotations

import os
import pickle
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _resolve_project_path(env_name: str, default: str | Path) -> Path:
    path = Path(os.environ.get(env_name, default))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


MODEL_DIR = _resolve_project_path("SPARKBOT_MODEL_DIR", PROJECT_ROOT / "models")
YOLO_MODEL_PATH = _resolve_project_path("YOLO_MODEL_PATH", MODEL_DIR / "yolov8n.pt")

# ============================================================
# COCO 80 类别 中英文对照表（用于 YOLO 结果中文化输出）
# ============================================================
COCO_CLASSES_ZH: dict[str, str] = {
    "person": "人",
    "bicycle": "自行车",
    "car": "轿车",
    "motorcycle": "摩托车",
    "airplane": "飞机",
    "bus": "公交车",
    "train": "火车",
    "truck": "卡车",
    "boat": "船",
    "traffic light": "交通灯",
    "fire hydrant": "消防栓",
    "stop sign": "停止标志",
    "parking meter": "停车计费表",
    "bench": "长椅",
    "bird": "鸟",
    "cat": "猫",
    "dog": "狗",
    "horse": "马",
    "sheep": "羊",
    "cow": "牛",
    "elephant": "大象",
    "bear": "熊",
    "zebra": "斑马",
    "giraffe": "长颈鹿",
    "backpack": "背包",
    "umbrella": "雨伞",
    "handbag": "手提包",
    "tie": "领带",
    "suitcase": "行李箱",
    "frisbee": "飞盘",
    "skis": "滑雪板",
    "snowboard": "单板滑雪",
    "sports ball": "运动球",
    "kite": "风筝",
    "baseball bat": "棒球棒",
    "baseball glove": "棒球手套",
    "skateboard": "滑板",
    "surfboard": "冲浪板",
    "tennis racket": "网球拍",
    "bottle": "瓶子",
    "wine glass": "酒杯",
    "cup": "杯子",
    "fork": "叉子",
    "knife": "刀",
    "spoon": "勺子",
    "bowl": "碗",
    "banana": "香蕉",
    "apple": "苹果",
    "sandwich": "三明治",
    "orange": "橙子",
    "broccoli": "西蓝花",
    "carrot": "胡萝卜",
    "hot dog": "热狗",
    "pizza": "披萨",
    "donut": "甜甜圈",
    "cake": "蛋糕",
    "chair": "椅子",
    "couch": "沙发",
    "potted plant": "盆栽",
    "bed": "床",
    "dining table": "餐桌",
    "toilet": "马桶",
    "tv": "电视",
    "laptop": "笔记本电脑",
    "mouse": "鼠标",
    "remote": "遥控器",
    "keyboard": "键盘",
    "cell phone": "手机",
    "microwave": "微波炉",
    "oven": "烤箱",
    "toaster": "烤面包机",
    "sink": "水槽",
    "refrigerator": "冰箱",
    "book": "书",
    "clock": "时钟",
    "vase": "花瓶",
    "scissors": "剪刀",
    "teddy bear": "玩具熊",
    "hair drier": "吹风机",
    "toothbrush": "牙刷",
}


def _en_to_zh(label: str) -> str:
    """将 COCO 英文类别名翻译为中文，未收录的保持原样。"""
    return COCO_CLASSES_ZH.get(label.lower(), label)


# ============================================================
# 可配置阈值（通过环境变量调节，方便后续适配不同环境）
# ============================================================
# 人脸相似度阈值：余弦相似度 >= 此值才认为"认出"（0~1，值越大越严格）
FACE_SIMILARITY_THRESHOLD = float(os.environ.get("FACE_SIMILARITY_THRESHOLD", "0.45"))

# YOLO 物体检测置信度阈值（0~1）
YOLO_CONF_THRESHOLD = float(os.environ.get("YOLO_CONF_THRESHOLD", "0.5"))

# 帧差异常检测：运动区域面积阈值（像素数，值越大越不灵敏）
ANOMALY_AREA_THRESHOLD = int(os.environ.get("ANOMALY_AREA_THRESHOLD", "2000"))

# ============================================================
# 模型初始化
# ============================================================
_INSIGHTFACE_READY = False
_face_app = None

try:
    from insightface.app import FaceAnalysis

    _face_app = FaceAnalysis(
        name="buffalo_s",
        providers=["CPUExecutionProvider"],
    )
    _face_app.prepare(ctx_id=0, det_size=(320, 320))
    _INSIGHTFACE_READY = True
except Exception:
    print("[visual] InsightFace 未就绪，人脸识别将不可用。请确保已安装 insightface 和 onnxruntime。")

# YOLO 对象检测
_YOLO_READY = False
_yolo_model = None

try:
    from ultralytics import YOLO

    model_source = YOLO_MODEL_PATH if YOLO_MODEL_PATH.exists() else "yolov8n.pt"
    _yolo_model = YOLO(str(model_source), verbose=False)
    _YOLO_READY = True
except Exception:
    print("[visual] YOLO 本地模型未就绪，将使用远程 API（如已配置）。")

# 远程对象检测 API 配置
_VISION_API_URL = os.environ.get("VISION_API_URL", "")
_VISION_API_KEY = os.environ.get("VISION_API_KEY", "")

# ============================================================
# 底库路径配置（独立文件存储，每人一个 .pkl + .jpg）
# ============================================================
DB_DIR = Path(__file__).resolve().parent / "face_db"
DB_DIR.mkdir(exist_ok=True)


def _feat_path(name: str) -> Path:
    """返回指定人名的特征文件路径。"""
    return DB_DIR / f"{name}.pkl"


def _img_path(name: str) -> Path:
    """返回指定人名的人脸图像路径（用于预览）。"""
    return DB_DIR / f"{name}.jpg"


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


# ============================================================
# 人脸识别
# ============================================================
def face_recognize(image_bytes: bytes) -> dict:
    """
    识别图片中的人脸，返回识别结果。

    参数:
        image_bytes (bytes): JPEG 格式的图片二进制数据

    返回:
        dict: {
            "detected": True,           # 是否检测到人脸
            "name": "张三",              # 识别出的人名（底库中有的话）
            "confidence": 0.92,          # 最大脸置信度 0~1
            "count": 1,                  # 画面中人脸数量
            "all_faces": [               # 画面中所有人脸的识别结果（高级字段）
                {
                    "name": "张三",
                    "confidence": 0.92,
                    "bbox": [x1, y1, x2, y2],   # 人脸边界框（像素）
                },
            ],
        }
    """
    try:
        if not image_bytes:
            return {"detected": False, "name": "", "confidence": 0.0, "count": 0, "all_faces": []}

        if not _INSIGHTFACE_READY:
            return {"detected": False, "name": "", "confidence": 0.0, "count": 0, "all_faces": []}

        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"detected": False, "name": "", "confidence": 0.0, "count": 0, "all_faces": []}

        faces = _face_app.get(img)
        if not faces:
            return {"detected": False, "name": "", "confidence": 0.0, "count": 0, "all_faces": []}

        # 加载底库（逐个读取独立文件）
        db: dict[str, np.ndarray] = {}
        for feat_file in DB_DIR.glob("*.pkl"):
            try:
                with open(feat_file, "rb") as f:
                    db[feat_file.stem] = pickle.load(f)
            except Exception:
                pass  # 损坏文件跳过，不影响其他人

        # 对每张人脸做识别
        all_faces_result: list[dict] = []
        for face in faces:
            bbox = [int(v) for v in face.bbox.tolist()]
            feat = face.embedding

            best_name = "陌生人"
            best_sim = 0.0
            for name, saved_feat in db.items():
                sim = _cosine_sim(feat, saved_feat)
                if sim > best_sim:
                    best_sim = sim
                    best_name = name

            if best_sim >= FACE_SIMILARITY_THRESHOLD:
                all_faces_result.append(
                    {"name": best_name, "confidence": round(best_sim, 2), "bbox": bbox}
                )
            else:
                all_faces_result.append(
                    {"name": "陌生人", "confidence": 0.0, "bbox": bbox}
                )

        # 主结果：取面积最大的脸（确保向下兼容）
        faces_sorted = sorted(
            zip(faces, all_faces_result),
            key=lambda x: (x[0].bbox[2] - x[0].bbox[0]) * (x[0].bbox[3] - x[0].bbox[1]),
            reverse=True,
        )
        primary = faces_sorted[0][1]

        return {
            "detected": True,
            "name": primary["name"],
            "confidence": primary["confidence"],
            "count": len(faces),
            "all_faces": all_faces_result,
        }

    except Exception:
        return {"detected": False, "name": "", "confidence": 0.0, "count": 0, "all_faces": []}


# ============================================================
# 人脸底库管理（独立文件存储）
# ============================================================
def register_face(name: str, image_bytes: bytes) -> dict:
    """
    注册一张新人脸到底库。同时保存裁切后的人脸 JPG 图像（用于预览）。

    参数:
        name (str): 这个人的名字，如 "张三"
        image_bytes (bytes): 包含这个人正脸的 JPEG 图片

    返回:
        dict: {"success": True, "msg": "张三 注册成功，底库现有 3 人"}
    """
    try:
        if not image_bytes:
            return {"success": False, "msg": "图片无效"}

        if not _INSIGHTFACE_READY:
            return {"success": False, "msg": "人脸识别服务未就绪"}

        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"success": False, "msg": "图片无效，无法解码"}

        faces = _face_app.get(img)
        if not faces:
            return {"success": False, "msg": "图片中未检测到人脸"}

        # 取面积最大的人脸
        faces = sorted(
            faces,
            key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]),
            reverse=True,
        )
        face = faces[0]

        # 保存 512 维特征向量
        with open(_feat_path(name), "wb") as f:
            pickle.dump(face.embedding, f)

        # 裁切并保存人脸 JPG 图像（用于后台预览）
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        # 稍微扩边，让截图好看一点
        padding = 20
        h, w = img.shape[:2]
        x1c = max(0, x1 - padding)
        y1c = max(0, y1 - padding)
        x2c = min(w, x2 + padding)
        y2c = min(h, y2 + padding)
        face_crop = img[y1c:y2c, x1c:x2c]
        cv2.imwrite(str(_img_path(name)), face_crop)

        # 统计当前底库人数
        total = len(list(DB_DIR.glob("*.pkl")))
        return {"success": True, "msg": f"{name} 注册成功，底库现有 {total} 人"}

    except Exception as e:
        return {"success": False, "msg": f"注册异常: {str(e)}"}


def remove_face(name: str) -> dict:
    """
    从底库中删除一个人（同时删除特征文件和人脸 JPG）。

    返回:
        dict: {"success": True, "msg": "已删除 张三"}
    """
    try:
        feat = _feat_path(name)
        img = _img_path(name)

        if not feat.exists():
            return {"success": False, "msg": f"底库中未找到 {name}"}

        feat.unlink()
        if img.exists():
            img.unlink()

        return {"success": True, "msg": f"已删除 {name}"}

    except Exception as e:
        return {"success": False, "msg": str(e)}


def list_faces() -> list:
    """
    列出底库中所有已注册的人名。

    返回:
        list: ["张三", "李四", "王五"]
    """
    return [p.stem for p in sorted(DB_DIR.glob("*.pkl"))]


# ============================================================
# 异常检测（帧差法 + 运动方向感知 + 抗抖动）
# ============================================================
_last_frame_gray = None
_last_frame_color = None
_anomaly_hit_count = 0   # 连续触发次数（用于抗单帧噪点误报）
_ANOMALY_MIN_HITS = 1    # 至少连续触发 N 帧才算真正异常（默认 1 不改变原行为，可调为 2）


def detect_anomaly(image_bytes: bytes) -> dict:
    """
    对比前后画面，判断是否有异常（有人靠近、东西被动过等）。

    说明:
        这个函数会被 A 同学定时调用（约每 3~5 秒一次）。
        函数内部维护"上一帧"状态来做对比。

    参数:
        image_bytes (bytes): JPEG 格式的图片二进制数据

    返回:
        dict: {
            "is_anomaly": True,
            "anomaly_type": "有人靠近",
            "description": "检测到一个人从左侧进入画面",
            "severity": "high",
        }
    """
    global _last_frame_gray, _last_frame_color, _anomaly_hit_count

    _no_anomaly = {
        "is_anomaly": False,
        "anomaly_type": "",
        "description": "画面无变化",
        "severity": "low",
    }

    try:
        if not image_bytes:
            return {**_no_anomaly, "description": "无效图片"}

        nparr = np.frombuffer(image_bytes, np.uint8)
        img_color = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img_color is None:
            return {**_no_anomaly, "description": "无效图片"}

        img_gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
        img_gray = cv2.GaussianBlur(img_gray, (21, 21), 0)

        # 第一帧，初始化
        if _last_frame_gray is None:
            _last_frame_gray = img_gray
            _last_frame_color = img_color
            _anomaly_hit_count = 0
            return {**_no_anomaly, "description": "监控初始化中"}

        # 尺寸对齐
        if _last_frame_gray.shape != img_gray.shape:
            img_gray = cv2.resize(
                img_gray,
                (_last_frame_gray.shape[1], _last_frame_gray.shape[0]),
            )

        # 帧差计算
        frame_delta = cv2.absdiff(_last_frame_gray, img_gray)
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        contours_result = cv2.findContours(
            thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = contours_result[0] if len(contours_result) == 2 else contours_result[1]

        h, w = img_gray.shape
        center_x, center_y = w // 2, h // 2

        significant_contours = [c for c in contours if cv2.contourArea(c) > ANOMALY_AREA_THRESHOLD]

        _last_frame_gray = img_gray
        _last_frame_color = img_color

        if not significant_contours:
            _anomaly_hit_count = 0
            return _no_anomaly

        # 运动区域分析
        total_motion_area = sum(cv2.contourArea(c) for c in significant_contours)
        total_pixels = h * w
        motion_ratio = total_motion_area / total_pixels

        all_points = np.vstack(significant_contours)
        motion_cx = int(np.mean(all_points[:, 0, 0]))
        motion_cy = int(np.mean(all_points[:, 0, 1]))

        dist_to_center = np.sqrt((motion_cx - center_x) ** 2 + (motion_cy - center_y) ** 2)
        max_dist = np.sqrt(center_x**2 + center_y**2)
        center_proximity = 1.0 - (dist_to_center / (max_dist + 1e-6))  # 0=边缘, 1=正中心

        # 分类异常类型
        if motion_ratio > 0.3:
            anomaly_type = "画面剧烈变化"
            severity = "high"
            description = "画面大面积变动，可能有物体翻倒或人员闯入"
        elif center_proximity > 0.5 and motion_ratio > 0.05:
            anomaly_type = "有人靠近"
            severity = "high"
            description = "检测到有人从画面中央靠近"
        elif len(significant_contours) >= 3:
            anomaly_type = "多处异动"
            severity = "medium"
            description = "检测到画面多处有物体移动"
        elif center_proximity > 0.3:
            anomaly_type = "有人靠近"
            severity = "medium"
            description = "检测到画面中央区域有物体移动"
        else:
            anomaly_type = "画面异动"
            severity = "low"
            description = "检测到画面边缘区域有微小变化"

        # 抗抖动：只有连续触发 _ANOMALY_MIN_HITS 次才上报
        _anomaly_hit_count += 1
        if _anomaly_hit_count >= _ANOMALY_MIN_HITS:
            return {
                "is_anomaly": True,
                "anomaly_type": anomaly_type,
                "description": description,
                "severity": severity,
            }
        else:
            # 第一帧触发，暂不上报，等下一帧确认
            return _no_anomaly

    except Exception:
        return {**_no_anomaly, "description": "检测异常"}


# ============================================================
# 对象检测（远程 API 优先，本地 YOLO 回退）
# ============================================================
def _detect_objects_remote(image_bytes: bytes) -> dict:
    """通过远程 API 做物体检测（格式与本地 YOLO 保持一致）。"""
    import base64
    import json
    import urllib.request

    try:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = json.dumps({"image": encoded}).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if _VISION_API_KEY:
            headers["Authorization"] = f"Bearer {_VISION_API_KEY}"

        req = urllib.request.Request(
            _VISION_API_URL,
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        raw_objects = result.get("objects", [])
        if not raw_objects:
            return {"objects": [], "count": 0, "description": "桌面上没有识别到物体"}

        # 远程 API 结果同样中文化
        objects = []
        zh_labels_seen: set[str] = set()
        for obj in raw_objects:
            en_label = obj.get("label", "未知")
            zh_label = _en_to_zh(en_label)
            conf = round(float(obj.get("confidence", 0.0)), 2)
            objects.append({"label": zh_label, "confidence": conf})
            zh_labels_seen.add(zh_label)

        return {
            "objects": objects,
            "count": len(objects),
            "description": f"桌面上有 {'、'.join(zh_labels_seen)}",
        }
    except Exception as e:
        return {"objects": [], "count": 0, "description": f"远程识别失败: {str(e)}"}


def _detect_objects_local(image_bytes: bytes) -> dict:
    """本地 YOLO 回退，使用中文类别名输出。"""
    try:
        if not _YOLO_READY:
            return {
                "objects": [],
                "count": 0,
                "description": f"物体识别未就绪，请设置 VISION_API_URL、安装 ultralytics，或检查模型路径: {YOLO_MODEL_PATH}",
            }

        img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return {"objects": [], "count": 0, "description": "无效图片"}

        results = _yolo_model(img, verbose=False)[0]
        objects: list[dict] = []
        zh_labels_seen: set[str] = set()

        for box in results.boxes:
            conf = float(box.conf[0])
            if conf > YOLO_CONF_THRESHOLD:
                cls_id = int(box.cls[0])
                en_label = _yolo_model.names[cls_id]
                zh_label = _en_to_zh(en_label)
                objects.append({"label": zh_label, "confidence": round(conf, 2)})
                zh_labels_seen.add(zh_label)

        if not objects:
            return {"objects": [], "count": 0, "description": "桌面上没有识别到物体"}

        return {
            "objects": objects,
            "count": len(objects),
            "description": f"桌面上有 {'、'.join(zh_labels_seen)}",
        }
    except Exception:
        return {"objects": [], "count": 0, "description": "识别异常"}


def detect_objects(image_bytes: bytes) -> dict:
    """
    识别画面中的物体（使用 YOLO 或类似模型）。

    参数:
        image_bytes (bytes): JPEG 格式的图片二进制数据

    返回:
        dict: {
            "objects": [
                {"label": "杯子", "confidence": 0.95},
                {"label": "手机", "confidence": 0.88},
            ],
            "count": 2,
            "description": "桌面上有 杯子、手机",
        }
    """
    try:
        if not image_bytes:
            return {"objects": [], "count": 0, "description": "无效图片"}

        if _VISION_API_URL:
            return _detect_objects_remote(image_bytes)
        else:
            return _detect_objects_local(image_bytes)
    except Exception:
        return {"objects": [], "count": 0, "description": "识别异常"}


# ============================================================
# 导出列表
# ============================================================
__all__ = [
    "COCO_CLASSES_ZH",
    "FACE_SIMILARITY_THRESHOLD",
    "YOLO_CONF_THRESHOLD",
    "ANOMALY_AREA_THRESHOLD",
    "YOLO_MODEL_PATH",
    "face_recognize",
    "register_face",
    "remove_face",
    "list_faces",
    "detect_anomaly",
    "detect_objects",
]

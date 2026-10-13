# 🤖 SparkBot — 视觉感知与监控引擎 (Visual Perception Module)

> **项目一句话定位**：给 300 块的桌面机器人装上“超级眼睛”！负责给机器人的大脑（同学 A 负责）实时提供人脸识别、全屋异常看护以及桌面物体的中文智能感知。

---

## 📂 项目目录结构 (Directory Structure)

本模块已按照 Python 工业级最佳实践进行了重构与归整，目录结构清晰、逻辑分明：

```
SparkBot-Visual/
├── services/                   # 核心业务服务包
│   ├── face_db/                # 人脸特征及照片底库目录（自动生成）
│   │   ├── {name}.pkl          # 注册用户的 512 维人脸特征向量
│   │   └── {name}.jpg          # 注册用户的原始裁切正脸照片（供后台展示）
│   ├── __init__.py             # Python 包初始化标识
│   └── visual.py               # 视觉引擎核心逻辑（人脸识别/异常检测/物体识别）
├── tests/                      # 自动化测试模块
│   ├── test_images/            # 测试专用图片样本库
│   │   ├── 人脸照.jpg           # 测试注册正脸
│   │   ├── b026fdc87504ae2055980a8957c161a9.jpg  # 测试复杂运动场景
│   │   └── 0ca02de071430c10dc580a9e5cbc6124.jpg  # 测试人脸+物体场景
│   └── test_visual.py          # 视觉模块一键自动化自测脚本
├── yolov8n.pt                  # 本地 YOLOv8 目标检测权重模型（不纳入 Git 追踪）
├── requirements_visual.txt     # 视觉感知模块独立依赖清单
├── 团队分工(3).md               # 团队原始分工及接口约定文档
└── README.md                   # 本说明书
```

---

## 🚀 核心三大功能 (Key Features)

### 1. 人脸识别与库管理 (Face Identification & Registry)
* **独立文件存储**：彻底弃用单一 `pkl` 大文件，采用 `{姓名}.pkl` 特征和 `{姓名}.jpg` 正脸截图的**双独立文件**存储。单人增删无任何并发锁冲突风险，且原生支持后台展示“已注册人脸墙”。
* **多目标感知**：在向下兼容返回主目标（最大人脸）的同时，新增 `all_faces` 高级列表。支持实时输出画面中**所有**被检测到的人脸姓名、余弦相似度及像素坐标。

### 2. 空间异常监控引擎 (Spatial Anomaly Monitor)
* **差分运动感知**：基于高斯模糊去噪与双帧差分技术，实时计算运动物体轮廓及变化比率。
* **多维度态势评估**：深度融合**运动像素比率**、**区域质心**与**画面中心逼近度**，智能分类为 `画面剧烈变化`、`有人靠近`、`多处异动`、`画面异动` 等多种事件类型与严重等级。
* **抖动过滤**：内置状态机抗噪点机制，平滑单帧摄像抖动带来的误报。

### 3. 智能物体中文感知 (YOLOv8 Chinese Object Detection)
* **本地与远程双轨制**：本地优先尝试加载轻量化 `yolov8n.pt` 进行推理，无硬核显卡时可自动无缝回退至配置的远程云端 API 运行。
* **全中文化映射**：内置了完整的 80 类 COCO 常用数据集**中英文对照映射字典**。识别结果会转换为生动、自然的纯中文语句（例如 `"桌面上有 人、手机、杯子"`，而非英文混合拼接），体验极佳。

---

## 🔧 环境准备与一键部署 (Quick Start)

### 1. 创建虚拟环境 (建议)
在项目根目录下打开命令行或 PowerShell：
```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 2. 安装依赖包
通过提供的视觉专属依赖清单一键完成安装：
```powershell
pip install -r requirements_visual.txt
```
> *注：`insightface` 本地编译需要 C++ 构建工具支持，请确保已安装 Visual Studio Build Tools 且包含 C++ 开发工作负载。*

### 3. 获取权重模型
1. **YOLO 权重**：首次运行代码时，YOLO 库会自动下载 `yolov8n.pt` 到根目录。你也可以手动下载 [YOLOv8n 权重](https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt) 放置在项目根目录下。
2. **人脸识别权重**：首次调用人脸接口时，`insightface` 会自动从 ModelZoo 下载轻量级 `buffalo_s` 模型包到用户家目录中的 `.insightface/models/` 目录下（约 50MB），全自动无需人工干预。

---

## 🔗 协作接口约定 (API Specifications)

视觉模块文件放置在 `services/visual.py` 中。同学 A 可在主服务中通过 `from services.visual import ...` 导入调用。

### 🔹 人脸识别 `face_recognize(image_bytes: bytes) -> dict`
* **参数**：
  * `image_bytes`: JPEG 格式图片二进制字节流
* **返回值字典**：
```json
{
  "detected": true,
  "name": "张三",
  "confidence": 0.92,
  "count": 1,
  "all_faces": [
    {
      "name": "张三",
      "confidence": 0.92,
      "bbox": [120, 85, 230, 240]
    }
  ]
}
```

### 🔹 人脸底库管理
* **人脸注册**：`register_face(name: str, image_bytes: bytes) -> dict`
  * 提取图片中最大正脸计算特征，在 `services/face_db/` 写入 `{name}.pkl` 和 `{name}.jpg`。
* **人脸删除**：`remove_face(name: str) -> dict`
  * 从底库目录中同步移除指定名字的两个存储文件。
* **已注册列表**：`list_faces() -> list[str]`
  * 返回已注册的所有人名列表（如 `["张三", "李四"]`）。

### 🔹 异常监控检测 `detect_anomaly(image_bytes: bytes) -> dict`
* **参数**：
  * `image_bytes`: 抓拍的 JPEG 二进制图片。建议由 WebSocket 服务端（同学 A 负责）每隔 3~5 秒定时调用喂入。
* **返回值字典**：
```json
{
  "is_anomaly": true,
  "anomaly_type": "有人靠近",
  "description": "检测到有人从画面中央靠近",
  "severity": "high"
}
```

### 🔹 物体感知 `detect_objects(image_bytes: bytes) -> dict`
* **参数**：
  * `image_bytes`: 桌面摄像头的 JPEG 二进制图片。
* **返回值字典**：
```json
{
  "objects": [
    {"label": "人", "confidence": 0.95},
    {"label": "手机", "confidence": 0.88}
  ],
  "count": 2,
  "description": "桌面上有 人、手机"
}
```

---

## 🧪 自动化单元自测 (Testing)

为保证视觉系统交接时的“零故障与高稳定性”，提供了全面的集成自测脚本。只需在项目根目录下直接运行：
```powershell
.venv\Scripts\python.exe tests/test_visual.py
```

### 自测覆盖项说明：
1. **自动路径寻址**：无需在代码中写死物理路径，自测脚本会基于包根目录动态寻址 `tests/test_images/` 目录中的样照进行检测。
2. **注册完整性校验**：检测注册动作是否正确创建了 `.pkl` 以及裁切后的 `.jpg` 预览人脸图。
3. **中文格式严谨性**：断言 YOLO 识别结果是否已被全面汉化，一旦含有 `person`/`tie` 等原 COCO 英文，测试直接报错熔断。
4. **健壮性压力测试**：输入空字节 `b""` 及损坏的字符串垃圾，测试三个主接口是否能 100% 捕获异常，并安全返回预设的默认字典。
5. **彻底清理**：测试完毕后自动将注册的测试用户及其文件清除，保持底库目录的绝对纯净。

## 测试图片与隐私

公开仓库不分发个人照片、裁剪人脸、场景派生图和人脸识别记录。需要测试时，将有授权的图片放在本地 `tests/test_images/`，参考人脸命名为 `人脸照.jpg`；比较图放在 `tests/visual_assets/face_*`。缺少参考图时，人脸素材测试跳过。
运行生成的场景图片、报告和人脸数据库已加入忽略规则，提交前仍需核对变更。

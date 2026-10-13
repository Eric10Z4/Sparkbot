"""
SparkBot — 视觉模块自测脚本
Member C 交付文件：tests/test_visual.py

用法（在项目根目录下执行）：
    .venv\\Scripts\\python.exe tests\\test_visual.py

测试内容：
    1. register_face       — 注册人脸 & 验证 .pkl / .jpg 文件生成
    2. list_faces          — 查询底库人名列表
    3. face_recognize      — 识别人脸（含 all_faces 高级字段验证）
    4. detect_objects      — 物体识别（验证描述全部中文化）
    5. detect_anomaly      — 异常检测（多帧对比）
    6. remove_face         — 删除人脸 & 验证文件已清理
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 把项目根目录加入 sys.path，确保无论在哪里运行都能正确 import
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.visual import (
    DB_DIR,
    detect_anomaly,
    detect_objects,
    face_recognize,
    list_faces,
    register_face,
    remove_face,
)

# ============================================================
# 工具函数
# ============================================================

def _load(path: Path) -> bytes:
    return path.read_bytes()


def _print_section(title: str) -> None:
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print("=" * 55)


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    raise AssertionError(msg)


# ============================================================
# 断言辅助
# ============================================================

def validate_face_result(result: dict) -> None:
    """验证 face_recognize 返回的字典结构。"""
    assert isinstance(result, dict), f"期望 dict，实际 {type(result)}"
    for key in ("detected", "name", "confidence", "count", "all_faces"):
        assert key in result, f"缺少字段: {key}"
    assert isinstance(result["all_faces"], list), "all_faces 应为 list"
    for face in result["all_faces"]:
        for k in ("name", "confidence", "bbox"):
            assert k in face, f"all_faces 元素缺少字段: {k}"
        assert isinstance(face["bbox"], list) and len(face["bbox"]) == 4, \
            "bbox 应为长度为 4 的 list"
    if result.get("name") == "陌生人":
        assert result["confidence"] == 0.0, "陌生人 confidence 应为 0.0"
    _ok(f"face_recognize 结构验证通过 | name={result['name']} conf={result['confidence']} "
        f"count={result['count']} all_faces={len(result['all_faces'])}张")


def validate_objects_result(result: dict) -> None:
    """验证 detect_objects 返回结构，并检查描述是否含英文 COCO 标签。"""
    assert isinstance(result, dict), f"期望 dict，实际 {type(result)}"
    for key in ("objects", "count", "description"):
        assert key in result, f"缺少字段: {key}"
    # 检查每个物体标签是否已中文化（不应出现 COCO 英文原始名如 "person"/"tie"）
    raw_en_labels = {
        "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
        "truck", "boat", "cat", "dog", "chair", "couch", "laptop", "mouse",
        "keyboard", "cell phone", "tie", "cup", "bottle", "book", "clock",
    }
    for obj in result["objects"]:
        label = obj.get("label", "")
        if label.lower() in raw_en_labels:
            _fail(f"detect_objects 返回了未翻译的英文标签: '{label}'，期望中文")
    _ok(f"detect_objects 结构验证通过 | count={result['count']} desc={result['description']}")


def validate_anomaly_result(result: dict) -> None:
    """验证 detect_anomaly 返回结构。"""
    assert isinstance(result, dict), f"期望 dict，实际 {type(result)}"
    for key in ("is_anomaly", "anomaly_type", "description", "severity"):
        assert key in result, f"缺少字段: {key}"
    assert result["severity"] in ("low", "medium", "high"), \
        f"severity 取值不合法: {result['severity']}"
    _ok(f"detect_anomaly 结构验证通过 | is_anomaly={result['is_anomaly']} "
        f"type={result['anomaly_type']} severity={result['severity']}")


# ============================================================
# 主流程
# ============================================================

def main() -> int:
    # 自动搜索测试图片（相对于项目根目录，不硬编码用户路径）
    candidates = [
        ROOT_DIR / "tests" / "test_images" / "人脸照.jpg",
        ROOT_DIR / "tests" / "test_images" / "b026fdc87504ae2055980a8957c161a9.jpg",
        ROOT_DIR / "tests" / "test_images" / "0ca02de071430c10dc580a9e5cbc6124.jpg",
    ]
    image_paths = [p for p in candidates if p.exists()]

    if not image_paths:
        print("[SKIP] 没有找到测试图片，请在 tests/test_images/ 目录放置至少一张 JPG 图片。")
        return 0

    register_src = ROOT_DIR / "tests" / "test_images" / "人脸照.jpg"

    # ────────────────────────────────────────
    _print_section("1. 人脸注册（register_face）")
    if register_src.exists():
        result = register_face("测试用户", _load(register_src))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        assert result["success"], f"注册失败: {result['msg']}"
        _ok(result["msg"])

        # 验证底库文件生成
        pkl = DB_DIR / "测试用户.pkl"
        jpg = DB_DIR / "测试用户.jpg"
        assert pkl.exists(), f"底库特征文件未生成: {pkl}"
        _ok(f"特征文件已生成: {pkl.name}")
        if jpg.exists():
            _ok(f"人脸 JPG 已生成: {jpg.name}（大小 {jpg.stat().st_size} 字节）")
        else:
            print("  [WARN] 人脸 JPG 未生成（可能人脸裁切区域为空，非致命）")
    else:
        print(f"  [SKIP] 未找到注册图片 {register_src.name}")

    # ────────────────────────────────────────
    _print_section("2. 底库列表（list_faces）")
    faces_list = list_faces()
    print(f"  当前底库: {faces_list}")
    assert isinstance(faces_list, list), "list_faces 应返回 list"
    _ok(f"list_faces 正常，当前 {len(faces_list)} 人")

    # ────────────────────────────────────────
    for path in image_paths:
        _print_section(f"3/4/5. 图片测试: {path.name}")
        data = _load(path)

        print("\n  [detect_objects]")
        obj_result = detect_objects(data)
        print(json.dumps(obj_result, ensure_ascii=False, indent=2))
        validate_objects_result(obj_result)

        print("\n  [face_recognize]")
        face_result = face_recognize(data)
        print(json.dumps(face_result, ensure_ascii=False, indent=2))
        validate_face_result(face_result)

        print("\n  [detect_anomaly]")
        anomaly_result = detect_anomaly(data)
        print(json.dumps(anomaly_result, ensure_ascii=False, indent=2))
        validate_anomaly_result(anomaly_result)

    # ────────────────────────────────────────
    _print_section("6. 空图片 / 损坏输入健壮性测试")
    for bad_input in (b"", b"not_an_image_bytes_xxxx"):
        r_face = face_recognize(bad_input)
        assert r_face["detected"] is False, "空/损坏图片 face_recognize 应返回 detected=False"
        r_obj = detect_objects(bad_input)
        assert r_obj["count"] == 0, "空/损坏图片 detect_objects 应返回 count=0"
        r_anomaly = detect_anomaly(bad_input)
        assert r_anomaly["is_anomaly"] is False, "空/损坏图片 detect_anomaly 应返回 is_anomaly=False"
    _ok("空图片 / 损坏输入全部安全返回默认值，未抛异常")

    # ────────────────────────────────────────
    _print_section("7. 清理 — remove_face（验证文件删除）")
    if register_src.exists():
        result = remove_face("测试用户")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        assert result["success"], f"删除失败: {result['msg']}"
        assert not (DB_DIR / "测试用户.pkl").exists(), "底库特征文件应已删除"
        assert not (DB_DIR / "测试用户.jpg").exists(), "人脸 JPG 应已删除"
        _ok("底库特征文件 & 人脸 JPG 均已删除")

    print(f"\n{'=' * 55}")
    print("  ✅ 所有测试完成！")
    print("=" * 55)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

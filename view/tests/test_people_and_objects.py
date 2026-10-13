"""
Integrated visual test for the standalone view package.

All face and object assets are stored in one flat directory:
tests/visual_assets
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.visual import (
    FACE_SIMILARITY_THRESHOLD,
    detect_objects,
    face_recognize,
    register_face,
    remove_face,
)

ASSET_DIR = ROOT_DIR / "tests" / "visual_assets"
ORIGINAL_FACE = ROOT_DIR / "tests" / "test_images" / "人脸照.jpg"
REPORT_PATH = ROOT_DIR / "CV_ASSET_TEST_REPORT.md"
REFERENCE_NAME = "原图人物"

OBJECT_SOURCES = {
    "object_raw_desk_laptop_cup_phone.jpg": "PublicDomainPictures: Notebook, Work, Coffee,desk, Iphone",
    "object_raw_alarm_clock.jpg": "PublicDomainPictures: Alarm Clock",
    "object_raw_still_life_bottle_toy_car.jpg": "Unsplash: still life with bottle and toy car",
}


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def run_face_match_test() -> list[dict]:
    if not ORIGINAL_FACE.exists():
        print("[SKIP] 请在本地准备有授权的人脸测试图片；公开仓库不包含个人照片。")
        return []

    register_result = register_face(REFERENCE_NAME, _read_bytes(ORIGINAL_FACE))
    if not register_result.get("success"):
        raise RuntimeError(f"failed to register original face: {register_result}")

    rows: list[dict] = []
    try:
        for path in sorted(ASSET_DIR.glob("face_*.*")):
            result = face_recognize(_read_bytes(path))
            matched = (
                bool(result.get("detected"))
                and result.get("name") == REFERENCE_NAME
                and float(result.get("confidence", 0.0)) >= FACE_SIMILARITY_THRESHOLD
            )
            rows.append(
                {
                    "file": path.name,
                    "detected": bool(result.get("detected")),
                    "recognized_name": result.get("name", ""),
                    "confidence": float(result.get("confidence", 0.0)),
                    "matched_original": matched,
                    "face_count": int(result.get("count", 0)),
                }
            )
    finally:
        remove_face(REFERENCE_NAME)

    return rows


def run_object_test() -> list[dict]:
    paths = sorted(ASSET_DIR.glob("object_raw_*.jpg")) + sorted(ASSET_DIR.glob("object_gen_*.jpg"))

    rows: list[dict] = []
    for path in paths:
        result = detect_objects(_read_bytes(path))
        labels = [obj.get("label", "") for obj in result.get("objects", [])]
        rows.append(
            {
                "file": path.relative_to(ROOT_DIR).as_posix(),
                "count": int(result.get("count", 0)),
                "labels": labels,
                "description": result.get("description", ""),
            }
        )
        assert "objects" in result and "description" in result

    return rows


def _format_bool(value: bool) -> str:
    return "是" if value else "否"


def write_report(face_rows: list[dict], object_rows: list[dict]) -> None:
    matched = [row for row in face_rows if row["matched_original"]]
    best = max(face_rows, key=lambda row: row["confidence"], default=None)
    object_raw_count = len(list(ASSET_DIR.glob("object_raw_*.jpg")))
    object_gen_count = len(list(ASSET_DIR.glob("object_gen_*.jpg")))
    scene_gen_count = len(list(ASSET_DIR.glob("scene_gen_*.jpg")))

    lines = [
        "# view 计算机视觉素材整合测试报告",
        "",
        "日期：2026-06-14",
        "",
        "## 素材位置",
        "",
        f"- 统一素材目录：`{ASSET_DIR.relative_to(ROOT_DIR).as_posix()}`",
        f"- 人脸图：{len(face_rows)} 张，文件名前缀 `face_`",
        f"- 物品原图：{object_raw_count} 张，文件名前缀 `object_raw_`",
        f"- 物品生成图：{object_gen_count} 张，文件名前缀 `object_gen_`",
        f"- 场景生成图：{scene_gen_count} 张，文件名前缀 `scene_gen_`",
        "",
        "## 人脸匹配结果",
        "",
        f"注册参考图：`{ORIGINAL_FACE.relative_to(ROOT_DIR).as_posix()}`，注册名：`{REFERENCE_NAME}`。",
        f"匹配阈值：`{FACE_SIMILARITY_THRESHOLD}`。",
        "",
        "| 图片 | 检测到人脸 | 识别名 | 相似度 | 判断为原图同一人 | 人脸数 |",
        "|---|---|---|---:|---|---:|",
    ]

    for row in face_rows:
        lines.append(
            f"| `{row['file']}` | {_format_bool(row['detected'])} | "
            f"`{row['recognized_name']}` | {row['confidence']:.2f} | "
            f"{_format_bool(row['matched_original'])} | {row['face_count']} |"
        )

    if matched:
        names = "、".join(f"`{row['file']}`" for row in matched)
        lines += ["", f"结论：代码判断 {names} 和原图是同一人。"]
    elif best:
        lines += [
            "",
            f"结论：没有图片达到同一人阈值。最高相似度是 `{best['file']}`，相似度 {best['confidence']:.2f}。",
        ]
    else:
        lines += ["", "结论：没有可用的人脸测试结果。"]

    lines += [
        "",
        "## 物品识别结果",
        "",
        "| 图片 | 检出数量 | 标签 | 描述 |",
        "|---|---:|---|---|",
    ]

    for row in object_rows:
        labels = "、".join(row["labels"]) if row["labels"] else "-"
        lines.append(f"| `{row['file']}` | {row['count']} | {labels} | {row['description']} |")

    lines += [
        "",
        "## 物品图片来源",
        "",
    ]
    for file_name, source in OBJECT_SOURCES.items():
        lines.append(f"- `{file_name}`：{source}")

    lines += [
        "",
        "## 原始机器可读结果",
        "",
        "```json",
        json.dumps({"faces": face_rows, "objects": object_rows}, ensure_ascii=False, indent=2),
        "```",
        "",
    ]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    face_rows = run_face_match_test()
    object_rows = run_object_test()
    write_report(face_rows, object_rows)

    print(json.dumps({"faces": face_rows, "objects": object_rows}, ensure_ascii=False, indent=2))
    print(f"report written: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

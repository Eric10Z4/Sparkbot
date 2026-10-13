"""
Generate extra photo-like samples from the bundled test photos and run the
visual APIs against them. The generated files live under tests/visual_assets.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.visual import detect_anomaly, detect_objects, face_recognize

SOURCE_DIR = ROOT_DIR / "tests" / "test_images"
OUTPUT_DIR = ROOT_DIR / "tests" / "visual_assets"


def _encode_jpg(image) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        raise RuntimeError("failed to encode generated image")
    return encoded.tobytes()


def _make_variants() -> list[Path]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    sources = sorted(SOURCE_DIR.glob("*.jpg"))
    if not sources:
        raise RuntimeError(f"no source photos found in {SOURCE_DIR}")

    generated: list[Path] = []
    for source in sources:
        image = cv2.imread(str(source))
        if image is None:
            continue

        variants = {
            "bright": cv2.convertScaleAbs(image, alpha=1.12, beta=18),
            "dark": cv2.convertScaleAbs(image, alpha=0.72, beta=-8),
            "blur": cv2.GaussianBlur(image, (7, 7), 0),
        }

        h, w = image.shape[:2]
        crop = image[h // 12 : h - h // 12, w // 12 : w - w // 12]
        variants["crop"] = cv2.resize(crop, (w, h))

        for name, variant in variants.items():
            out = OUTPUT_DIR / f"scene_gen_{source.stem}_{name}.jpg"
            cv2.imwrite(str(out), variant)
            generated.append(out)

    return generated


def main() -> int:
    generated = _make_variants()
    print(f"generated {len(generated)} photos in {OUTPUT_DIR}")

    summary = []
    for path in generated:
        data = path.read_bytes()
        objects = detect_objects(data)
        face = face_recognize(data)
        anomaly = detect_anomaly(data)
        row = {
            "file": path.name,
            "objects": objects.get("count", 0),
            "object_description": objects.get("description", ""),
            "face_detected": face.get("detected", False),
            "face_count": face.get("count", 0),
            "anomaly": anomaly.get("is_anomaly", False),
            "severity": anomaly.get("severity", ""),
        }
        summary.append(row)
        print(json.dumps(row, ensure_ascii=False))

        assert "objects" in objects and "description" in objects
        assert "detected" in face and "all_faces" in face
        assert "is_anomaly" in anomaly and "severity" in anomaly

    print("generated photo visual test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Generate an expanded object-image test set into one flat asset directory.

Raw object photos use the prefix object_raw_.
Generated object photos use the prefix object_gen_.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT_DIR / "tests" / "visual_assets"


def _imread(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _imwrite(path: Path, image) -> bool:
    ok, encoded = cv2.imencode(".jpg", image)
    if not ok:
        return False
    encoded.tofile(str(path))
    return True


def _resize_like(image, reference):
    h, w = reference.shape[:2]
    return cv2.resize(image, (w, h), interpolation=cv2.INTER_LINEAR)


def _center_crop(image, crop_ratio: float):
    h, w = image.shape[:2]
    new_h = int(h * crop_ratio)
    new_w = int(w * crop_ratio)
    y1 = max(0, (h - new_h) // 2)
    x1 = max(0, (w - new_w) // 2)
    return image[y1 : y1 + new_h, x1 : x1 + new_w]


def _rotate(image, angle: float):
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), borderMode=cv2.BORDER_REFLECT_101)


def _add_noise(image, sigma: float):
    noise = np.random.default_rng(20260614).normal(0, sigma, image.shape)
    noisy = image.astype(np.float32) + noise
    return np.clip(noisy, 0, 255).astype(np.uint8)


def _warm(image):
    result = image.astype(np.float32)
    result[:, :, 2] *= 1.12
    result[:, :, 0] *= 0.92
    return np.clip(result, 0, 255).astype(np.uint8)


def _cool(image):
    result = image.astype(np.float32)
    result[:, :, 0] *= 1.12
    result[:, :, 2] *= 0.92
    return np.clip(result, 0, 255).astype(np.uint8)


def _sharpen(image):
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    return cv2.filter2D(image, -1, kernel)


def _jpeg_roundtrip(image, quality: int):
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return image
    decoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    return decoded if decoded is not None else image


def _apply_vignette(image):
    h, w = image.shape[:2]
    x = cv2.getGaussianKernel(w, w / 2.5)
    y = cv2.getGaussianKernel(h, h / 2.5)
    mask = y @ x.T
    mask = mask / mask.max()
    result = image.astype(np.float32) * (0.55 + 0.45 * mask[:, :, None])
    return np.clip(result, 0, 255).astype(np.uint8)


def _apply_shadow(image):
    h, w = image.shape[:2]
    gradient = np.linspace(0.65, 1.05, w, dtype=np.float32)
    result = image.astype(np.float32) * gradient[None, :, None]
    return np.clip(result, 0, 255).astype(np.uint8)


def _variants(image):
    h, w = image.shape[:2]
    small = cv2.resize(image, (max(32, w // 2), max(32, h // 2)))

    return {
        "bright": cv2.convertScaleAbs(image, alpha=1.15, beta=22),
        "dark": cv2.convertScaleAbs(image, alpha=0.70, beta=-10),
        "high_contrast": cv2.convertScaleAbs(image, alpha=1.28, beta=-18),
        "low_contrast": cv2.convertScaleAbs(image, alpha=0.82, beta=22),
        "blur_soft": cv2.GaussianBlur(image, (5, 5), 0),
        "blur_strong": cv2.GaussianBlur(image, (9, 9), 0),
        "sharpen": _sharpen(image),
        "noise_light": _add_noise(image, 7),
        "noise_medium": _add_noise(image, 14),
        "warm": _warm(image),
        "cool": _cool(image),
        "crop_90": _resize_like(_center_crop(image, 0.90), image),
        "crop_80": _resize_like(_center_crop(image, 0.80), image),
        "crop_70": _resize_like(_center_crop(image, 0.70), image),
        "rotate_left": _rotate(image, -5),
        "rotate_right": _rotate(image, 5),
        "rotate_left_big": _rotate(image, -10),
        "rotate_right_big": _rotate(image, 10),
        "flip_horizontal": cv2.flip(image, 1),
        "small_upscale": cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR),
        "jpeg_95": _jpeg_roundtrip(image, 95),
        "jpeg_75": _jpeg_roundtrip(image, 75),
        "jpeg_55": _jpeg_roundtrip(image, 55),
        "gray_bgr": cv2.cvtColor(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR),
        "equalized": cv2.cvtColor(
            cv2.equalizeHist(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)),
            cv2.COLOR_GRAY2BGR,
        ),
        "top_crop": _resize_like(image[: int(h * 0.86), :], image),
        "bottom_crop": _resize_like(image[int(h * 0.14) :, :], image),
        "left_crop": _resize_like(image[:, : int(w * 0.86)], image),
        "right_crop": _resize_like(image[:, int(w * 0.14) :], image),
        "letterbox": cv2.copyMakeBorder(
            cv2.resize(image, (int(w * 0.86), int(h * 0.86))),
            int(h * 0.07),
            h - int(h * 0.86) - int(h * 0.07),
            int(w * 0.07),
            w - int(w * 0.86) - int(w * 0.07),
            cv2.BORDER_CONSTANT,
            value=(245, 245, 245),
        ),
        "vignette": _apply_vignette(image),
        "shadow": _apply_shadow(image),
    }


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    raw_paths = sorted(ASSET_DIR.glob("object_raw_*.jpg"))
    if not raw_paths:
        raise RuntimeError(f"no object_raw_*.jpg images found in {ASSET_DIR}")

    for stale in ASSET_DIR.glob("object_gen_*.jpg"):
        stale.unlink()

    written = []
    for raw_path in raw_paths:
        image = _imread(raw_path)
        if image is None:
            continue

        raw_stem = raw_path.stem.removeprefix("object_raw_")
        for suffix, variant in _variants(image).items():
            out_path = ASSET_DIR / f"object_gen_{raw_stem}_{suffix}.jpg"
            if _imwrite(out_path, variant):
                written.append(out_path)

    print(f"raw images: {len(raw_paths)}")
    print(f"generated images: {len(written)}")
    print(f"output: {ASSET_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

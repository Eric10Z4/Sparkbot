from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "captured_images"
DEFAULT_OUTPUT_DIR = DEFAULT_INPUT_DIR / "repaired"


def decode_rgb565_big_endian(data: bytes, width: int, height: int) -> np.ndarray:
    expected = width * height * 2
    if len(data) != expected:
        raise ValueError(f"expected {expected} bytes for {width}x{height} RGB565, got {len(data)}")

    pixels = np.frombuffer(data, dtype=">u2").reshape((height, width))
    r5 = (pixels >> 11) & 0x1F
    g6 = (pixels >> 5) & 0x3F
    b5 = pixels & 0x1F

    r8 = ((r5 << 3) | (r5 >> 2)).astype(np.uint8)
    g8 = ((g6 << 2) | (g6 >> 4)).astype(np.uint8)
    b8 = ((b5 << 3) | (b5 >> 2)).astype(np.uint8)
    return np.dstack((r8, g8, b8))


def write_image(path: Path, image_bgr: np.ndarray, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise RuntimeError(f"failed to encode {path}")
    encoded.tofile(str(path))


def convert_file(src: Path, dst: Path, width: int, height: int, quality: int, rotate_180: bool) -> None:
    rgb = decode_rgb565_big_endian(src.read_bytes(), width, height)
    if rotate_180:
        rgb = cv2.rotate(rgb, cv2.ROTATE_180)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    write_image(dst, bgr, quality)


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert SparkBot RGB565 captures to normal JPG images.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--width", type=int, default=240)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--quality", type=int, default=95)
    parser.add_argument("--no-rotate", action="store_true", help="Disable the default 180-degree rotation fix.")
    args = parser.parse_args()

    sources = sorted(args.input_dir.glob("*.rgb565"))
    if not sources:
        print(f"No .rgb565 files found in {args.input_dir}")
        return 0

    for src in sources:
        dst = args.output_dir / f"{src.stem}_fixed.jpg"
        convert_file(src, dst, args.width, args.height, args.quality, not args.no_rotate)
        print(dst)

    print(f"Converted {len(sources)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

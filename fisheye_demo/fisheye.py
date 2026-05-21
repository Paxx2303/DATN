from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image


def _map_standard(radius: np.ndarray) -> np.ndarray:
    return (2.0 / math.pi) * np.arcsin(radius)


def _map_extreme(radius: np.ndarray) -> np.ndarray:
    return radius * radius


def _map_subtle(radius: np.ndarray) -> np.ndarray:
    return radius * (1.0 - 0.25 * np.sin(radius * math.pi))


def _map_traffic_camera(radius: np.ndarray) -> np.ndarray:
    standard = _map_standard(radius)
    extreme = _map_extreme(radius)
    return np.clip((standard * 0.45) + (extreme * 0.55), 0.0, 1.0)


EFFECT_MAP = {
    "standard": _map_standard,
    "extreme": _map_extreme,
    "subtle": _map_subtle,
    "traffic_camera": _map_traffic_camera,
}

EFFECT_LABELS_VI: dict[str, str] = {
    "standard": "Mắt cá tiêu chuẩn",
    "extreme": "Biến dạng cực độ",
    "subtle": "Vết lồi nhỏ",
    "traffic_camera": "Preset camera giao thông",
}


def bilinear_sample(source: np.ndarray, sample_x: np.ndarray, sample_y: np.ndarray) -> np.ndarray:
    height, width, _channels = source.shape

    sample_x = np.clip(sample_x, 0, width - 1)
    sample_y = np.clip(sample_y, 0, height - 1)

    x0 = np.floor(sample_x).astype(np.int32)
    y0 = np.floor(sample_y).astype(np.int32)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)

    frac_x = (sample_x - x0).astype(np.float32)[:, None]
    frac_y = (sample_y - y0).astype(np.float32)[:, None]

    weight_00 = (1 - frac_x) * (1 - frac_y)
    weight_10 = frac_x * (1 - frac_y)
    weight_01 = (1 - frac_x) * frac_y
    weight_11 = frac_x * frac_y

    value_00 = source[y0, x0]
    value_10 = source[y0, x1]
    value_01 = source[y1, x0]
    value_11 = source[y1, x1]

    return weight_00 * value_00 + weight_10 * value_10 + weight_01 * value_01 + weight_11 * value_11


def apply_fisheye(
    image: Image.Image,
    strength: float = 0.5,
    radius: float = 0.7,
    effect: str = "standard",
    center_x_ratio: float = 0.5,
    center_y_ratio: float = 0.5,
    axis_scale_x: float = 1.0,
    axis_scale_y: float = 1.0,
    full_frame: bool = False,
) -> Image.Image:
    if effect not in EFFECT_MAP:
        raise ValueError(f"effect must be one of {list(EFFECT_MAP)}, got {effect!r}")

    strength = float(np.clip(strength, 0.0, 1.0))
    radius = float(np.clip(radius, 0.0, 1.0))
    center_x_ratio = float(np.clip(center_x_ratio, 0.0, 1.0))
    center_y_ratio = float(np.clip(center_y_ratio, 0.0, 1.0))
    axis_scale_x = float(np.clip(axis_scale_x, 0.35, 2.5))
    axis_scale_y = float(np.clip(axis_scale_y, 0.35, 2.5))

    original_mode = image.mode
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA")

    source = np.asarray(image, dtype=np.float32)
    height, width, channels = source.shape
    center_x = width * center_x_ratio
    center_y = height * center_y_ratio
    if full_frame:
        corner_distances = np.array(
            [
                math.hypot(center_x / axis_scale_x, center_y / axis_scale_y),
                math.hypot((width - center_x) / axis_scale_x, center_y / axis_scale_y),
                math.hypot(center_x / axis_scale_x, (height - center_y) / axis_scale_y),
                math.hypot((width - center_x) / axis_scale_x, (height - center_y) / axis_scale_y),
            ],
            dtype=np.float32,
        )
        max_radius = float(corner_distances.max()) * radius
    else:
        max_radius = min(
            center_x / axis_scale_x,
            (width - center_x) / axis_scale_x,
            center_y / axis_scale_y,
            (height - center_y) / axis_scale_y,
        ) * radius

    if max_radius <= 0:
        return image.copy().convert(original_mode)

    grid_y, grid_x = np.mgrid[0:height, 0:width]
    delta_x = grid_x.astype(np.float32) - center_x
    delta_y = grid_y.astype(np.float32) - center_y
    normalized_x = delta_x / axis_scale_x
    normalized_y = delta_y / axis_scale_y
    distance = np.sqrt(normalized_x * normalized_x + normalized_y * normalized_y)

    source_x = grid_x.astype(np.float32).ravel()
    source_y = grid_y.astype(np.float32).ravel()

    mask = (distance > 0) & (distance < max_radius)
    if mask.any():
        radius_norm = distance[mask] / max_radius
        mapped_radius = EFFECT_MAP[effect](radius_norm)
        final_radius = radius_norm + (mapped_radius - radius_norm) * strength
        scale = final_radius / radius_norm

        flat_mask = mask.ravel()
        source_x[flat_mask] = center_x + delta_x.ravel()[flat_mask] * scale
        source_y[flat_mask] = center_y + delta_y.ravel()[flat_mask] * scale

    sampled = bilinear_sample(source, source_x, source_y)
    output = np.clip(sampled, 0, 255).astype(np.uint8).reshape(height, width, channels)

    result = Image.fromarray(output, mode=image.mode)
    if result.mode != original_mode:
        result = result.convert(original_mode)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply a fisheye or barrel distortion effect to an image.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="Input image path")
    parser.add_argument("output", nargs="?", help="Output image path")
    parser.add_argument("--strength", "-s", type=float, default=0.5, help="Distortion strength [0.0-1.0]")
    parser.add_argument("--radius", "-r", type=float, default=0.7, help="Distortion radius [0.0-1.0]")
    parser.add_argument("--effect", "-e", choices=list(EFFECT_MAP), default="standard", help="Distortion profile")
    return parser


def main() -> None:
    args = build_parser().parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_name(f"{input_path.stem}_fisheye.png")

    image = Image.open(input_path)
    result = apply_fisheye(image, strength=args.strength, radius=args.radius, effect=args.effect)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path)

    print(f"Saved fisheye output to: {output_path}")


if __name__ == "__main__":
    main()

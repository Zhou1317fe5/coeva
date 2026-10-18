from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE_PATH = ROOT / "assets/vasu/reference/vasu-native-canonical-hires.png"
NEUTRAL_PATH = HERE / "neutral-reconstruction.png"
CLOSED_PATH = HERE / "closed-reconstruction.png"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def visible_diff(left: Image.Image, right: Image.Image) -> dict[str, float | int]:
    changed = 0
    total = 0
    maximum = 0
    sum_abs = 0
    greater_than_15 = 0
    for source_pixel, reconstructed_pixel in zip(left.getdata(), right.getdata()):
        if source_pixel[3] > 0 or reconstructed_pixel[3] > 0:
            total += 1
            delta = sum(
                abs(source_pixel[channel] - reconstructed_pixel[channel])
                for channel in range(3)
            )
            sum_abs += delta
            maximum = max(maximum, delta)
            greater_than_15 += delta > 15
            changed += source_pixel != reconstructed_pixel
    return {
        "changed_visible_pixels": changed,
        "visible_pixels": total,
        "max_rgb_delta_sum": maximum,
        "mean_rgb_abs_sum": sum_abs / total if total else 0.0,
        "pixels_rgb_delta_sum_gt15": greater_than_15,
    }


with Image.open(SOURCE_PATH) as opened:
    source = opened.convert("RGBA")
with Image.open(NEUTRAL_PATH) as opened:
    neutral = opened.convert("RGBA")
with Image.open(CLOSED_PATH) as opened:
    closed = opened.convert("RGBA")

source_desktop = source.resize((300, 300), Image.Resampling.LANCZOS)
neutral_desktop = neutral.resize((300, 300), Image.Resampling.LANCZOS)
closed_desktop = closed.resize((300, 300), Image.Resampling.LANCZOS)

font = ImageFont.load_default()
comparison = Image.new("RGBA", (900, 330), (241, 240, 236, 255))
draw = ImageDraw.Draw(comparison)
for index, (label, image) in enumerate(
    (
        ("canonical", source_desktop),
        ("neutral reconstruction", neutral_desktop),
        ("blink preview", closed_desktop),
    )
):
    background = Image.new("RGB", image.size, "#f1f0ec")
    background.paste(image, mask=image.getchannel("A"))
    comparison.paste(background, (index * 300, 30))
    draw.text((index * 300 + 8, 8), label, fill="#241a16", font=font)
    draw.rectangle((index * 300, 30, index * 300 + 299, 329), outline="#5b4a40")
comparison.convert("RGB").save(HERE / "desktop-neutral-reconstruction-comparison.png")

layer_metrics: dict[str, dict[str, object]] = {}
for path in sorted((HERE / "layers").glob("*.png")):
    with Image.open(path) as opened:
        image = opened.convert("RGBA")
    alpha = image.getchannel("A")
    bbox = image.getbbox()
    layer_metrics[path.stem] = {
        "path": str(path),
        "sha256": sha(path),
        "size": list(image.size),
        "bbox": list(bbox) if bbox else None,
        "transparent_rgb_residue": sum(
            1
            for red, green, blue, alpha_value in image.getdata()
            if alpha_value == 0 and (red or green or blue)
        ),
        "nontransparent_pixels": sum(alpha.histogram()[1:]),
    }

neutral_native_diff = visible_diff(source, neutral)
neutral_desktop_diff = visible_diff(source_desktop, neutral_desktop)
closed_native_diff = visible_diff(source, closed)
checks = {
    "neutral_effectively_indistinguishable_at_desktop": (
        neutral_desktop_diff["mean_rgb_abs_sum"] <= 2.0
        and neutral_desktop_diff["pixels_rgb_delta_sum_gt15"] <= 20
    ),
    "layer_transparent_rgb_clean": all(
        metrics["transparent_rgb_residue"] == 0 for metrics in layer_metrics.values()
    ),
    "neutral_reconstruction_present": NEUTRAL_PATH.exists(),
    "blink_reconstruction_present": CLOSED_PATH.exists(),
}
checks["pass"] = all(checks.values())
validation = {
    "phase": "V2-A2R",
    "native_master": str(SOURCE_PATH),
    "layer_structure": layer_metrics,
    "neutral_reconstruction": {
        "path": str(NEUTRAL_PATH),
        "visible_diff_native": neutral_native_diff,
        "visible_diff_desktop_300px": neutral_desktop_diff,
    },
    "blink_reconstruction": {
        "path": str(CLOSED_PATH),
        "visible_diff_against_open_native": closed_native_diff,
    },
    "desktop_target": {
        "preview_canvas_px": 300,
        "visible_height_range_px": [186, 221],
    },
    "checks": checks,
}
(HERE / "validation.json").write_text(
    json.dumps(validation, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps({"pass": checks["pass"], "desktop_diff": neutral_desktop_diff}, indent=2))

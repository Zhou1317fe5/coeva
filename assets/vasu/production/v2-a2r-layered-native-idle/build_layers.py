from __future__ import annotations

import json
from pathlib import Path
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from native_idle_rig import LayeredNativeIdleAssets, compose_native  # noqa: E402

ROOT = HERE.parents[3]
NATIVE = ROOT / "assets/vasu/reference/vasu-native-canonical-hires.png"
BLINK = ROOT / "assets/vasu/production/v2-a2-native-idle/candidate-02-clean/frames/02.png"
BLINK_EDIT = HERE / "blink-edit-normalized.png"
LAYERS = HERE / "layers"
LAYERS.mkdir(parents=True, exist_ok=True)


def clean_rgba(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    data = bytearray(rgba.tobytes())
    for index in range(0, len(data), 4):
        if data[index + 3] == 0:
            data[index] = data[index + 1] = data[index + 2] = 0
    return Image.frombytes("RGBA", rgba.size, bytes(data))


def copy_region(target: Image.Image, source: Image.Image, box: tuple[int, int, int, int]) -> None:
    target.alpha_composite(source.crop(box), (box[0], box[1]))


def inpaint_eye_crop(crop: Image.Image, mask: Image.Image) -> Image.Image:
    """Fill a tight eye-shaped mask from its surrounding native fur texture."""
    rgba = crop.convert("RGBA")
    width, height = rgba.size
    source_pixels = list(rgba.getdata())
    mask_values = [value > 0 for value in mask.getdata()]
    filled = [not value for value in mask_values]
    output = list(source_pixels)
    for _ in range(width + height):
        updates: list[tuple[int, tuple[int, int, int, int]]] = []
        for index, is_masked in enumerate(mask_values):
            if not is_masked or filled[index]:
                continue
            x = index % width
            y = index // width
            neighbors: list[tuple[int, int, int, int]] = []
            for nx, ny in (
                (x - 1, y),
                (x + 1, y),
                (x, y - 1),
                (x, y + 1),
            ):
                if 0 <= nx < width and 0 <= ny < height:
                    neighbor = ny * width + nx
                    if filled[neighbor]:
                        neighbors.append(output[neighbor])
            if neighbors:
                count = len(neighbors)
                updates.append(
                    (
                        index,
                        tuple(
                            sum(color[channel] for color in neighbors) // count
                            for channel in range(4)
                        ),
                    )
                )
        if not updates:
            break
        for index, color in updates:
            output[index] = color
            filled[index] = True
    return Image.frombytes("RGBA", rgba.size, bytes(sum(output, ())))


with Image.open(NATIVE) as opened:
    source = clean_rgba(opened)
with Image.open(BLINK_EDIT) as opened:
    blink_edit = clean_rgba(opened)

# The head/body regions overlap geometrically, but the body is masked wherever the
# head has visible pixels. This preserves exact neutral pixels while leaving a broad
# neck viewport available for tiny future head translations. The head base uses tight
# local fur fills at the eye ovals; eyes-open restores the exact native eye pixels.
body = source.copy()
body_pixels = body.load()
for y in range(0, 420):
    for x in range(body.width):
        body_pixels[x, y] = (0, 0, 0, 0)
head_base = source.copy()
head_pixels = head_base.load()
for y in range(560, head_base.height):
    for x in range(head_base.width):
        head_pixels[x, y] = (0, 0, 0, 0)
left_eye = (360, 385, 415, 438)
right_eye = (497, 406, 560, 464)
# Replace each open-eye shape with an inpainted local texture. The open-eye layer
# restores the exact native pixels for neutral reconstruction; the closed-eye layer
# can therefore draw only the eyelid line, with no rectangular cover block.
for box in (left_eye, right_eye):
    x1, y1, x2, y2 = box
    native_crop = source.crop(box)
    edit_crop = blink_edit.crop(box)
    native_mask = Image.new("L", native_crop.size, 0)
    edit_mask = Image.new("L", edit_crop.size, 0)
    for crop, mask in ((native_crop, native_mask), (edit_crop, edit_mask)):
        mask_pixels = mask.load()
        crop_pixels = crop.load()
        for y in range(crop.height):
            for x in range(crop.width):
                red, green, blue, alpha = crop_pixels[x, y]
                if alpha > 16 and red < 150 and green < 115 and blue < 105:
                    mask_pixels[x, y] = 255
    dark_mask = ImageChops.lighter(native_mask, edit_mask).filter(ImageFilter.MaxFilter(3))
    fill = inpaint_eye_crop(edit_crop, dark_mask)
    paste_mask = dark_mask.filter(ImageFilter.GaussianBlur(1.5))
    head_base.paste(fill, (x1, y1), paste_mask)
    head_pixels = head_base.load()
for y in range(source.height):
    for x in range(source.width):
        if head_pixels[x, y][3] > 0:
            body_pixels[x, y] = (0, 0, 0, 0)
for x1, y1, x2, y2 in (left_eye, right_eye):
    for y in range(y1, y2):
        for x in range(x1, x2):
            body_pixels[x, y] = (0, 0, 0, 0)
eyes_open = Image.new("RGBA", source.size, (0, 0, 0, 0))
copy_region(eyes_open, source, left_eye)
copy_region(eyes_open, source, right_eye)

eyes_closed = Image.new("RGBA", source.size, (0, 0, 0, 0))
# The targeted imagegen repair supplies a texture-consistent head-region replacement.
# The runtime compositor uses this only during blink, while the neutral path still
# uses head-base plus exact eyes-open pixels.
head_overlay_box = (251, 232, 866, 560)
eyes_closed.alpha_composite(
    blink_edit.crop(head_overlay_box),
    (head_overlay_box[0], head_overlay_box[1]),
)

for name, layer in (("body", body), ("head-base", head_base), ("eyes-open", eyes_open), ("eyes-closed", eyes_closed)):
    clean_rgba(layer).save(LAYERS / f"{name}.png")

assets = LayeredNativeIdleAssets(body=body, head_base=head_base, eyes_open=eyes_open, eyes_closed=eyes_closed)
neutral = compose_native(assets, scale_y=1.0, anchor_y=952.0, blink_closed=False)
neutral.save(HERE / "neutral-reconstruction.png")
closed = compose_native(assets, scale_y=1.0, anchor_y=952.0, blink_closed=True)
closed.save(HERE / "closed-reconstruction.png")

# A simple visual comparison at native canvas scale.
comparison = Image.new("RGBA", (2048, 1024), (241, 240, 236, 255))
comparison.alpha_composite(source, (0, 0))
comparison.alpha_composite(neutral, (1024, 0))
comparison.convert("RGB").save(HERE / "canonical-vs-reconstruction.png")

metadata = {
    "canvas": {"width": 1024, "height": 1024},
    "layers": {
        "body": "layers/body.png",
        "head_base": "layers/head-base.png",
        "eyes_open": "layers/eyes-open.png",
        "eyes_closed": "layers/eyes-closed.png",
    },
    "identity_source": str(NATIVE),
    "accepted_blink_source": str(BLINK),
    "targeted_blink_repair_source": str(BLINK_EDIT),
    "head_body_overlap": {"body_start_y": 420, "head_end_y": 560, "overlap_px": 140, "visible_overlap_masked": True},
    "eye_boxes": {"left": left_eye, "right": right_eye},
    "alternative_structure_reason": "eye-only raster repair created visible texture seams; the smallest safe alternative is a texture-consistent head-region replacement used only during blink. Neutral still uses head-base plus exact eyes-open pixels.",
    "closed_head_overlay_box": head_overlay_box,
    "neutral_reconstruction": "neutral-reconstruction.png",
}
(HERE / "rig.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
print(json.dumps(metadata, indent=2))

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from native_idle_rig import (  # noqa: E402
    AmbientIdleConfig,
    blink_is_closed,
    load_assets,
    make_blink_schedule,
    render_frame,
    resize_assets,
)

DURATION_S = 14.0
FPS = 12
ROOT = HERE
native_assets = load_assets(ROOT / "layers")
assets = resize_assets(native_assets, 320)
config = AmbientIdleConfig(
    breathing_period_s=6.0,
    breathing_amplitude=0.004,
    blink_min_interval_s=4.5,
    blink_max_interval_s=8.5,
    blink_duration_s=0.14,
    seed=20261017,
    desktop_size=320,
    anchor_y=952.0 * 320 / 1024,
)
events = make_blink_schedule(DURATION_S, config)
frame_count = round(DURATION_S * FPS)
start = time.perf_counter()
frames = [
    render_frame(assets, index / FPS, config, events)
    for index in range(frame_count)
]
elapsed = time.perf_counter() - start

preview_path = ROOT / "procedural-preview-qa.gif"
frames[0].save(
    preview_path,
    save_all=True,
    append_images=frames[1:],
    duration=round(1000 / FPS),
    loop=0,
    disposal=2,
    optimize=False,
)

font = ImageFont.load_default()
sample_indices = [0, 18, 36, 54, 72, 90, 108, 126, 144, 167]
contact = Image.new("RGB", (5 * 320, 2 * 350), "#f1f0ec")
draw = ImageDraw.Draw(contact)
for slot, frame_index in enumerate(sample_indices):
    frame = frames[min(frame_index, len(frames) - 1)]
    x = (slot % 5) * 320
    y = (slot // 5) * 350
    bg = Image.new("RGB", frame.size, "#f1f0ec")
    bg.paste(frame, mask=frame.getchannel("A"))
    contact.paste(bg, (x, y + 30))
    draw.rectangle((x, y + 30, x + 319, y + 349), outline="#5b4a40")
    time_s = min(frame_index / FPS, DURATION_S)
    draw.text(
        (x + 8, y + 8),
        f"t={time_s:.2f}s {'blink' if blink_is_closed(time_s, events) else 'open'}",
        fill="#241a16",
        font=font,
    )
contact.save(ROOT / "procedural-preview-contact.png")

frame_metrics = []
for index, frame in enumerate(frames):
    bbox = frame.getbbox()
    frame_metrics.append(
        {
            "index": index,
            "time_s": index / FPS,
            "blink_closed": blink_is_closed(index / FPS, events),
            "bbox": list(bbox) if bbox else None,
            "visible_height": bbox[3] - bbox[1] if bbox else 0,
            "visible_width": bbox[2] - bbox[0] if bbox else 0,
        }
    )

(ROOT / "preview-events.json").write_text(
    json.dumps(
        {
            "duration_s": DURATION_S,
            "fps": FPS,
            "config": {
                "breathing_period_s": config.breathing_period_s,
                "breathing_amplitude": config.breathing_amplitude,
                "blink_min_interval_s": config.blink_min_interval_s,
                "blink_max_interval_s": config.blink_max_interval_s,
                "blink_duration_s": config.blink_duration_s,
                "seed": config.seed,
            },
            "blink_events": [event.__dict__ for event in events],
            "blink_phases": [
                (event.start_s % config.breathing_period_s) / config.breathing_period_s
                for event in events
            ],
            "render_seconds": elapsed,
            "render_ms_per_frame": elapsed / frame_count * 1000,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
(ROOT / "preview-frame-metrics.json").write_text(
    json.dumps({"frames": frame_metrics}, indent=2) + "\n",
    encoding="utf-8",
)
print(
    json.dumps(
        {
            "preview": str(preview_path),
            "frames": frame_count,
            "duration_s": DURATION_S,
            "blink_events": [event.__dict__ for event in events],
            "render_ms_per_frame": elapsed / frame_count * 1000,
            "visible_height_range": [
                min(item["visible_height"] for item in frame_metrics),
                max(item["visible_height"] for item in frame_metrics),
            ],
        },
        indent=2,
    )
)

from __future__ import annotations

"""Small procedural ambient-idle rig prototype for Vasu v2.

This module is a production feasibility harness, not desktop runtime integration.
It renders a frozen layered native Vasu with continuous breathing and an independent
seeded blink schedule so the behavior can be reviewed without a fixed sprite loop.
"""

from dataclasses import dataclass
import math
import random
from pathlib import Path
from typing import Iterable

from PIL import Image


@dataclass(frozen=True)
class BlinkEvent:
    start_s: float
    end_s: float


@dataclass(frozen=True)
class AmbientIdleConfig:
    breathing_period_s: float = 6.0
    breathing_amplitude: float = 0.004
    blink_min_interval_s: float = 4.5
    blink_max_interval_s: float = 8.5
    blink_duration_s: float = 0.14
    seed: int = 20261017
    anchor_y: float = 952.0
    desktop_size: int = 300


@dataclass(frozen=True)
class LayeredNativeIdleAssets:
    body: Image.Image
    head_base: Image.Image
    eyes_open: Image.Image
    eyes_closed: Image.Image

    @property
    def size(self) -> tuple[int, int]:
        return self.body.size


def resize_assets(
    assets: LayeredNativeIdleAssets,
    size: int,
) -> LayeredNativeIdleAssets:
    """Prepare one cached display-resolution copy for a desktop renderer."""
    def resize(layer: Image.Image) -> Image.Image:
        return layer.resize((size, size), Image.Resampling.LANCZOS)

    return LayeredNativeIdleAssets(
        body=resize(assets.body),
        head_base=resize(assets.head_base),
        eyes_open=resize(assets.eyes_open),
        eyes_closed=resize(assets.eyes_closed),
    )


def make_blink_schedule(
    duration_s: float,
    config: AmbientIdleConfig,
) -> tuple[BlinkEvent, ...]:
    """Create irregular blink events independent of breathing phase."""
    rng = random.Random(config.seed)
    cursor = rng.uniform(config.blink_min_interval_s, config.blink_max_interval_s)
    events: list[BlinkEvent] = []
    while cursor < duration_s:
        events.append(BlinkEvent(cursor, cursor + config.blink_duration_s))
        cursor += rng.uniform(
            config.blink_min_interval_s,
            config.blink_max_interval_s,
        )
    return tuple(events)


def blink_is_closed(time_s: float, events: Iterable[BlinkEvent]) -> bool:
    return any(event.start_s <= time_s < event.end_s for event in events)


def breathing_scale(time_s: float, config: AmbientIdleConfig) -> float:
    phase = (time_s / config.breathing_period_s) * math.tau
    return 1.0 + config.breathing_amplitude * math.sin(phase)


def scale_about_anchor(
    layer: Image.Image,
    scale_y: float,
    anchor_y: float,
) -> Image.Image:
    if layer.mode != "RGBA":
        layer = layer.convert("RGBA")
    inverse_scale = 1.0 / scale_y
    offset = anchor_y * (1.0 - inverse_scale)
    return layer.transform(
        layer.size,
        Image.Transform.AFFINE,
        (1.0, 0.0, 0.0, 0.0, inverse_scale, offset),
        resample=Image.Resampling.BICUBIC,
    )


def compose_native(
    assets: LayeredNativeIdleAssets,
    scale_y: float = 1.0,
    anchor_y: float = 952.0,
    blink_closed: bool = False,
) -> Image.Image:
    """Composite the four layers at the native canvas resolution."""
    canvas = Image.new("RGBA", assets.size, (0, 0, 0, 0))
    canvas.alpha_composite(scale_about_anchor(assets.body, scale_y, anchor_y))
    if blink_closed:
        # The closed-eye prototype is a texture-consistent head-region replacement.
        # It is the smallest raster-safe alternative to a visibly patched eye-only fill.
        canvas.alpha_composite(scale_about_anchor(assets.eyes_closed, scale_y, anchor_y))
    else:
        canvas.alpha_composite(scale_about_anchor(assets.head_base, scale_y, anchor_y))
        canvas.alpha_composite(scale_about_anchor(assets.eyes_open, scale_y, anchor_y))
    return canvas


def render_frame(
    assets: LayeredNativeIdleAssets,
    time_s: float,
    config: AmbientIdleConfig,
    blink_events: Iterable[BlinkEvent],
) -> Image.Image:
    native = compose_native(
        assets,
        scale_y=breathing_scale(time_s, config),
        anchor_y=config.anchor_y,
        blink_closed=blink_is_closed(time_s, blink_events),
    )
    return native.resize(
        (config.desktop_size, config.desktop_size),
        Image.Resampling.LANCZOS,
    )


def load_assets(root: Path) -> LayeredNativeIdleAssets:
    def load(name: str) -> Image.Image:
        with Image.open(root / name) as opened:
            return opened.convert("RGBA")

    return LayeredNativeIdleAssets(
        body=load("body.png"),
        head_base=load("head-base.png"),
        eyes_open=load("eyes-open.png"),
        eyes_closed=load("eyes-closed.png"),
    )

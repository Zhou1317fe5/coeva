# V2.1 Native Desktop Idle + Sparse Blink

Status: PASS — validation completed; blink timing tuned to 8–18s and blink asset repaired

## Implementation approach

Vasu keeps the existing `PetWindow` and `AnimationPlayer` stack. A small validated
`native_idle.json` record selects two same-canvas static images. While Vasu is in
`PetState.IDLE`, `PetWindow` stops the atlas player, paints the neutral image, and
arms two small one-shot Qt timers: one for the next blink and one for neutral
restoration. The blink timer swaps to the closed-eye image once, restores the
neutral image after the configured duration, and chooses a new random delay.

The existing Core atlas is still loaded and remains the fallback for invalid/missing
native assets and for explicit Core states such as working, thinking, happy, error,
waiting, and sleeping. Native idle also suppresses the old autonomous activity timer,
so normal Vasu presence has no body, tail, head, or breathing loop.

## Files changed

- `src/body/animation.py`: validated native-idle config loader.
- `src/body/window.py`: Vasu-only neutral/blink swap and native-idle scheduler.
- `src/body/main.py`, `run_companion.py`: 0.3 initial native scale (persisted user scale still wins).
- `tests/test_body.py`: neutral restoration, sparse timer, Core fallback/state coverage.
- `assets/pets/vasu/native_idle.json`: production timing/asset contract.
- `assets/vasu/production/v2.1-native-desktop-idle/vasu-blink.png`: accepted closed-eye visual copied to the V2.1 production path.
- `docs/specs/vasu/SPEC.md`, `DESIGN.md`, `CHANGELOG.md`: source-of-truth and handover updates.

## Desktop validation result

The production `PetWindow` was shown at scale `0.3` for `1200.274s` (20m 0.274s).
Its logical window was `307×307px`; the native art occupied approximately `216px`
of visible height. The local window grab is [`desktop-210.png`](desktop-210.png),
and the neutral/closed-eye comparison is [`diagnostic-preview.png`](diagnostic-preview.png).

The run recorded 38 blink starts. The neutral and blink assets are both 1024×1024
RGBA images with the same alpha bounds `(157, 232, 866, 952)`. No rectangular patch,
canvas shift, seam, or non-neutral return was observed. One recorded timer gap was
66.435s; the remaining gaps were 18.489–42.178s, with a median of 31.172s. This is
an acceptable quiet-presence outlier, but it is retained in the timing record rather
than hidden.

After this validation, the production interval was tuned from `18–42s` to `8–18s`
to better match calm screen-reading presence while remaining sparse. The prior run
and its log are retained as the long-duration visual/runtime stability record; the
new interval is configuration-only and uses the same one-shot rendering path.

After review found that the first blink image changed the whole-body silhouette, the
production blink image was replaced with a baked head-only replacement. Static QA now
shows the neutral/blink difference confined to `(251, 232, 866, 560)`; the full body
and tail region from `y=560` through the bottom is pixel-identical. No runtime layer
compositor or rig was added.

Performance samples were taken every 30s through 1110.7s. Working set was 63.13–115.73MB,
private memory 56.00–58.42MB, CPU time 0.83–1.58s, and thread count 2–9. The profile
was flat after startup with no CPU loop or memory growth trend; see [`performance.json`](performance.json).

Core freeze verification is [`core-freeze-verification.json`](core-freeze-verification.json):
`src/core/` had no diff from baseline commit `9028f419e65b2a09855a41767f8cb30de7fbd7a1`.

## Repository checks

- `uv run ruff check .`: passed.
- `uv run mypy src --strict`: passed (47 source files).
- `uv run pytest -q`: passed (160 tests).
- `spec_validate`: unavailable in this checkout (`spec_validate` was not recognized as a command).

## Acceptance decision

PASS for V2.1. The Native Canonical remains faithful, the desktop is materially more
refined than the Core atlas idle row at 210px-class display size, blinking is clean and
irregular, there is no normal-state animation loop, and the runtime change is confined
to the existing body path.

Next step: stop at V2.1. Do not add breathing, gaze, head-follow, Observe, Self-work,
Rest, Play, Sleep, or other life states without explicit approval.

## Scope guard

This change does not use `NativeIdlePlayer`, the abandoned layered runtime rig, whole-
body scaling for breathing, gaze/head-follow, Observe, Self-work, Rest, Play, Sleep,
or any new animation engine. The copied blink art is used as a full-canvas image only;
the archived A2R2 runtime remains untouched.

## Validation records

- Timing/config: `native_idle.json` and `timing-config.json`
- Desktop screenshot: `desktop-210.png`
- Blink event log: `blink-events.jsonl`
- Performance: `performance.json`
- Core freeze: `core-freeze-verification.json`
- Visual integrity: `visual-integrity.json`
- Optional visual diagnostic: `diagnostic-preview.png`

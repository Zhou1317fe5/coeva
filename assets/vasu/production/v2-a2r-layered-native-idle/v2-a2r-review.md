# Vasu V2-A2R · Layered Native Idle Rig Review

**Visual Asset Gate:** V2-A2 passed. The old four-frame `idle.gif` remains a useful visual/QA reference only.

**Native Idle Runtime Architecture Gate:** PASS for a feasibility prototype; not runtime-integrated.

## Planning/spec updates

- [`assets/vasu/production/v2-development-guide.md`](../v2-development-guide.md) now defines procedural ambient life as the V2 idle architecture and reserves full-frame animations for larger pose-changing life states.
- [`v2-a2-native-idle-motion-contract.md`](../v2-a2-native-idle-motion-contract.md) now explicitly reclassifies the 1400ms GIF as a visual asset, not permanent ambient idle.
- [`v2-a2-native-idle/v2-a2-review.md`](../v2-a2-native-idle/v2-a2-review.md) records the split result: visual asset pass, runtime architecture incomplete.

## Layer structure

The prototype uses four `1024×1024` transparent layers:

- [`layers/body.png`](layers/body.png): torso, cream chest/belly, legs, paws and tail.
- [`layers/head-base.png`](layers/head-base.png): head, ears, muzzle, nose, mouth and facial fur with the eye boxes removed.
- [`layers/eyes-open.png`](layers/eyes-open.png): exact native-master eye pixels at the registered eye boxes.
- [`layers/eyes-closed.png`](layers/eyes-closed.png): texture-consistent head-region replacement used only during blink, derived from a targeted edit of the locked native master.

The eye-only split was tested first and rejected because local raster inpainting left visible texture discontinuities. The head-region replacement is the smallest raster-safe alternative: body stays shared, neutral uses head-base plus exact eyes-open, and blink swaps only the head region.

[`rig.json`](rig.json) records layer paths, eye boxes, overlap masks and the reason for the minimal raster split. The body/head regions have a 140px geometric viewport overlap, while visible pixels are masked to avoid double compositing.

## Neutral reconstruction

[`neutral-reconstruction.png`](neutral-reconstruction.png) is composed from the four layers at neutral coordinates. At the 300px desktop comparison, the mean RGB difference is `1.62` per pixel sum and only `9` pixels exceed a 15-level RGB delta. The comparison is visually indistinguishable at the target scale:

- [`desktop-neutral-reconstruction-comparison.png`](desktop-neutral-reconstruction-comparison.png)
- [`validation.json`](validation.json)

Layer transparency is clean with zero fully transparent RGB residue. No visible neck seam, body/head gap or palette discontinuity was found.

## Procedural motion

[`native_idle_rig.py`](native_idle_rig.py) implements a small display-resolution renderer:

- Breathing: continuous vertical interpolation around the grounded anchor, period `6.0s`, amplitude `±0.4%`.
- Blink: independent seeded schedule, interval range `4.5–8.5s`, blink duration `0.14s`, seed `20261017`.
- The 14-second QA run blinks at approximately `5.622s` and `11.873s`; the blink phases are independent of the breathing cycle.
- No head-follow, gaze, tail motion, scheduler, or other life state exists in this prototype.

[`procedural-preview-qa.gif`](procedural-preview-qa.gif) is a sampled QA preview only. It is not the permanent ambient asset and does not establish a repeating runtime loop. [`preview-events.json`](preview-events.json) records the schedule and tunable parameters.

## Desktop and performance QA

- Preview canvas: `320×320`; visible Vasu height stayed between `186–221px` (target desktop band).
- Baseline remained grounded through the breathing samples.
- The cached display-resolution Pillow harness rendered at about `22ms/frame` on this machine, roughly `45fps` in the prototype path; the first uncached native-resolution experiment was much slower, so runtime should cache display-resolution layers.
- The current preview is CPU-rendered and has no GPU path. No PySide runtime adapter was added in this phase.

## Remaining risks

- The neutral split is visually strong, but the head/body layer boundary is a masked raster overlap rather than a semantic vector cut. Future head translation should be rechecked at the same desktop scale.
- The closed-eye layer was repaired in this pass: rectangular eye patches and texture discontinuities were removed by switching to a texture-consistent head-region replacement. The eye-only split remains rejected for this raster master.
- The QA GIF must never become the permanent idle loop; the runtime should render from the layers and schedules.
- Frozen Core v0.1 hashes remain unchanged: [`core-freeze-check.json`](core-freeze-check.json).

**Recommendation:** accept the layered procedural approach as viable for V2-A2R. The next gate should be review/polish of this rig and a minimal runtime adapter only after approval; do not proceed to gaze/head-follow or any other life-state yet.


## Targeted blink repair

The reported defect was real: the first eyes-closed layer exposed rectangular source patches and mismatched eye-region colors. The repair touched only the blink support path and its head-base eye support; the native master, body layer, eyes-open layer and Core v0.1 remain unchanged. The refreshed [desktop comparison](desktop-neutral-reconstruction-comparison.png) shows no rectangular cover block.

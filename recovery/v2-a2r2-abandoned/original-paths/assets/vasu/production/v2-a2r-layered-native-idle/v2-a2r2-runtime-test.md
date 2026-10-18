# Vasu V2-A2R2 · Runtime Test Notes

The accepted layered rig is now connected to the real `PetWindow` path used by
`run_companion.py`.

## Runtime behavior

- Cached 1024px layers are downsampled once to a fixed `360×360` display canvas.
- The strong-visible character height is approximately `204px`; the window and
  ground baseline remain fixed while breathing.
- Breathing is continuous at a `6.0s` period with `±0.7%` vertical amplitude,
  sampled by a `50ms` timer and anchored at the bottom.
- Blink is independent and irregular: `4.5–8.5s` interval, `0.14s` duration.
- The shared runtime backdrop keeps the complete canonical raster; the blink
  layer contains only two soft eye patches, so no regenerated head region can
  overlap the body or leave eye highlights behind.
- Metrics contain one-second samples plus an explicit `blink_start` event, so a
  short blink is not lost by one-second sampling.

## User test

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe run_companion.py
```

Leave Vasu visible for 20–30 minutes. Check that breathing is barely noticeable,
the paws and baseline stay fixed, no head/body seam appears during blink, and the
blink does not feel periodic. Switching to another action and back to idle should
also restore the same neutral face.

For a timed diagnostic run with a metrics file:

```powershell
$env:COEVA_NATIVE_IDLE_TEST_MODE = "1"
$env:COEVA_NATIVE_IDLE_TEST_DURATION_S = "1800"
$env:COEVA_NATIVE_IDLE_METRICS = "assets/vasu/production/v2-a2r-layered-native-idle/user-runtime-metrics.jsonl"
.\.venv\Scripts\python.exe run_companion.py
```

The process exits after 30 minutes and writes samples plus `blink_start` events.
Diagnostic mode also disables the normal five-minute State Care timer so the
sample remains in Native Idle; ordinary runs keep that timer unchanged.
The long-duration visual acceptance decision remains with the user because this
desktop test must be observed on the real display.

## Current verification

- Native Idle and body/e2e targeted tests: `30 passed`.
- 12-second real entrypoint smoke run: exit code `0`; visible height `204px`,
  baseline `319`, and one explicit blink event.
- Frozen Core v0.1 hashes remain unchanged.
- A 20–30 minute real-display run has not been claimed as passed yet.

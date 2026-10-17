# Vasu `failed` timing refinement · Phase 2C timing-v2

**Gate: pass.** This refinement changes playback timing only; the eight approved visual frames remain byte-for-byte unchanged.

## Old vs new timing

- Old: `[140, 140, 140, 140, 140, 140, 140, 240]` ms per frame; total `1220` ms.
- New: `[160, 150, 180, 260, 220, 150, 140, 260]` ms per frame; total `1520` ms.
- The longer holds give the puzzled pause (frame 03) and the mild-disappointment state (frame 04) room to read before recovery, while frames 05–07 keep the return to calm moving.

## Visual review

- [Updated GIF](failed.gif) is the timing-v2 preview; [`qa/previews/failed.gif`](../previews/failed.gif) now points to the same updated playback.
- [Full-size frame contact](failed-contact.png) confirms the existing calm → notice → puzzled → mild disappointment → recovery → calm arc.
- [64px contact](failed-64px-contact.png) preserves the rounded head, small dark eyes, cream bib, compact body and attached tail at pet scale.
- The 03 → 04 pose change remains an intentional small emotional step; with the longer holds it no longer reads as a rushed cascade. No visual repair was needed.

## Deterministic QA

- Eight frames, each `192×208`; validation errors: `0`.
- Baseline is planted and unchanged; no size or silhouette repair was introduced.
- Alpha/chroma checks remain clean: no edge pixels, no chroma-adjacent opaque pixels, and no transparent RGB residue in the approved frame files.
- GIF metadata contains the new eight-frame timing; frame order is unchanged.
- All previously approved rows, including `idle`, `running-right`, `running-left`, `waiting`, `review`, `running`, `waving`, and `jumping`, remain byte-for-byte unchanged. The `failed` decoded strip and eight extracted frames are also unchanged.
- The inspector reports the existing `stable-slots` method as a warning for `failed`; this is the previously accepted extraction choice used to keep the common baseline stable, not a new failure.

**Recommendation:** lock `failed` with the timing-v2 preview and proceed to final atlas approval only when separately authorized.

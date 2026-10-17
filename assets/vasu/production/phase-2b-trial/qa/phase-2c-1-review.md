# Vasu Phase 2C-1 · `running-left` mirror gate

**Decision: mirror-safe; left row approved.** Scope is the approved `running-right` row and its deterministic left-facing counterpart only. The locked `idle`, `running-right`, Phase 1 identity, and Phase 2A motion language were not changed; no other row or atlas was produced.

## Asymmetry review before derivation

| Feature | Finding |
| --- | --- |
| Face and ears | Small calm eye, rounded muzzle and ears have no one-sided marking or accessory. A near/far ear swap is the natural result of changing facing direction. |
| Cream muzzle/chest | The cream bib and cheek shape are continuous anatomy, not a directional badge or side-specific patch. |
| Tail and paws | The thick tail remains attached behind the haunch. Short planted paws alternate without a side-specific prop or limb design. |
| Shading/artifacts | Soft baked body shading flips with the sprite but does not encode an external light source or meaningful direction. No text, asymmetric effects, shadow, or loose component would reverse incorrectly. |

The hatch mirror script first created [`decoded/running-left.png`](../decoded/running-left.png) by mirroring each of eight source-strip slots in place, preserving frame order. The source poses crowd some original slot boundaries: re-extracting that packed strip changed the widths of several mirrored frames and failed the exact right/left comparison. That extraction was rejected. The approved [left frames](../frames/running-left/) instead use the same hatch per-slot mirror function on **each already approved 192×208 right frame**, with index `00` mirrored to `00` through `07` to `07`. Future atlas work must use these approved frames; do not replace them by re-extracting the packed decoded strip.

## Row QA

- Eight of eight left frames are pixel-exact horizontal mirrors of the same-index approved right frames. Their face, brown/cream palette, tail thickness, paw shapes and timing are unchanged except for intended direction reversal.
- Bounding-box top is `y=51–52`; bottom is `y=156` in every frame. No cell-edge pixels or frame size pop. The eight-frame [left GIF](previews/running-left.gif) keeps the right row's cadence and loop timing.
- [Right/left contact sheet](right-left-contact.png) and [64px comparison](right-left-64px.png) show the same calm, grounded otter gait in both directions. The only visible difference is horizontal reversal, including body-relative highlights.
- [Row inspection](running-left-review.json) has zero errors. Its inherited stable-slot warning was visually reviewed with no clipping. [Mirror comparison](mirror-comparison.json) confirms exact per-index reversal, zero transparent-pixel RGB residue, zero chroma-adjacent opaque pixels and zero purple spill.
- The approved rightward and idle source/frame hashes remained unchanged from the pre-derivation check.

**Gate: pass for `running-left` only.** The next production phase may plan the next distinct state after approval. No `waiting` or other row was started here.

# Vasu Phase 2B · Two-row trial review

Scope: `idle` (6 frames) and `running-right` (8 frames) only. The [Phase 1 contract](../../../../../docs/specs/vasu/SPEC.md) and [Phase 2A motion language](../../phase-2a-motion-language.md) remain unchanged. The original canonical portrait was copied byte-for-byte to `references/canonical-base.png`; the Phase 2A side pose guided movement silhouette only. Both generated strips used flat magenta `#FF00FF` chroma key, not generated transparency.

| Row | Extraction | Visual and motion QA | Result |
| --- | --- | --- | --- |
| `idle` | 6 component-extracted 192×208 frames | Planted paws and tail, stable frame size and baseline, small blink and visible quiet breath. Frame 00 works as a still; first/last poses settle smoothly. Canonical face, cream bib, brown fur, and thick tail stay recognizable at 64px. | Pass |
| `running-right` | 8 stable-slot 192×208 frames | Right-facing, short alternating grounded steps; attached thick tail and consistent head/chest mass. The final frames share bottom `y=156` and top `y=51–52`, with no edge pixels or visible size pop. The last pose returns near the first; 64px silhouette remains an otter. | Pass |

## Repairs and validation

1. Both initial strips had near-magenta background variation. Hatch extraction at key threshold 200 removed the key; a second deterministic key pass removed resized edge remnants. The remaining purple spill was identified by `blue > green + 10`, a hue absent from opaque canonical pixels, and removed from extracted frames. Visual review confirmed no lost whiskers or outline.
2. The first `running-right` strip had a genuinely compressed fourth pose (index 03). One full-row repair improved it but did not remove the dip. A focused image edit of that pose narrowed the source height difference to about two pixels while preserving the other seven poses. Stable-slot extraction then kept the common ground line without clipping. `idle` was never visually regenerated during this repair.
3. Row inspection reports zero errors. It retains one expected warning for the deliberate `running-right` stable-slot method, resolved by contact-sheet, GIF, and 64px visual review. All 14 exported frames have zero nonzero RGB in fully transparent pixels, zero `#FF00FF`-adjacent opaque pixels under the strict 200-distance check, and zero remaining purple-spill pixels by the canonical-palette rule.

## Review artifacts

- [Two-row contact sheet](contact-sheet-two-rows.png): top `idle`, bottom `running-right`.
- [64px comparison](contact-sheet-64px.png): canonical 64px master precedes each row.
- [Idle GIF](previews/idle.gif) and [running-right GIF](previews/running-right.gif).
- [Row-level machine review](row-review.json), [idle review](idle-review.json), and [frame manifest](../frames/frames-manifest.json).
- Source strips: [`idle`](../decoded/idle.png) and [`running-right`](../decoded/running-right.png). Extracted frames remain under `../frames/` for later row-specific repair.

**Gate:** Phase 2B passes for these two rows only. The next production step, if authorized, is to review whether the approved rightward gait can be mirrored safely for `running-left`, then produce the remaining Codex states individually. No left row, other animation row, or final atlas was made in this phase.

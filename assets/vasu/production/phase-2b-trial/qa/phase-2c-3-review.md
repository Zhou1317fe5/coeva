# Vasu Phase 2C-3 · `review` row review

**Gate: pass for `review` only.** Here `review` means Vasu quietly studying one point of interest in the shared environment. It does not review Agent output, code, task completion or the user's work. The Phase 1 state/frame mapping and reference hierarchy remain unchanged; only the row's art interpretation was aligned with this phase.

## Motion and comparison

- [Three-row contact sheet](idle-waiting-review-contact.png): top `idle` stays in its private breath/blink rhythm; middle `waiting` briefly notices the space; bottom `review` turns its gaze/head a little farther right and holds that attention through the middle poses before settling. This is a sustained, self-directed look rather than repeated scanning or a response to the user.
- [64px comparison](idle-waiting-review-64px.png): the canonical 64px master precedes each row. The focused direction remains legible while Vasu's small eyes, rounded muzzle, broad cream bib, compact brown body and thick attached tail remain recognizable.
- [Review GIF](previews/review.gif): six frames form a calm loop with planted paws and no full-body bounce, alert/surveillance stance, prop, UI or speech bubble.

## Production and QA

The one generated [source strip](../decoded/review.png) used built-in `image_gen` on opaque `#FF00FF` chroma, with the original canonical portrait as identity authority. The approved `waiting` strip was a size/baseline comparator only. Hatch extraction found six independent components. The same deterministic chroma and purple-spill cleanup used for approved rows produced [six 192×208 frames](../frames/review/). No visual regeneration was needed.

The [row validation](review-row-validation.json) has zero errors and warnings. Frame bounds remain x=5–187, y=16–191/192, matching idle/waiting; there is no visible size pop or baseline jump. All six frames have zero nonzero RGB in transparent pixels, zero chroma-adjacent opaque pixels, and zero purple-spill pixels. The GIF has six frames. Independent visual QA passed, and hashes of locked `idle`, `running-right`, `running-left`, and `waiting` source/frame files remained unchanged.

The row prompt is [`prompts/rows/review.md`](../prompts/rows/review.md); built-in image generation and deterministic extraction were the only production methods. No other row or final atlas was made.

**Next recommended state:** `running` as Vasu's own small purposeful activity, but first revise/lock the Phase 2A self-work pose so it cannot read as coding, serving, or an Agent progress cue. Do not begin without approval.

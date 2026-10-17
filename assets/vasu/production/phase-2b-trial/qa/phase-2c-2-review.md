# Vasu Phase 2C-2 · `waiting` row review

**Gate: pass for `waiting` only.** This six-frame row depicts Vasu pausing its own activity and quietly noticing the shared environment. It is awake, patient and self-possessed; it neither requests input nor seeks attention. The Phase 1 identity hierarchy and Codex row/frame mapping remain unchanged. The Phase 1 `waiting` description was aligned with this user-approved interpretation.

## Visual distinction and identity

- [Idle/waiting contact sheet](idle-waiting-contact.png): top `idle` breathes and blinks within its own rhythm; bottom `waiting` makes a slight sideward gaze/head-angle shift and settles. Paws stay planted and the tail remains thick and attached. There is no forward lean, wave, pleading expression or Agent-status cue.
- [64px comparison](idle-waiting-64px.png): the canonical 64px master precedes both rows. The awareness change remains readable without enlarged eyes or a new character silhouette. Rounded muzzle, cream bib, warm-brown fur and compact body remain Vasu.
- [Waiting GIF](previews/waiting.gif): six frames form one calm loop. The first and last poses are close; there is no full-body bounce or size pop.

## Repairs and validation

The first generated row passed basic extraction but was too tall and turned the whole face upward. A waiting-only regeneration still occupied roughly y203–539 in the 2172×724 source, about 11% taller than approved idle, and was rejected. A second waiting-only regeneration explicitly matched idle's source band (waiting y239–536; idle y238–537), with much smaller gaze changes. No approved `idle`, `running-right` or `running-left` art was regenerated or altered.

The accepted source [`decoded/waiting.png`](../decoded/waiting.png) was generated through built-in `image_gen` on opaque `#FF00FF` chroma. Hatch extraction found six independent components. The same deterministic chroma-key and purple-spill cleanup used in Phase 2B produced [six 192×208 frames](../frames/waiting/). The [row review](waiting-review.json) reports zero errors and warnings. Frame bounds are x=5–187 and y=16–191/192, matching the approved idle footprint; no cell-edge pixels. All six frames have zero nonzero RGB in transparent pixels, zero chroma-adjacent opaque pixels and zero purple-spill pixels. The GIF has six frames, and independent visual QA passed.

The generation prompt is [`prompts/rows/waiting.md`](../prompts/rows/waiting.md); targeted repairs are [`waiting-01.md`](../prompts/repairs/waiting-01.md) and [`waiting-02.md`](../prompts/repairs/waiting-02.md). Rejected source strips remain under `qa/` for traceability.

**Next recommended state:** `review`, to establish focused inspection as a separate quiet expression from idle and waiting. Do not begin it without approval. No other row or final atlas was made here.

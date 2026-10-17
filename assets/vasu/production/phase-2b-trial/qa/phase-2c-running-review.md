# Vasu Phase 2C · `running` as self-directed purposeful movement

**Gate: pass for `running` only.** The Codex-compatible state name remains `running`, but Vasu's present animation depicts Vasu deciding to go about its own small business. It does not indicate an Agent task, tool execution, user productivity or progress. This is an asset interpretation, not a change to the higher-level state contract; later art can replace the loop without redefining that contract.

## Phase 2A correction

The old self-work draft showed closed-eye forepaw grooming, which reads as sleepy at 64px and was never approved production art. [Phase 2A motion language](../../phase-2a-motion-language.md) now defines purposeful activity as a low, grounded step toward Vasu's own chosen place, open-eyed and without tools or work symbols. The accepted right-facing key pose supplied silhouette guidance only. No new static pose was needed; this six-frame trial tests the corrected meaning.

## Visual comparison

- [Four-row contact sheet](quiet-vs-running-contact.png), top to bottom: `idle` breath/blink; `waiting` mild shared-space awareness; `review` sustained focus on one point; `running` grounded movement toward Vasu's own destination. The first three remain planted seated loops; the last has alternating short steps and a forward self-chosen gaze.
- [64px comparison](quiet-vs-running-64px.png) places the canonical master before each row. Vasu's cream muzzle and bib, small eye, compact warm-brown body and thick attached tail remain recognizable in the moving pose.
- [Running GIF](previews/running.gif) shows six calm steps, with planted paw beats and no sprint, body bounce, tools, code, UI, question mark, speech bubble or Agent-status cue. Its walk is visually close to the approved eight-frame `running-right` drag gait. The distinct meaning comes from state context and Vasu's own activity, so the animation remains replaceable later without changing the state contract.

## Production and QA

The one selected [source strip](../decoded/running.png) was generated through built-in `image_gen` on opaque `#FF00FF` chroma with the original canonical portrait as identity authority. Hatch extraction found six independent components. Deterministic chroma cleanup yielded [six 192×208 frames](../frames/running/); no visual regeneration after the selected source was required.

The [row validation](running-row-validation.json) reports zero errors and warnings. Frame bounds stay within x=5–187 and y=50–158, without edge clipping or visible size pop. All six frames have zero nonzero RGB in transparent pixels, zero chroma-adjacent opaque pixels and zero purple-spill pixels. The GIF has six frames; independent visual QA passed. Hashes of locked `idle`, `running-right`, `running-left`, `waiting` and `review` source/frame files remained unchanged.

The [production prompt](../prompts/rows/running.md) records this phase's Vasu-specific interpretation. No other row or final atlas was made.

# Vasu Phase 2C · `failed` review

**Gate: pass for `failed` only.** This row means one of Vasu's own small intentions did not work. It shows mild puzzlement and tiny disappointment, then emotional recovery. It does not represent Agent execution, tool, user or system failure.

## Visual review

- [Idle/waiting/failed contact sheet](idle-waiting-failed-contact.png): the failed row starts neutral, notices the miss, lowers its head/ears slightly, compresses briefly, then returns toward calm. It remains separate from waiting's quiet availability.
- [64px comparison](idle-waiting-failed-64px.png): the small eyes, rounded muzzle, cream bib, warm-brown palette and attached tail remain Vasu. The emotion reads through posture and gaze, without tears, symbols, UI or dramatic collapse.
- [Failed GIF](previews/failed.gif): the eight-frame arc recovers rather than staying stuck. The final poses settle calmly.

## Repairs and QA

The first candidate had correct semantics but was too large against approved idle/waiting, and its middle frames created a scale pop. A failed-only repair softened the head turns and disappointment, then a full failed-only scale repair matched the quiet-row body band while retaining the emotional timing. No approved row was regenerated.

The final [source strip](../decoded/failed.png) used opaque `#FF00FF` chroma. Stable-slot extraction preserved the common planted lower edge; the final [eight 192×208 frames](../frames/failed/) pass [row validation](failed-row-validation.json) with zero errors and no warnings. All frames have zero transparent-pixel RGB residue, zero chroma-adjacent opaque pixels and zero purple spill. Independent visual QA found no tears, panic, error symbols, Agent/user failure cues, clipping or identity drift.

Hashes of approved `idle`, `running-right`, `running-left`, `waiting`, `review`, `running`, `waving` and `jumping` remained unchanged. No other row or final atlas was made.

**All nine hatch-pet core rows are now ready for a future final-atlas composition step, pending separate approval.**

# Vasu Phase 2C · `waving` review

**Gate: pass for `waving` only.** The row depicts a short companion acknowledgment: Vasu notices the user's presence, lifts one forepaw close to its chest for a small peak, then returns to its own quiet life. It is an occasional relational event, not repeated mascot waving, command waiting, celebration, begging or Agent progress.

## Visual review

- [Idle/waiting/waving contact sheet](idle-waiting-waving-contact.png): the first two rows remain seated quiet states; waving adds one small forepaw gesture while keeping the body planted and the tail attached.
- [64px comparison](idle-waiting-waving-64px.png): the paw lift remains readable at pet size. Eyes, muzzle, bib, ears, body mass and warm-brown palette remain canonical. No broad grin, wide eyes, both-paws-up or saluting posture.
- [Waving GIF](previews/waving.gif): four-beat progression is baseline/notice → one-paw lift → restrained acknowledgment peak → return/settle. The final frame is close to the starting footprint.

The first component-extraction preview had an artificial size dip in frame 02 because its visible component was smaller. The source strip itself shared a common baseline; re-extracting with hatch-pet's deliberate `stable-slots` method preserved a consistent body range and the intended paw gesture. A visual review then found an apparent extra forepaw in the raised-paw frames: both front paws were still grounded while a third appeared lifted. A waving-only image edit corrected frames 01–02 so exactly one forepaw is planted and the other is lifted from the shoulder/chest; frames 00 and 03 remain baseline poses. The accepted row uses the stable-slot frames from that corrected strip. No approved row was regenerated.

## QA

The selected [source strip](../decoded/waving.png) used built-in `image_gen` with opaque `#FF00FF` chroma. The final [four 192×208 frames](../frames/waving/) have zero validation errors, zero cell-edge pixels, zero transparent-pixel RGB residue, zero chroma-adjacent opaque pixels and zero purple spill. The [row validation](waving-row-validation.json) has only the expected stable-slot review warning, resolved by contact-sheet, GIF and 64px inspection. Independent visual QA explicitly confirmed one planted forepaw plus one lifted forepaw in frames 01–02; no duplicate third forepaw remains.

Hashes of approved `idle`, `running-right`, `running-left`, `waiting`, `review` and `running` source/frame files stayed unchanged. No other row or final atlas was produced.

**Next recommended state:** `jumping`, if approved. Keep its amplitude small and treat it as Vasu's own brief play rather than task-success feedback.

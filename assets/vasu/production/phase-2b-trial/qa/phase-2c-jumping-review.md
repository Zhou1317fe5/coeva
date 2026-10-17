# Vasu Phase 2C · `jumping` review

**Gate: pass for `jumping` only.** This row depicts one small spontaneous hop because Vasu feels playful, unrelated to Agent completion, user productivity or task success. The five beats are preparation, slight crouch, compact airborne peak, grounded landing and calm settle.

## Visual review

- [Idle/waving/jumping contact sheet](idle-waving-jumping-contact.png): jumping is visibly separate from the seated quiet rows and does not borrow their relational gesture. It has one low hop, not repeated bouncing.
- [64px comparison](idle-waving-jumping-64px.png): Vasu remains recognizable in the airborne frame through its small calm face, cream muzzle/bib, short legs and thick tail. The airborne body stays compact and mature-cute.
- [Jumping GIF](previews/jumping.gif): the preparation and landing carry weight, the peak is restrained, and the final frame returns close to baseline. The tail reacts upward for balance but remains attached and consistent.

## Production and QA

The selected [source strip](../decoded/jumping.png) used built-in `image_gen` with opaque `#FF00FF` chroma. Component extraction showed strong vertical pose changes, so hatch-pet's deliberate `stable-slots` extraction preserved one consistent observation window instead of resizing each visible component independently. The final [five 192×208 frames](../frames/jumping/) have zero validation errors, zero cell-edge pixels, zero transparent-pixel RGB residue, zero chroma-adjacent opaque pixels and zero purple spill. The [row validation](jumping-row-validation.json) contains only the expected stable-slot review warning, resolved by visual review.

Independent visual QA found no celebration, Agent/status, wide-eye, giant-smile, prop, symbol, shadow, clipping or repeated-bounce issue. Hashes of approved `idle`, `running-right`, `running-left`, `waiting`, `review`, `running` and `waving` files remained unchanged. No other row or final atlas was made.

**Next recommended state:** `failed`, if approved, with a quiet deflated reaction that does not turn tool failure into Vasu's failure.

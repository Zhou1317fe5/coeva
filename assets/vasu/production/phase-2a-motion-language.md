# Vasu · Phase 2A Motion Language and Key Pose Review

This is a static pose study for [the locked Phase 1 contract](../../../docs/specs/vasu/SPEC.md). The identity and reference order remain unchanged: `vasu-canonical.png` defines the character; `vasu-pixel-master-64.png` checks small-scale reading; `vasu-companion-board.png` contributes only mood and action ideas. These studies are not animation frames or atlas cells.

## Motion grammar

- Keep the torso compact and weight low. Small, short-legged steps carry the body horizontally; the head and chest do not bounce independently. Plant at least one paw in the locomotion base.
- Retain the canonical rounded head, small ears and eyes, short cream muzzle, broad cream bib, warm-brown fur, and thick tapering otter tail in every pose. The face changes through a small gaze shift or eyelid change, not new eye or mouth geometry.
- Start directional drawing facing right. The tail trails behind the body in profile; its attachment and thickness must remain clear. Draw markings and shading so a future left-facing mirror is plausible, then inspect the actual right-facing study before authorizing a mirror.
- Let actions start and settle in nearly the same footprint. Use paw, gaze, head, and tail changes before moving the whole body. No motion lines, symbols, detached effects, floor shadow, costume, programmer tools, or attention-seeking gestures.
- Most moments should read as quiet co-presence. Observation is subtle, response is brief, and play belongs to Vasu's own life rather than a user's task outcome.

## Six static key poses

| Pose | Locked key drawing | Distinguishing read | Avoid |
| --- | --- | --- | --- |
| Right-facing standing / locomotion base | Low, slightly elongated side silhouette; short planted legs; thick tail extending behind; calm head facing right. | An otter ready to take an unhurried step. | Upright mascot stance, long-legged run, bouncing, skinny or disconnected tail. |
| Observe | Mostly planted body; a slight head or gaze lift toward the surroundings. | Quiet curiosity without urgency. | Wide eyes, alert icon posture, surveillance or Agent-status look. |
| Self-work | Forepaws occupied with a small purposeful self-grooming action; no object required. | Vasu tending to its own life. | Coding, tool props, serving the user, frantic paw movement. |
| Rest | Settled low with relaxed shoulders, half-open eyes and a comfortably supported head. | Awake and at ease, distinct from sleep. | Closed eyes, `zzz`, bed or blanket, collapsed/sad posture. |
| Play | Brief low crouch and a small self-directed tail glance or paw reach. | Private curiosity and light amusement. | Victory jump, confetti, grin, oversized bounce, invitation to watch. |
| Relate / respond | A glance toward the user and one small paw or head acknowledgment, then settle. | Friendly recognition within shared life. | Repeated wave, begging, saluting, speech bubble, eager helper stance. |

Exploration is not a seventh key pose in this phase. Its later motion can combine the right-facing grounded step with the quiet gaze of Observe; it should not become a constant search animation.

## Review gate

Compare every candidate against the canonical face, bib shape, body mass, tail and fur palette. At 64-pixel scale, the otter silhouette, cream face/chest, short ears and thick tail must still separate cleanly. Reject any pose that reads as a different otter, a mascot, a servant, an Agent status indicator, or an exaggerated emotional reaction. Record visual findings below after inspecting the study.

## Visual review · Phase 2A

- [Six-pose draft](phase-2a-six-pose-draft.png): one still for each category, ordered left to right across two rows. This is a concept sheet, not production sprite art; the transparent image has a visible soft brown fringe around some silhouettes.
- [Six poses at 64 pixels](phase-2a-64px-qa.png): the canonical 64×64 master is first, then the six draft poses in the same order. This preview keeps the study's relative sizes.
- [Focused right-facing base](phase-2a-right-facing-base.png) and [64-pixel comparison](phase-2a-right-facing-64px-qa.png): the latter shows the canonical 64×64 master on the left and the proposed side pose on the right, scaled to fit a 64×64 cell.

| Pose | Review decision |
| --- | --- |
| Right-facing standing / locomotion base | **Motion anchor accepted for Phase 2B trials.** The focused study corrects the first sheet's overlong torso and pointed muzzle. Short planted legs and a thick attached tail read clearly at 64 pixels. Keep the canonical smaller calm eyes, rounded muzzle and restrained mouth when drawing animation frames; this still is a guide, not a finished frame. |
| Observe | **Revise before its own animation.** The draft lifts the whole chest and looks alert. Keep the body planted; move only gaze and a little head angle. |
| Self-work | **Revise before its own animation.** Forepaw grooming is a prop-free purposeful action, but the closed eyes read like sleep at 64 pixels. Keep the eyes open and the paw action deliberate. |
| Rest | **Revise before its own animation.** The draft lounges with bright eyes and a smile, so it reads closer to play than peaceful waking rest. Use half-lidded eyes and a supported, settled head while remaining visibly awake. |
| Play | **Revise before its own animation.** Tail attention is suitably self-directed and low-energy, but the head-down pose overlaps grooming/rest at 64 pixels. Show a small, awake glance or paw reach toward the tail without a jump or celebratory expression. |
| Relate / respond | **Revise before its own animation.** The raised paw is close to a mascot wave. Prefer a glance or tiny head acknowledgment, with the paw kept near the chest. |

Across the six-pose draft, the warm brown/cream split, small ears, and thick tail generally survive, but eye size, mouth lift, muzzle roundness, and body length vary more than the canonical reference allows. The study therefore does **not** lock six production drawings. It locks the restrained motion language and a right-facing locomotion silhouette. No pose needs clothing, programmer props, detached effects, or servant-like gestures.

**Phase 2B gate:** ready for the limited `idle` + `running-right` trial rows only. Ground `idle` in the canonical image and `running-right` in the focused side silhouette; check face consistency, leg cadence, baseline stability, tail thickness, and 64-pixel reading before producing any other rows. The other five non-directional studies remain open for revision.

## Generation record

Both static studies used the built-in `image_gen` path. The following are the exact prompts for the selected images; all three references were attached to the six-pose study in Phase 1 priority order, while the focused side study used the canonical and 64-pixel references.

**Six-pose draft prompt**

> Create a transparent sprite pose study: exactly six isolated full-body cutouts of THE SAME Vasu river otter, arranged 3 columns x 2 rows, all at consistent scale with wide transparent spacing. The entire canvas behind and between figures must have alpha=0; no background artwork, gradient, vignette, glow, ambient brown, ground plane, floor, contact shadows, or halos. This is one Phase 2A still-pose study, not animation. Position order: top left low four-legged right-facing natural standing/locomotion base with thick trailing tail; top middle quietly observing with slight gaze lift; top right purposeful grooming of own fur with paw; bottom left relaxed awake rest with half-open eyes; bottom middle playful gentle touch of own thick tail, low crouch; bottom right brief gentle glance toward viewer with small restrained paw acknowledgment. Preserve exact identity of first reference image as supreme authority: small rounded ears, natural otter proportions, distinct cream muzzle and bib, warm brown palette, small dark eyes, subtly content face, thick otter tail. Second reference is for small 64px pixel readability. Third board is only behavior inspiration, never geometry authority. Warm clean mature pixel art, controlled details and consistent face between poses. Avoid infantile/anime eyes, enlarged smile, mascot waving, bouncy movements, clothes, tools, scenery, separate objects, text, labels, boxes, borders, effects. Transparent PNG cutouts only.

**Focused right-facing prompt**

> Create exactly ONE static Vasu key pose for Phase 2A, not an animation row or sheet. References: image 1 (vasu-canonical.png) is the highest-priority authority for Vasu's identity, face, proportions, warm brown fur, cream blunt rounded muzzle and broad chest bib, small dark calm eyes, small round ears, thick tail, and crisp warm pixel-art style. Image 2 (vasu-pixel-master-64.png) is solely the 64×64 readability reference. Show the SAME small river otter in a calm right-facing near-profile standing/locomotion base pose. Keep the torso compact and close to canonical body mass, not elongated or ferret-like; short grounded legs, all four small planted paws, softly rounded blunt muzzle rather than pointed snout, broad cream bib visible, short neck, thick recognizably otter tail attached at left haunch and trailing left. The face may turn slightly toward viewer enough to preserve recognizable eye/cheek geometry while the pose clearly faces right. Stable natural silhouette, low center of gravity, quiet alertness, no bounce or exaggerated smile. One centered full-body sprite with ample clear margin, genuinely transparent background/alpha. No other poses or characters, no props, clothing, text, shadows, glow, floor patch, background scenery, motion effects, or scene panels.

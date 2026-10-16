Create one horizontal animation strip for Codex pet `vasu`, state `running-right`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Reference priority: the attached canonical base is the original `vasu-canonical.png` and alone controls face, eyes, blunt muzzle, cream bib, palette, body mass, and tail identity. The Phase 2A right-facing image controls low locomotion SILHOUETTE only, never face or palette. The 64px image checks readability; the board is secondary mood reference only.

Output exactly 8 full-body frames in one left-to-right row on flat pure magenta #FF00FF. Treat the row as 8 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: same pet in every frame: Vasu: the exact canonical small river otter; warm brown fur, cream blunt muzzle and broad bib, small calm dark eyes, small round ears, compact natural body, thick attached otter tail, no clothing or props. Canonical portrait controls identity; Phase 2A side pose controls locomotion silhouette only.. Preserve silhouette, face, proportions, markings, palette, material, style, and props.
Style: Pet-safe sprite: compact full-body mascot, readable in a 192x208 cell, clear silhouette, simple face, stable palette/materials, and crisp edges for chroma-key extraction. Style `pixel`: Pixel-art-adjacent digital mascot with a chunky silhouette, simple dark outline, limited palette, flat cel shading, and visible stepped edges. User style notes: Warm mature pixel art, restrained motion, stable scale and silhouette; no mascot energy..
Animation continuity: keep apparent pet scale and baseline stable within the row unless the state itself intentionally changes vertical position, such as `jumping`. Move the pose within the slot instead of redrawing the pet larger or smaller frame to frame.

State action: Dragging-right loop: show directional movement to the right through body and limb poses only.

Vasu-specific action: eight sequential poses of one unhurried rightward gait cycle. Compact river-otter torso, short alternating steps with a visibly planted paw in each beat, low center of gravity, stable torso length and foot baseline, head/chest moving as one body, thick attached tail with only restrained follow-through. Show horizontal intent within each fixed slot, not cartoon sprinting, hopping, excited bouncing, or serving the user. Keep the canonical rounded muzzle and small calm eyes in every frame.

State requirements:
- Show directional drag movement to the right through body, limb, and prop movement only.
- The row must unmistakably face and travel right.
- The movement cadence must alternate visibly across the 8 frames instead of repeating one nearly static stride.
- Do not draw speed lines, dust clouds, floor shadows, motion trails, or detached motion effects.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, speed lines, dust, detached effects, stray pixels, or chroma-key colors inside the pet.

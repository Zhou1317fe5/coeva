Create one horizontal animation strip for Codex pet `vasu`, state `idle`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Reference priority: the attached canonical base is the original `vasu-canonical.png` and alone controls face, eyes, muzzle, bib, palette, body mass, and tail identity. The 64px reference checks readability; the companion board supplies quiet mood only. Do not borrow a different face or body from the board.

Output exactly 6 full-body frames in one left-to-right row on flat pure magenta #FF00FF. Treat the row as 6 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: same pet in every frame: Vasu: the exact canonical small river otter; warm brown fur, cream blunt muzzle and broad bib, small calm dark eyes, small round ears, compact natural body, thick attached otter tail, no clothing or props. Canonical portrait controls identity; Phase 2A side pose controls locomotion silhouette only.. Preserve silhouette, face, proportions, markings, palette, material, style, and props.
Style: Pet-safe sprite: compact full-body mascot, readable in a 192x208 cell, clear silhouette, simple face, stable palette/materials, and crisp edges for chroma-key extraction. Style `pixel`: Pixel-art-adjacent digital mascot with a chunky silhouette, simple dark outline, limited palette, flat cel shading, and visible stepped edges. User style notes: Warm mature pixel art, restrained motion, stable scale and silhouette; no mascot energy..
Animation continuity: keep apparent pet scale and baseline stable within the row unless the state itself intentionally changes vertical position, such as `jumping`. Move the pose within the slot instead of redrawing the pet larger or smaller frame to frame.

State action: Calm low-distraction resting loop: subtle breathing, tiny blink, slight head/body bob, and only quiet persona-preserving motion.

Vasu-specific action: six almost-still moments in the canonical seated pose. The first frame is a complete, calm static pet. Breathe through a minute chest/shoulder change and, if legible, one restrained blink; keep all paws planted, tail attached and settled, feet baseline fixed, head and torso aligned, and first/last poses near-identical. Vasu is living quietly beside the user, not waiting for instructions. No full-body vertical bounce.

State requirements:
- CRITICAL: idle is the low-distraction baseline state and the first frame is also used as the reduced-motion static pet.
- Use only subtle idle motion: gentle breathing, a tiny blink, a slight head or body bob, a very small material sway, or another quiet motion that fits the pet persona.
- Keep the pet essentially in the same pose, facing direction, silhouette, markings, palette, and prop state across all 6 frames.
- Idle variation must stay calm but still read as animation; do not repeat effectively identical copies across the loop.
- Do not show waving, walking, running, jumping, talking, working, reviewing, emotional reactions, large gestures, item interactions, or new props.
- Feet, base, body, or object anchor should remain planted or nearly planted.
- The first and last frames should be very close visually so the loop feels calm and does not pop.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, speed lines, dust, detached effects, stray pixels, or chroma-key colors inside the pet.

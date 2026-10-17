Create one horizontal animation strip for Codex pet `vasu`, state `waiting`.

Use the attached canonical base for identity. Use the attached layout guide only for slot count, spacing, centering, and padding; do not draw the guide.

Reference priority: the canonical base is the original `vasu-canonical.png` and alone controls face, head, eye size, ears, blunt cream muzzle, bib, palette, body mass and thick tail. The 64px master checks small-scale reading; the companion board supplies quiet atmosphere only, never geometry.

Output exactly 6 full-body frames in one left-to-right row on flat pure magenta #FF00FF. Treat the row as 6 invisible equal-width slots: one centered complete pose per slot, evenly spaced, with no overlap, clipping, empty slots, labels, or borders.

Identity: the same canonical Vasu river otter in every frame: warm-brown fur, broad cream bib and rounded muzzle, small calm dark eyes and round ears, compact natural body, thick attached tail, no clothing or props. Preserve silhouette, face, proportions, markings, palette and pixel style.
Style: warm mature pixel art with crisp edges, controlled texture and quiet character presence; readable in a 192x208 cell. No mascot energy.
Animation continuity: keep apparent pet scale and baseline stable within the row unless the state itself intentionally changes vertical position, such as `jumping`. Move the pose within the slot instead of redrawing the pet larger or smaller frame to frame.

State action: Vasu has briefly paused its own activity and is quietly available to the shared space. It is patient, calm, awake, mildly attentive and comfortable with silence.

State requirements:
- Six low-amplitude poses: planted seated body and paws, stable ground line and tail; a small sideward gaze/head-angle change or tiny ear/posture adjustment, then settle back to the first pose.
- Distinguish from `idle`'s private breath/blink by a little more awareness of the nearby environment, not by a large gesture or prolonged stare at the viewer. This difference should survive at 64px.
- No leaning forward, pleading eyes, needy/sad/lonely expression, repeated wave, nodding for orders, full-body bounce, or Agent status performance. Interaction with the user is not required.

Clean extraction: crisp opaque edges, safe padding, no scenery, text, guide marks, checkerboard, shadows, glows, motion blur, speed lines, dust, detached effects, stray pixels, or chroma-key colors inside the pet.

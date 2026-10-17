# Vasu Core v0.1 · Phase 3 production review

**Result: PASS.** The nine approved Vasu core rows are frozen and composed into the Codex-compatible atlas without redrawing, re-extracting, recoloring, resizing, or changing any approved frame.

## Frozen inputs

- Source run: `D:\CodeProjects\co-evolving-companion\assets\vasu\production\phase-2b-trial`
- Exact approved rows: `idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, `review`.
- `running-left` uses the approved per-frame horizontal mirrors in `frames/running-left/`, preserving frame order.
- `failed` uses the approved timing refinement: `[160, 150, 180, 260, 220, 150, 140, 260]` ms per frame, total `1520` ms. Its eight visual frames are unchanged.
- Freeze evidence: [hash-freeze-manifest](hash-freeze-manifest.json), [post-freeze check](hash-postfreeze-check.json), [frame manifest](frame-manifest.json).

## Atlas and package

- Atlas: `1536×1872`, 8 columns × 9 rows, cells `192×208`.
- Row order: `idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, `review`.
- Used cells: `57`; unused cells: `15`, all fully transparent.
- Release files: [spritesheet.webp](../final/spritesheet.webp) and [pet.json](../final/pet.json).
- Repository core package: `D:\CodeProjects\co-evolving-companion\assets\vasu\core`.
- Codex package staged at: `C:\Users\Admin\.codex\pets\vasu`.

## Deterministic QA

- [Atlas validation](../final/validation.json): pass, zero errors, `1536×1872`, zero transparent RGB residue.
- [Frame inspection](review.json): pass, zero errors; five existing `stable-slots` warnings were reviewed and accepted because those rows were deliberately frozen with stable baselines.
- [Atlas frame equivalence](atlas-frame-equivalence.json): all 57 used cells are pixel-exact copies of the approved frame files.
- [PNG/WebP equivalence](atlas-equivalence.json): zero pixel differences; package copies match.
- [GIF previews](previews/): all nine rows present with expected frame counts; `failed.gif` retains the refined timing.
- [64px full-state contact sheet](contact-sheet-64px.png): all states remain recognizable as Vasu.

## Visual QA

Final visual QA returned `visual_qa=pass`: the same calm river-otter identity, palette, face, compact body and attached tail remain consistent across all rows; direction, semantics, baseline, scale and 64px readability are stable. No cropping, guide artifacts, chroma spill, detached effects, or Agent-status cues were found.

**Vasu Core v0.1 is ready for runtime installation/testing.** Coeva-specific extended animations remain outside this core atlas and were not started.

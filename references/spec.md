# Render specification

Use normalized image coordinates: `[0, 0]` is the top-left and `[1, 1]` is the bottom-right. The renderer accepts JSON with these fields.

## Core fields

```json
{
  "mode": "photo-overlay",
  "grid_style": "random",
  "grid_chance": 0.5,
  "variant": 0,
  "words": [
    {
      "text": "SILVER",
      "anchor": [0.66, 0.24],
      "orientation": "auto",
      "cluster": "wardrobe",
      "weight": 1.0,
      "evidence": "silver shoulder bag in the upper-right"
    },
    {
      "text": "PLEATS",
      "anchor": [0.48, 0.58],
      "orientation": "vertical",
      "weight": 0.8,
      "evidence": "pleated skirt at center"
    }
  ]
}
```

- `mode`: `photo-overlay`, `grid-board`, or `auto`. `auto` selects overlay for one input and board for several.
- `grid_style`: `random`, `full`, `none`, or `inherit`. The skill should normally write `random`; the input and variant then choose a reproducible grid state. `inherit` preserves legacy behavior: overlay has no full grid and board has a full grid.
- `grid_chance`: probability from `0` to `1` used only by `grid_style: random`; default `0.5`.
- `variant`: integer mixed into the input-derived seed. Keep it to reproduce a layout; increment it for alternatives.
- `words`: 6–12 entries is the useful range.
  - `text`: normally 3–14 letters or ideographs. Spaces and most punctuation are removed for grid placement. Prefer a shared writing system so crossings are possible.
  - `anchor`: optional normalized point near the evidence. This affects placement, not image cropping.
  - `orientation`: `auto`, `horizontal`, or `vertical`.
  - `cluster`: optional semantic-cluster name. Words only seek crossings within the same cluster. Use 2–3 clusters to distribute separate visual ideas around the frame; omit it when one connected word network is intentional.
  - `weight`: optional `0.1–2.0`; higher values place earlier.
  - `evidence`: optional audit note. It is not drawn.

## Art-direction fields

```json
{
  "title": "FOUND / WORN / KEPT",
  "caption": "A PERSONAL OBJECT INDEX",
  "grid_rows": 24,
  "color_square_density": 0.022,
  "paper_wash": 0.1,
  "word_opacity": 0.72,
  "grid_opacity": 0.26,
  "protect_regions": [[0.34, 0.08, 0.30, 0.34]],
  "image_panels": [
    {"image_index": 0, "box": [0.06, 0.12, 0.36, 0.34], "rotation": -2.0},
    {"image_index": 1, "box": [0.48, 0.26, 0.44, 0.55], "rotation": 1.5}
  ]
}
```

- `title` and `caption`: optional small editorial labels. They are not used as crossword words.
- `grid_rows`: 18–32. The column count follows the output aspect ratio.
- `color_square_density`: fraction of grid cells filled with accent colors; usually `0.015–0.032`.
- `paper_wash`: warm veil over a full-bleed photo; `0–0.3`.
- `word_opacity`: word-tile opacity; `0.5–0.9`.
- `grid_opacity`: full-grid line opacity whenever the chosen `grid_style` is `full`; `0–0.6`. The default is subtler over a full-bleed photo than on a paper board.
- `protect_regions`: normalized rectangles `[x, y, width, height]` where non-crossword accent squares should not appear. Use for faces, hands, product marks, and small critical details. Word anchors may still intentionally enter these regions.
- `image_panels`: optional in `grid-board`. Each normalized `box` places a source image in an irregular paper-like mask. Omit for automatic placement.

The optional `palette` object accepts `paper`, `ink`, `word_tiles` (array), and `accents` (array) as CSS hex colors. Preserve the restrained word-tile versus saturated-accent distinction.

## Content selection test

Before rendering, be able to point from each factual word to visible evidence or explicit user context. If the same word list could plausibly describe most unrelated portraits or products, it is too generic. Replace mood labels with concrete details such as material, gesture, object, silhouette, setting, or a user-supplied phrase.

# Image Crossword Collage

An open-source Codex skill and deterministic image compositor for turning personal photos into editorial crossword collages.

The visual system stays recognizable—square letter tiles, thin grid rules, translucent warm colors, and sparse saturated blocks—while the actual words, anchors, composition, crop, and random seed come from each input image. The result is a shared style, not a repeated template.

[中文说明](README.zh-CN.md)

## Model configuration

This package uses Doubao 2.0-lite for analysis and optional Seedream 5.0 Pro
for photographic generation. See [references/models.md](references/models.md) for the
endpoint configuration, separate environment variables and executable model entrypoints.
No API keys or private credential paths are included in this package.

## How it works

The project deliberately separates semantic decisions from precision graphics:

1. A vision-capable model inspects the user's image and writes a small JSON art-direction spec containing image-grounded words and normalized anchors.
2. `scripts/render_crossword_collage.py` lays out the crossword, typography, grid, photo panels, color blocks, grain, and export with Pillow.

The renderer derives its default seed from the source-image bytes, the semantic spec, and a variant number. The same inputs are reproducible; a new image or variant produces a new topology. With `grid_style: random`, that same seed also makes a reproducible choice between a full background grid and no background grid.

Reference artwork and user photos are not included in this repository.

## Install as a Codex skill

Place this repository at:

```text
~/.codex/skills/image-crossword-collage
```

Then invoke it with a source image:

```text
Use $image-crossword-collage to turn this photo into a personalized editorial crossword collage.
```

Codex desktop can use its bundled image runtime. For standalone CLI use, install the Python dependency:

```bash
python3 -m pip install -r requirements.txt
```

## CLI use

Create a JSON spec using `examples/example-spec.json` as a starting point, then run:

```bash
python3 scripts/render_crossword_collage.py \
  --input /absolute/path/photo.jpg \
  --spec examples/example-spec.json \
  --output result.png
```

Repeat `--input` for a multi-image board. Use `--mode photo-overlay` to preserve one full-bleed source photo or `--mode grid-board` for an off-white board with image panels. Set `grid_style` to `random` for seeded grid/no-grid variation, `full` to force grid lines, or `none` to suppress them. `--variant 1`, `--variant 2`, and so on create reproducible alternatives.

See [references/spec.md](references/spec.md) for the complete schema.

## Image-grounding rule

At least 70% of the words should describe directly visible objects, materials, colors, actions, or settings; no more than 30% should be inferred mood. A word list that could describe most unrelated photos is not specific enough. The optional `evidence` field records why each word was chosen without drawing that note into the image.

The compositor processes files locally and contains no network calls or telemetry.
The separate `scripts/ark_models.py` wrapper sends image previews to the configured Ark
model endpoints when invoked; see [references/models.md](references/models.md) before
sending sensitive images. Private `.env.*` key files must be excluded from every package.

## Development

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
```

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Security reports should follow [SECURITY.md](SECURITY.md).

## License

MIT. You remain responsible for having permission to use source images, fonts, names, and other content in generated work.

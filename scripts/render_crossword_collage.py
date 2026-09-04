#!/usr/bin/env python3
"""Render an image-grounded editorial crossword collage.

The model supplies semantic words and optional anchors in a JSON spec. This
script keeps typography and grid geometry deterministic and reproducible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFont, ImageOps
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Pillow is required. In Codex desktop, call load_workspace_dependencies "
        "and run this script with the returned Python executable."
    ) from exc


DEFAULT_PALETTE = {
    "paper": "#F2EEE7",
    "ink": "#111111",
    "word_tiles": ["#F2A36B", "#F08EA5", "#B697DF", "#F1B57A"],
    "accents": ["#F52516", "#00A8E5", "#F4E600", "#00C93A", "#050505"],
}


@dataclass
class Word:
    text: str
    anchor: tuple[float, float]
    orientation: str
    weight: float
    source_index: int
    cluster: str


@dataclass
class Placement:
    word: Word
    row: int
    col: int
    orientation: str
    crossings: int


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def hex_rgba(value: str, alpha: int = 255) -> tuple[int, int, int, int]:
    rgb = ImageColor.getrgb(value)
    return (rgb[0], rgb[1], rgb[2], alpha)


def normalize_word(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).upper()
    return "".join(char for char in text if char.isalnum())[:18]


def read_spec(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not read spec {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Spec root must be a JSON object.")
    if not isinstance(data.get("words"), list) or not data["words"]:
        raise SystemExit("Spec must contain a non-empty 'words' array.")
    return data


def stable_seed(inputs: list[Path], spec: dict[str, Any], variant: int) -> int:
    digest = hashlib.sha256()
    for path in inputs:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    semantic_spec = {key: value for key, value in spec.items() if key != "variant"}
    digest.update(json.dumps(semantic_spec, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    digest.update(str(variant).encode("ascii"))
    return int.from_bytes(digest.digest()[:8], "big")


def parse_words(spec: dict[str, Any], rng: random.Random) -> list[Word]:
    words: list[Word] = []
    for index, item in enumerate(spec["words"]):
        item = {"text": item} if isinstance(item, str) else item
        if not isinstance(item, dict):
            continue
        text = normalize_word(item.get("text", ""))
        if len(text) < 2:
            continue
        raw_anchor = item.get("anchor")
        if (
            isinstance(raw_anchor, list)
            and len(raw_anchor) == 2
            and all(isinstance(value, (int, float)) for value in raw_anchor)
        ):
            anchor = (clamp(float(raw_anchor[0]), 0.04, 0.96), clamp(float(raw_anchor[1]), 0.04, 0.96))
        else:
            angle = index * 2.3999632297 + rng.uniform(-0.3, 0.3)
            radius = 0.10 + 0.24 * math.sqrt((index + 1) / (len(spec["words"]) + 1))
            anchor = (
                clamp(0.5 + math.cos(angle) * radius, 0.08, 0.92),
                clamp(0.5 + math.sin(angle) * radius, 0.08, 0.92),
            )
        orientation = str(item.get("orientation", "auto")).lower()
        if orientation not in {"auto", "horizontal", "vertical"}:
            orientation = "auto"
        try:
            weight = clamp(float(item.get("weight", 1.0)), 0.1, 2.0)
        except (TypeError, ValueError):
            weight = 1.0
        raw_cluster = str(item.get("cluster", "default")).strip()
        cluster = raw_cluster[:40] if raw_cluster else "default"
        words.append(Word(text, anchor, orientation, weight, index, cluster))
    if not words:
        raise SystemExit("No usable words remain after normalization.")
    return sorted(words, key=lambda word: (-word.weight, -len(word.text), word.source_index))


def cell_for(placement: Placement, letter_index: int) -> tuple[int, int]:
    if placement.orientation == "horizontal":
        return (placement.row, placement.col + letter_index)
    return (placement.row + letter_index, placement.col)


def fits(
    text: str,
    row: int,
    col: int,
    orientation: str,
    rows: int,
    cols: int,
    occupied: dict[tuple[int, int], str],
) -> tuple[bool, int]:
    end_row = row + (len(text) - 1 if orientation == "vertical" else 0)
    end_col = col + (len(text) - 1 if orientation == "horizontal" else 0)
    if row < 0 or col < 0 or end_row >= rows or end_col >= cols:
        return (False, 0)
    crossings = 0
    for index, letter in enumerate(text):
        pos = (
            row + (index if orientation == "vertical" else 0),
            col + (index if orientation == "horizontal" else 0),
        )
        present = occupied.get(pos)
        if present is not None and present != letter:
            return (False, 0)
        crossings += int(present == letter)
    return (True, crossings)


def place_words(words: list[Word], rows: int, cols: int, rng: random.Random) -> list[Placement]:
    occupied: dict[tuple[int, int], str] = {}
    cluster_occupied: dict[str, dict[tuple[int, int], str]] = {}
    placements: list[Placement] = []
    for word in words:
        orientations = [word.orientation] if word.orientation != "auto" else ["horizontal", "vertical"]
        rng.shuffle(orientations)
        target_row = round(word.anchor[1] * (rows - 1) + rng.uniform(-1.6, 1.6))
        target_col = round(word.anchor[0] * (cols - 1) + rng.uniform(-1.6, 1.6))
        target_row = int(clamp(target_row, 0, rows - 1))
        target_col = int(clamp(target_col, 0, cols - 1))
        candidates: list[tuple[float, int, int, str, int]] = []

        local_occupied = cluster_occupied.get(word.cluster, {})
        if local_occupied:
            for letter_index, letter in enumerate(word.text):
                for (cross_row, cross_col), present in local_occupied.items():
                    if present != letter:
                        continue
                    for orientation in orientations:
                        row = cross_row - (letter_index if orientation == "vertical" else 0)
                        col = cross_col - (letter_index if orientation == "horizontal" else 0)
                        valid, crossings = fits(word.text, row, col, orientation, rows, cols, occupied)
                        if valid:
                            center_row = row + (len(word.text) - 1) * (orientation == "vertical") / 2
                            center_col = col + (len(word.text) - 1) * (orientation == "horizontal") / 2
                            distance = math.hypot(center_row - target_row, center_col - target_col)
                            score = distance - crossings * 4.5 + rng.random() * 0.9
                            candidates.append((score, row, col, orientation, crossings))

        if not candidates:
            for radius in range(max(rows, cols)):
                for orientation in orientations:
                    center_row = target_row + rng.randint(-radius, radius) if radius else target_row
                    center_col = target_col + rng.randint(-radius, radius) if radius else target_col
                    row = center_row - (len(word.text) // 2 if orientation == "vertical" else 0)
                    col = center_col - (len(word.text) // 2 if orientation == "horizontal" else 0)
                    valid, crossings = fits(word.text, row, col, orientation, rows, cols, occupied)
                    if valid:
                        score = radius + (5 if occupied and crossings == 0 else 0) + rng.random()
                        candidates.append((score, row, col, orientation, crossings))
                if candidates:
                    break

        if not candidates:
            continue
        _, row, col, orientation, crossings = min(candidates, key=lambda item: item[0])
        placement = Placement(word, row, col, orientation, crossings)
        placements.append(placement)
        for letter_index, letter in enumerate(word.text):
            position = cell_for(placement, letter_index)
            occupied[position] = letter
            cluster_occupied.setdefault(word.cluster, {})[position] = letter
    return placements


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def load_images(paths: list[Path]) -> list[Image.Image]:
    images: list[Image.Image] = []
    for path in paths:
        try:
            with Image.open(path) as source:
                images.append(ImageOps.exif_transpose(source).convert("RGBA"))
        except OSError as exc:
            raise SystemExit(f"Could not open input image {path}: {exc}") from exc
    return images


def irregular_panel(
    image: Image.Image,
    box: tuple[int, int, int, int],
    rotation: float,
    rng: random.Random,
) -> tuple[Image.Image, tuple[int, int]]:
    x, y, width, height = box
    panel = cover(image, (width, height))
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    jitter = max(3, round(min(width, height) * 0.025))
    polygon = [
        (rng.randint(0, jitter), rng.randint(0, jitter)),
        (width - 1 - rng.randint(0, jitter), rng.randint(0, jitter)),
        (width - 1 - rng.randint(0, jitter), height - 1 - rng.randint(0, jitter)),
        (rng.randint(0, jitter), height - 1 - rng.randint(0, jitter)),
    ]
    draw.polygon(polygon, fill=255)
    panel.putalpha(mask)
    if rotation:
        panel = panel.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
        x -= (panel.width - width) // 2
        y -= (panel.height - height) // 2
    return panel, (x, y)


def parse_box(raw: Any, width: int, height: int) -> tuple[int, int, int, int] | None:
    if not (isinstance(raw, list) and len(raw) == 4 and all(isinstance(v, (int, float)) for v in raw)):
        return None
    x, y, w, h = [float(v) for v in raw]
    if w <= 0 or h <= 0:
        return None
    return (
        round(clamp(x, 0, 1) * width),
        round(clamp(y, 0, 1) * height),
        max(1, round(clamp(w, 0.02, 1) * width)),
        max(1, round(clamp(h, 0.02, 1) * height)),
    )


def render_board_images(canvas: Image.Image, images: list[Image.Image], spec: dict[str, Any], rng: random.Random) -> None:
    width, height = canvas.size
    panels = spec.get("image_panels")
    configs = [item for item in panels if isinstance(item, dict)] if isinstance(panels, list) else []
    if not configs:
        if len(images) == 1:
            configs = [{"image_index": 0, "box": [0.16, 0.10, 0.68, 0.78], "rotation": rng.uniform(-2.2, 2.2)}]
        else:
            slots = [
                [0.04, 0.10, 0.30, 0.33],
                [0.35, 0.16, 0.34, 0.62],
                [0.70, 0.51, 0.27, 0.36],
                [0.08, 0.58, 0.25, 0.31],
            ]
            configs = [
                {"image_index": index, "box": slots[index % len(slots)], "rotation": rng.uniform(-3, 3)}
                for index in range(min(len(images), len(slots)))
            ]
    for index, config in enumerate(configs):
        try:
            image_index = int(config.get("image_index", index % len(images))) % len(images)
        except (TypeError, ValueError):
            image_index = index % len(images)
        box = parse_box(config.get("box"), width, height)
        if not box:
            continue
        try:
            rotation = clamp(float(config.get("rotation", 0)), -8, 8)
        except (TypeError, ValueError):
            rotation = 0
        panel, position = irregular_panel(images[image_index], box, rotation, rng)
        shadow = Image.new("RGBA", panel.size, (0, 0, 0, 0))
        shadow.putalpha(panel.getchannel("A").point(lambda value: round(value * 0.12)))
        canvas.alpha_composite(shadow, (position[0] + 5, position[1] + 7))
        canvas.alpha_composite(panel, position)


def find_font(
    font_path: str | None,
    size: int,
    prefer_cjk: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    system_candidates = [
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    if not prefer_cjk:
        system_candidates[0], system_candidates[1] = system_candidates[1], system_candidates[0]
    candidates = [font_path, *system_candidates]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def inside_regions(row: int, col: int, rows: int, cols: int, regions: Iterable[Any]) -> bool:
    x = (col + 0.5) / cols
    y = (row + 0.5) / rows
    for region in regions:
        if isinstance(region, list) and len(region) == 4:
            try:
                rx, ry, rw, rh = map(float, region)
            except (TypeError, ValueError):
                continue
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return True
    return False


def add_grain(image: Image.Image, rng: random.Random, strength: float = 0.035) -> None:
    if strength <= 0:
        return
    width, height = image.size
    noise_width = min(320, width)
    noise_height = max(1, round(noise_width * height / width))
    noise = Image.frombytes("L", (noise_width, noise_height), rng.randbytes(noise_width * noise_height))
    noise = noise.resize((width, height), Image.Resampling.BILINEAR)
    grain = Image.merge(
        "RGBA",
        (noise, noise, noise, Image.new("L", (width, height), round(255 * strength))),
    )
    image.alpha_composite(grain)


def draw_grid(layer: Image.Image, rows: int, cols: int, origin: tuple[int, int], cell: float, ink: str, opacity: float) -> None:
    draw = ImageDraw.Draw(layer)
    x0, y0 = origin
    color = hex_rgba(ink, round(255 * clamp(opacity, 0, 1)))
    line_width = max(1, round(cell * 0.025))
    for col in range(cols + 1):
        x = round(x0 + col * cell)
        draw.line((x, y0, x, round(y0 + rows * cell)), fill=color, width=line_width)
    for row in range(rows + 1):
        y = round(y0 + row * cell)
        draw.line((x0, y, round(x0 + cols * cell), y), fill=color, width=line_width)


def render(args: argparse.Namespace) -> dict[str, Any]:
    input_paths = [Path(value).expanduser().resolve() for value in args.input]
    for path in input_paths:
        if not path.is_file():
            raise SystemExit(f"Input image does not exist: {path}")
    spec = read_spec(Path(args.spec).expanduser().resolve())
    variant = args.variant if args.variant is not None else int(spec.get("variant", 0))
    seed = stable_seed(input_paths, spec, variant)
    rng = random.Random(seed)
    images = load_images(input_paths)

    mode = args.mode or str(spec.get("mode", "auto"))
    if mode == "auto":
        mode = "photo-overlay" if len(images) == 1 else "grid-board"
    if mode not in {"photo-overlay", "grid-board"}:
        raise SystemExit("Mode must be auto, photo-overlay, or grid-board.")

    requested_grid_style = str(spec.get("grid_style", "inherit")).lower()
    if requested_grid_style not in {"random", "full", "none", "inherit"}:
        raise SystemExit("grid_style must be random, full, none, or inherit.")
    if requested_grid_style == "inherit":
        grid_style = "full" if mode == "grid-board" else "none"
    elif requested_grid_style == "random":
        grid_chance = clamp(float(spec.get("grid_chance", 0.5)), 0, 1)
        grid_rng = random.Random(seed ^ 0x9E3779B97F4A7C15)
        grid_style = "full" if grid_rng.random() < grid_chance else "none"
    else:
        grid_style = requested_grid_style

    width = max(480, int(args.width))
    if args.height:
        height = max(480, int(args.height))
    else:
        ratio = images[0].height / images[0].width
        height = round(width * clamp(ratio, 0.62, 1.6))

    user_palette = spec.get("palette") if isinstance(spec.get("palette"), dict) else {}
    palette = {**DEFAULT_PALETTE, **user_palette}
    paper = str(palette["paper"])
    ink = str(palette["ink"])
    word_colors = list(palette["word_tiles"])
    accent_colors = list(palette["accents"])

    if mode == "photo-overlay":
        background = cover(images[0], (width, height))
        background = ImageEnhance.Contrast(background).enhance(0.96)
        background = ImageEnhance.Color(background).enhance(0.94).convert("RGBA")
        wash_alpha = round(255 * clamp(float(spec.get("paper_wash", 0.08)), 0, 0.35))
        background.alpha_composite(Image.new("RGBA", (width, height), hex_rgba(paper, wash_alpha)))
        canvas = background
    else:
        canvas = Image.new("RGBA", (width, height), hex_rgba(paper))

    rows = int(clamp(float(spec.get("grid_rows", 24)), 16, 36))
    cols = max(16, round(rows * width / height))
    cell = min(width / cols, height / rows)
    grid_width = cell * cols
    grid_height = cell * rows
    origin = (round((width - grid_width) / 2), round((height - grid_height) / 2))

    underlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if grid_style == "full":
        default_grid_opacity = 0.18 if mode == "photo-overlay" else 0.28
        draw_grid(
            underlay,
            rows,
            cols,
            origin,
            cell,
            ink,
            float(spec.get("grid_opacity", default_grid_opacity)),
        )
    canvas.alpha_composite(underlay)
    if mode == "grid-board":
        render_board_images(canvas, images, spec, rng)

    words = parse_words(spec, rng)
    placements = place_words(words, rows, cols, rng)
    occupied = {
        cell_for(placement, index)
        for placement in placements
        for index in range(len(placement.word.text))
    }

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    density = clamp(float(spec.get("color_square_density", 0.022)), 0, 0.08)
    square_count = round(rows * cols * density)
    available = [
        (row, col)
        for row in range(rows)
        for col in range(cols)
        if (row, col) not in occupied
        and not inside_regions(row, col, rows, cols, spec.get("protect_regions", []))
    ]
    rng.shuffle(available)
    for index, (row, col) in enumerate(available[:square_count]):
        x0 = round(origin[0] + col * cell)
        y0 = round(origin[1] + row * cell)
        inset = max(1, round(cell * (0.06 if mode == "photo-overlay" else 0.02)))
        color = accent_colors[index % len(accent_colors)]
        alpha = 215 if color.lower() not in {"#050505", "#000000"} else 245
        draw.rectangle(
            (x0 + inset, y0 + inset, round(x0 + cell) - inset, round(y0 + cell) - inset),
            fill=hex_rgba(color, alpha),
        )

    word_opacity = round(255 * clamp(float(spec.get("word_opacity", 0.72)), 0.35, 0.95))
    border = hex_rgba(ink, 150)
    border_width = max(1, round(cell * 0.025))
    has_non_ascii = any(ord(letter) > 127 for word in words for letter in word.text)
    font = find_font(args.font, max(10, round(cell * 0.57)), prefer_cjk=has_non_ascii)
    cell_owners: dict[tuple[int, int], tuple[str, int]] = {}
    for placement_index, placement in enumerate(placements):
        tile_color = word_colors[placement.word.source_index % len(word_colors)]
        for letter_index, letter in enumerate(placement.word.text):
            row, col = cell_for(placement, letter_index)
            x0 = round(origin[0] + col * cell)
            y0 = round(origin[1] + row * cell)
            x1 = round(origin[0] + (col + 1) * cell)
            y1 = round(origin[1] + (row + 1) * cell)
            owner = cell_owners.get((row, col))
            if owner is None:
                draw.rectangle(
                    (x0, y0, x1, y1),
                    fill=hex_rgba(tile_color, word_opacity),
                    outline=border,
                    width=border_width,
                )
                cell_owners[(row, col)] = (letter, placement_index)
            else:
                draw.rectangle(
                    (x0, y0, x1, y1),
                    fill=hex_rgba(tile_color, min(110, word_opacity // 2)),
                    outline=border,
                    width=border_width,
                )
            bbox = draw.textbbox((0, 0), letter, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            tx = x0 + (x1 - x0 - text_width) / 2 - bbox[0]
            ty = y0 + (y1 - y0 - text_height) / 2 - bbox[1] - cell * 0.02
            draw.text((round(tx), round(ty)), letter, font=font, fill=hex_rgba(ink, 245))

    title = str(spec.get("title", "")).strip()
    caption = str(spec.get("caption", "")).strip()
    labels_have_non_ascii = any(ord(letter) > 127 for letter in title + caption)
    label_font = find_font(
        args.font,
        max(10, round(cell * 0.33)),
        prefer_cjk=labels_have_non_ascii,
    )
    if title:
        title_bbox = draw.textbbox((0, 0), title, font=label_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_height = title_bbox[3] - title_bbox[1]
        title_x = origin[0] + round(cell * 0.18)
        title_y = max(8, origin[1] + round(cell * 0.18))
        title_box = (
            title_x - round(cell * 0.14),
            title_y - round(cell * 0.10),
            title_x + title_width + round(cell * 0.18),
            title_y + title_height + round(cell * 0.16),
        )
        draw.rectangle(title_box, fill=hex_rgba(paper, 220))
        draw.text(
            (title_x, title_y),
            title,
            font=label_font,
            fill=hex_rgba(ink, 245),
        )
    if caption:
        bbox = draw.textbbox((0, 0), caption, font=label_font)
        text_width = bbox[2] - bbox[0]
        draw.text(
            (max(8, width - text_width - round(cell * 0.35)), height - round(cell * 0.70)),
            caption,
            font=label_font,
            fill=hex_rgba(ink, 220),
        )

    canvas.alpha_composite(overlay)
    add_grain(canvas, rng, float(spec.get("grain", 0.025)))

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        canvas.convert("RGB").save(output_path, quality=94, subsampling=0)
    else:
        canvas.save(output_path, format="PNG", optimize=True)

    placed_words = [placement.word.text for placement in placements]
    return {
        "output": str(output_path),
        "mode": mode,
        "grid_style": grid_style,
        "variant": variant,
        "seed": seed,
        "canvas": [width, height],
        "grid": [cols, rows],
        "placed_words": placed_words,
        "skipped_words": [word.text for word in words if word.text not in placed_words],
        "placements": [
            {
                "text": placement.word.text,
                "cluster": placement.word.cluster,
                "row": placement.row,
                "col": placement.col,
                "orientation": placement.orientation,
                "crossings": placement.crossings,
            }
            for placement in placements
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="Source image path; repeat for multiple images")
    parser.add_argument("--spec", required=True, help="JSON render-spec path")
    parser.add_argument("--output", required=True, help="Output PNG or JPEG path")
    parser.add_argument("--mode", choices=["auto", "photo-overlay", "grid-board"], help="Override spec mode")
    parser.add_argument("--variant", type=int, help="Override spec variant")
    parser.add_argument("--width", type=int, default=1600, help="Output width in pixels")
    parser.add_argument("--height", type=int, help="Output height; default follows first input aspect ratio")
    parser.add_argument("--font", help="Optional TrueType/OpenType font path")
    return parser


if __name__ == "__main__":
    summary = render(build_parser().parse_args())
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    print()

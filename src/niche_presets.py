from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT_NICHE = "stickman_history"
SUPPORTED_VOICES = {"af_heart", "am_michael"}
PRESET_DIR = Path(__file__).resolve().parent.parent / "config" / "niches"
REQUIRED_FIELDS = {
    "display_name", "style_prefix", "character_look", "color_palette",
    "environment_hints", "action_directions", "negative_prompt",
    "fixed_seed", "caption_style", "default_voice",
}
CAPTION_FIELDS = {"font_size", "text_color", "outline_color", "position"}
POSITIONS = {"bottom_center", "top_center", "middle_center", "bottom_left", "top_left", "bottom_right", "top_right"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def available_niches() -> list[str]:
    """Return preset file stems in stable order."""
    return sorted(path.stem for path in PRESET_DIR.glob("*.json") if path.is_file())


def _validate_preset(name: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"Niche preset '{name}' must contain a JSON object.")
    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        raise ValueError(f"Niche preset '{name}' is missing required field(s): {', '.join(missing)}.")
    for field in ("display_name", "style_prefix", "character_look", "color_palette", "environment_hints", "negative_prompt"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(f"Niche preset '{name}' field '{field}' must be a non-empty string.")
    if not isinstance(data["action_directions"], list) or not 8 <= len(data["action_directions"]) <= 10:
        raise ValueError(f"Niche preset '{name}' field 'action_directions' must be a list of 8-10 non-empty strings.")
    if any(not isinstance(item, str) or not item.strip() for item in data["action_directions"]):
        raise ValueError(f"Niche preset '{name}' field 'action_directions' must contain only non-empty strings.")
    if isinstance(data["fixed_seed"], bool) or not isinstance(data["fixed_seed"], int):
        raise ValueError(f"Niche preset '{name}' field 'fixed_seed' must be an integer.")
    if not isinstance(data["default_voice"], str) or data["default_voice"] not in SUPPORTED_VOICES:
        raise ValueError(f"Niche preset '{name}' field 'default_voice' must be one of: {', '.join(sorted(SUPPORTED_VOICES))}.")
    data.setdefault("postprocess", False)
    if not isinstance(data["postprocess"], bool):
        raise ValueError(f"Niche preset '{name}' field 'postprocess' must be true or false.")
    caption = data["caption_style"]
    if not isinstance(caption, dict):
        raise ValueError(f"Niche preset '{name}' field 'caption_style' must be a JSON object.")
    missing_caption = sorted(CAPTION_FIELDS - set(caption))
    if missing_caption:
        raise ValueError(f"Niche preset '{name}' caption_style is missing field(s): {', '.join(missing_caption)}.")
    if isinstance(caption["font_size"], bool) or not isinstance(caption["font_size"], int) or not 8 <= caption["font_size"] <= 80:
        raise ValueError(f"Niche preset '{name}' caption_style.font_size must be an integer from 8 to 80.")
    for field in ("text_color", "outline_color"):
        if not isinstance(caption[field], str) or not HEX_COLOR.fullmatch(caption[field]):
            raise ValueError(f"Niche preset '{name}' caption_style.{field} must be a hex color such as #FFFFFF.")
    if not isinstance(caption["position"], str) or caption["position"] not in POSITIONS:
        raise ValueError(f"Niche preset '{name}' caption_style.position must be one of: {', '.join(sorted(POSITIONS))}.")
    for field, default in (("outline_width", 2), ("margin_v", 46)):
        if field in caption and (isinstance(caption[field], bool) or not isinstance(caption[field], int) or caption[field] < 0):
            raise ValueError(f"Niche preset '{name}' caption_style.{field} must be a non-negative integer.")
        caption.setdefault(field, default)
    return data


def load_niche_preset(name: str = DEFAULT_NICHE) -> dict[str, Any]:
    """Load and validate a niche preset, raising a clear ValueError for bad input or config."""
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]+", name):
        raise ValueError(f"Invalid niche name {name!r}. Use one of: {', '.join(available_niches())}.")
    path = PRESET_DIR / f"{name}.json"
    if not path.is_file():
        raise ValueError(f"Unknown niche preset '{name}'. Available niches: {', '.join(available_niches())}.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read niche preset '{name}' at {path}: {exc}") from exc
    return _validate_preset(name, data)


def build_scene_prompt(
    preset: dict[str, Any], topic: str, paragraph: str, index: int
) -> str:
    """Build a universal monochrome stickman scene; only the story action changes by niche."""
    directions = preset["action_directions"]
    direction = directions[index % len(directions)]
    clean = re.sub(r"\s+", " ", paragraph).strip()[:420]
    return (
        "FIXED UNIVERSAL VISUAL IDENTITY — keep identical across ALL niches and scenes: "
        "simple 2D stickman explainer drawing, pure white background (#FFFFFF), black ink lines only, "
        "monochrome black-and-white, clean bold hand-drawn black outlines, same simple round white head "
        "with black outline, tiny black facial features, thin black stick arms and legs, simple consistent "
        "body proportions, readable expressive pose. No color anywhere. "
        "Draw every object, prop, animal, building, landscape and historical detail as simple black line art "
        "on the same pure white background. Keep the main stickman recognizable and consistent in every frame. "
        "Niche must NEVER change the character shape, line-art style, monochrome palette, or white background. "
        f"Scene action: {direction}. "
        f"Story context guidance: {preset['environment_hints']} "
        "Illustrate the actual narration beat with one specific, dynamic action; vary poses and scene composition "
        "instead of repeating a static pose. Keep props and setting relevant to the narration and niche, "
        "but render them only as black line drawings. No color fills, colored clothing, colored props, gray wash, "
        "shading, gradients, textures, realistic images, vector-flat color art, or 3D. "
        "Do not draw written words, captions, labels, logos, borders, or watermarks inside the image. "
        f"Topic/niche: {topic}. Narration beat to illustrate: {clean}. "
        f"Avoid: {preset['negative_prompt']}, any color, colored background, colored objects, photorealism, "
        "3D, anime, glossy cartoon, detailed realistic anatomy."
    )

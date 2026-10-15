from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT_NICHE = "stickman_history"
SUPPORTED_VOICES = {"af_heart", "am_michael"}
ROOT_DIR = Path(__file__).resolve().parent.parent
PRESET_DIR = ROOT_DIR / "config" / "niches"
UNIVERSAL_STYLE_PATH = ROOT_DIR / "config" / "universal_style.json"
REQUIRED_FIELDS = {
    "display_name", "fixed_seed", "environment_hints", "action_directions",
    "default_voice", "caption_style", "clothing_hint",
}
OPTIONAL_FIELDS = {"postprocess"}
CAPTION_FIELDS = {"font_size", "text_color", "outline_color", "position"}
POSITIONS = {"bottom_center", "top_center", "middle_center", "bottom_left", "top_left", "bottom_right", "top_right"}
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
PROMPT_MAX_CHARS = 900
PROMPT_TARGET_CHARS = (500, 700)


def available_niches() -> list[str]:
    """Return preset file stems in stable order."""
    return sorted(path.stem for path in PRESET_DIR.glob("*.json") if path.is_file())


def load_universal_style() -> dict[str, str]:
    try:
        data = json.loads(UNIVERSAL_STYLE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read universal visual style at {UNIVERSAL_STYLE_PATH}: {exc}") from exc
    required = {"style_sentence", "character_definition", "color_rule", "exclusions", "prompt_tail", "negative_prompt"}
    if not isinstance(data, dict) or required - set(data):
        raise ValueError("Universal visual style is missing required fields.")
    if any(not isinstance(data[key], str) or not data[key].strip() for key in required):
        raise ValueError("Universal visual style fields must be non-empty strings.")
    return data


def _validate_preset(name: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"Niche preset '{name}' must contain a JSON object.")
    missing = sorted(REQUIRED_FIELDS - set(data))
    extra = sorted(set(data) - REQUIRED_FIELDS - OPTIONAL_FIELDS)
    if missing:
        raise ValueError(f"Niche preset '{name}' is missing required field(s): {', '.join(missing)}.")
    if extra:
        raise ValueError(f"Niche preset '{name}' contains unsupported field(s): {', '.join(extra)}.")
    for field in ("display_name", "environment_hints", "clothing_hint"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise ValueError(f"Niche preset '{name}' field '{field}' must be a non-empty string.")
    if not isinstance(data["action_directions"], list) or not 8 <= len(data["action_directions"]) <= 10:
        raise ValueError(f"Niche preset '{name}' field 'action_directions' must be a list of 8-10 non-empty strings.")
    if any(not isinstance(item, str) or not item.strip() for item in data["action_directions"]):
        raise ValueError(f"Niche preset '{name}' field 'action_directions' must contain only non-empty strings.")
    if any(re.search(r"\b(group of stickmen|crowd of stickmen|two stickmen)\b", item, re.I) for item in data["action_directions"]):
        raise ValueError(f"Niche preset '{name}' action directions must center one main stickman.")
    if isinstance(data["fixed_seed"], bool) or not isinstance(data["fixed_seed"], int):
        raise ValueError(f"Niche preset '{name}' field 'fixed_seed' must be an integer.")
    if not isinstance(data["default_voice"], str) or data["default_voice"] not in SUPPORTED_VOICES:
        raise ValueError(f"Niche preset '{name}' field 'default_voice' must be one of: {', '.join(sorted(SUPPORTED_VOICES))}.")
    if "postprocess" in data and not isinstance(data["postprocess"], bool):
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
    _validate_preset(name, data)
    load_universal_style()
    return data


def _shorten_beat(paragraph: str, fallback: str) -> str:
    """Reduce a narration beat to its first key sentence without mutating stored narration."""
    clean = re.sub(r"(?im)^\s*(?:#{1,6}\s*)?(?:scene\s+\d+\s*[-—:]?[^\n]*|\[scene[^\]]*\])\s*$", " ", paragraph)
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean:
        clean = fallback
    sentence = re.split(r"(?<=[.!?])\s+", clean, maxsplit=1)[0].strip()
    sentence = sentence[:140].rsplit(" ", 1)[0].rstrip(" ,;:") if len(sentence) > 140 else sentence
    return sentence or fallback


def build_scene_prompt(preset: dict[str, Any], topic: str, paragraph: str, index: int) -> str:
    """Build a compact shared-style prompt; narration is only shortened for image prompting."""
    style = load_universal_style()
    directions = preset["action_directions"]
    direction = directions[index % len(directions)]
    beat = _shorten_beat(paragraph, direction)
    clothing = re.sub(r"\s+", " ", preset["clothing_hint"]).strip().rstrip(" .")
    environment = re.sub(r"\s+", " ", preset["environment_hints"]).strip().rstrip(" .")
    environment = environment[:115].rsplit(" ", 1)[0] if len(environment) > 115 else environment
    prompt = (
        f"{style['style_sentence']} "
        f"Clothing: {clothing}. "
        f"Action: {beat} "
        f"Setting: {environment}. "
        f"{style['prompt_tail']}"
    )
    if len(prompt) > PROMPT_MAX_CHARS:
        available = PROMPT_MAX_CHARS - len(style["style_sentence"]) - len(f" Clothing: {clothing}. Action:  Setting: . {style['prompt_tail']}")
        beat = beat[:max(30, available // 2)].rsplit(" ", 1)[0]
        environment = environment[:max(25, available - len(beat))].rsplit(" ", 1)[0]
        prompt = (
            f"{style['style_sentence']} Clothing: {clothing}. "
            f"Action: {beat} Setting: {environment}. {style['prompt_tail']}"
        )
    if len(prompt) > PROMPT_MAX_CHARS:
        raise ValueError(f"Built scene prompt exceeds {PROMPT_MAX_CHARS} characters ({len(prompt)}).")
    return prompt

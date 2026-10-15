import copy
import json

import pytest

from src.manual_script import build_manual_story
from src.niche_presets import (
    DEFAULT_NICHE, PRESET_DIR, REQUIRED_FIELDS, available_niches,
    build_scene_prompt, load_niche_preset, load_universal_style,
)

EXPECTED_NICHES = {"stickman_history", "survival", "psychology", "science", "dark_mysteries"}


def test_all_five_niche_presets_load_and_validate():
    assert set(available_niches()) == EXPECTED_NICHES
    for name in sorted(EXPECTED_NICHES):
        preset = load_niche_preset(name)
        assert set(preset) == REQUIRED_FIELDS
        assert preset["display_name"]
        assert 8 <= len(preset["action_directions"]) <= 10
        assert isinstance(preset["fixed_seed"], int)
        assert preset["caption_style"]["font_size"] > 0
        assert preset["clothing_hint"]


def test_default_preset_and_universal_style():
    preset = load_niche_preset()
    style = load_universal_style()
    assert DEFAULT_NICHE == "stickman_history"
    assert preset["default_voice"] == "af_heart"
    assert preset["caption_style"]["font_size"] == 22
    assert "round white head" in style["style_sentence"]
    assert "pure white background" in style["style_sentence"]


def test_missing_required_field_has_clear_error(tmp_path, monkeypatch):
    import src.niche_presets as presets

    bad = copy.deepcopy(load_niche_preset())
    bad.pop("clothing_hint")
    monkeypatch.setattr(presets, "PRESET_DIR", tmp_path)
    (tmp_path / "broken.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field.*clothing_hint"):
        presets.load_niche_preset("broken")


def test_invalid_niche_name_has_clear_error():
    with pytest.raises(ValueError, match="Unknown niche preset.*Available niches"):
        load_niche_preset("not_a_real_niche")


def test_invalid_field_type_has_clear_error(tmp_path, monkeypatch):
    import src.niche_presets as presets

    bad = copy.deepcopy(load_niche_preset())
    bad["fixed_seed"] = "not-an-integer"
    monkeypatch.setattr(presets, "PRESET_DIR", tmp_path)
    (tmp_path / "bad_seed.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="fixed_seed.*integer"):
        presets.load_niche_preset("bad_seed")


def test_narration_is_unchanged_for_every_niche_preset():
    raw_script = (
        "## SCENE 1 — THE HOOK\n"
        + ("The narrator says these exact words and the preset must never rewrite them. " * 55)
        + "\n\nSCENE 2 — THE PAYOFF\n"
        + ("Every sentence stays in the same order, with the same wording and punctuation. " * 20)
    )
    baseline = build_manual_story("Narration Preservation", raw_script)
    baseline_text = "\n\n".join(baseline.paragraphs)
    for niche in sorted(EXPECTED_NICHES):
        _ = load_niche_preset(niche)
        current = build_manual_story("Narration Preservation", raw_script)
        assert "\n\n".join(current.paragraphs) == baseline_text
        assert current.word_count == baseline.word_count
    assert "these exact words" in baseline_text
    assert "must never rewrite them" in baseline_text


def test_all_scene_prompts_are_short_and_use_shared_style():
    style = load_universal_style()
    assert "No color anywhere" not in json.dumps(style)
    for niche in sorted(EXPECTED_NICHES):
        preset = load_niche_preset(niche)
        for index, beat in enumerate((
            "Grug woke up because something was chewing his foot. Not nibbling. CHEWING.",
            "A hunter notices fresh tracks beside the river.",
            "A strange object falls from the sky and the stickman recoils.",
        )):
            prompt = build_scene_prompt(preset, "Example topic", beat, index)
            assert len(prompt) <= 900
            assert "No color anywhere" not in prompt
            assert "round white head" in prompt
            assert "pure white background" in prompt
            assert "Clothing:" in prompt
            assert "Action:" in prompt
            assert "Setting:" in prompt


def test_action_directions_center_one_main_stickman():
    for niche in sorted(EXPECTED_NICHES):
        preset = load_niche_preset(niche)
        assert all("one main stickman" in action.lower() for action in preset["action_directions"])


def test_preset_schema_rejects_removed_legacy_style_fields(tmp_path, monkeypatch):
    import src.niche_presets as presets

    bad = copy.deepcopy(load_niche_preset())
    bad["color_palette"] = "blue and red"
    monkeypatch.setattr(presets, "PRESET_DIR", tmp_path)
    (tmp_path / "bad_schema.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported field.*color_palette"):
        presets.load_niche_preset("bad_schema")

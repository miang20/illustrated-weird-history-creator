import copy
import json

import pytest

from src.manual_script import build_manual_story
from src.niche_presets import DEFAULT_NICHE, PRESET_DIR, available_niches, load_niche_preset


EXPECTED_NICHES = {"stickman_history", "survival", "psychology", "science", "dark_mysteries"}


def test_all_five_niche_presets_load_and_validate():
    assert set(available_niches()) == EXPECTED_NICHES
    for name in sorted(EXPECTED_NICHES):
        preset = load_niche_preset(name)
        assert preset["display_name"]
        assert 8 <= len(preset["action_directions"]) <= 10
        assert isinstance(preset["fixed_seed"], int)
        assert preset["caption_style"]["font_size"] > 0


def test_default_preset_reproduces_stickman_history_defaults():
    preset = load_niche_preset()
    assert DEFAULT_NICHE == "stickman_history"
    assert preset["default_voice"] == "af_heart"
    assert preset["caption_style"]["font_size"] == 22
    assert "2D stickman" in preset["style_prefix"]
    assert "no photorealism" in preset["style_prefix"].lower()
    assert "no 3d" in preset["style_prefix"].lower()


def test_missing_required_field_has_clear_error(tmp_path, monkeypatch):
    import src.niche_presets as presets

    bad = copy.deepcopy(load_niche_preset())
    bad.pop("character_look")
    monkeypatch.setattr(presets, "PRESET_DIR", tmp_path)
    (tmp_path / "broken.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field.*character_look"):
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
        preset = load_niche_preset(niche)
        # Preset loading/configuration must not mutate narration or parser output.
        _ = preset["style_prefix"], preset["character_look"], preset["color_palette"]
        current = build_manual_story("Narration Preservation", raw_script)
        assert "\n\n".join(current.paragraphs) == baseline_text
        assert current.word_count == baseline.word_count
    assert "these exact words" in baseline_text
    assert "must never rewrite them" in baseline_text

def test_scene_prompt_combines_preset_identity_action_environment_and_palette():
    from src.niche_presets import build_scene_prompt

    preset = load_niche_preset("psychology")
    prompt = build_scene_prompt(preset, "Social Anxiety", "The character hesitates before speaking.", 0)
    assert preset["style_prefix"] in prompt
    assert preset["character_look"] in prompt
    assert preset["action_directions"][0] in prompt
    assert preset["environment_hints"] in prompt
    assert preset["color_palette"] in prompt
    assert "The character hesitates before speaking." in prompt

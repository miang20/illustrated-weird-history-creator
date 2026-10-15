from PIL import Image

from src.image_providers import apply_monochrome_line_art, clean_line_art_background
from src.niche_presets import build_scene_prompt, load_niche_preset


def test_gentle_cleanup_whitens_near_white_background_and_preserves_color_and_edges():
    source = Image.new("RGB", (4, 2), (248, 248, 246))
    source.putpixel((0, 0), (30, 30, 30))
    source.putpixel((1, 0), (220, 190, 150))
    source.putpixel((2, 0), (235, 235, 235))
    result = clean_line_art_background(source)

    assert result.mode == "RGB"
    assert result.size == source.size
    assert result.getpixel((3, 1)) == (255, 255, 255)
    assert result.getpixel((0, 0)) != (255, 255, 255)
    assert result.getpixel((1, 0)) != (255, 255, 255)
    assert result.getpixel((2, 0)) != (255, 255, 255)


def test_legacy_hard_threshold_filter_remains_available_only_when_opted_in():
    source = Image.new("RGB", (4, 2), (255, 255, 255))
    source.putpixel((0, 0), (15, 30, 45))
    result = apply_monochrome_line_art(source)
    assert result.mode == "RGB"
    assert set(result.getdata()) <= {(0, 0, 0), (255, 255, 255)}


def test_all_niches_use_the_same_character_and_short_prompt():
    prompts = []
    for niche in ("stickman_history", "survival", "psychology", "science", "dark_mysteries"):
        preset = load_niche_preset(niche)
        prompt = build_scene_prompt(preset, "Topic", "Grug woke up because something was chewing his foot.", 0)
        prompts.append(prompt)
        assert len(prompt) <= 900
        assert "No color anywhere" not in prompt
        assert "round white head" in prompt
        assert "pure white background" in prompt
    assert len(set(prompts)) == 5  # clothing and setting vary; shared character sentence does not


def test_default_hard_threshold_is_off_for_all_current_presets():
    for niche in ("stickman_history", "survival", "psychology", "science", "dark_mysteries"):
        assert load_niche_preset(niche).get("postprocess", False) is False

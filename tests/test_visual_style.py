from PIL import Image

from src.visuals import _apply_monochrome_line_art


def test_monochrome_treatment_outputs_only_black_and_white_pixels():
    source = Image.new("RGB", (4, 2), (255, 255, 255))
    source.putpixel((0, 0), (15, 30, 45))
    source.putpixel((1, 0), (120, 80, 50))
    source.putpixel((2, 0), (240, 20, 20))
    result = _apply_monochrome_line_art(source)

    assert result.mode == "RGB"
    assert result.size == source.size
    assert set(result.getdata()) <= {(0, 0, 0), (255, 255, 255)}
    assert result.getpixel((0, 0)) == (0, 0, 0)
    assert result.getpixel((3, 1)) == (255, 255, 255)


def test_scene_prompt_style_is_independent_of_niche_palette():
    from src.niche_presets import build_scene_prompt, load_niche_preset

    prompts = []
    for niche in ("stickman_history", "survival", "psychology", "science", "dark_mysteries"):
        preset = load_niche_preset(niche)
        prompts.append(build_scene_prompt(preset, "Topic", "A person discovers something unexpected.", 0))

    for prompt in prompts:
        assert "pure white background (#FFFFFF)" in prompt
        assert "black ink lines only" in prompt
        assert "No color anywhere" in prompt
        assert "Niche must NEVER change the character shape" in prompt

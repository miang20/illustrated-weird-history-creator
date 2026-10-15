from pathlib import Path

import pytest

from src.manual_script import build_manual_story, read_manual_script


def test_script_file_reading_and_blank_lines_preserved(tmp_path):
    content = "First narration beat.\n\nSecond narration beat.\n\nThird beat."
    path = tmp_path / "sample.txt"
    path.write_text(content, encoding="utf-8")
    loaded = read_manual_script("sample.txt", "ignored single-line script", repo_root=tmp_path)
    assert loaded == content
    story = build_manual_story("test", loaded, enforce_minimum=False)
    assert story.paragraphs == ["First beat.", "Second beat.", "Third beat.", "Fourth beat.", "Fifth beat.", "Sixth beat."]


def test_test_mode_allows_short_script():
    story = build_manual_story("test", "Grug sees a mammoth.\n\nGrug runs to the cave.", enforce_minimum=False)
    assert story.word_count > 0


def test_normal_mode_still_rejects_short_script():
    with pytest.raises(ValueError, match="only .* words after parsing"):
        build_manual_story("test", "Grug sees a mammoth. " * 20)


def test_narration_is_not_rewritten():
    text = "Grug says sh*t, then runs.\n\nThe mammoth waits."
    story = build_manual_story("test", text, enforce_minimum=False)
    assert "\n".join(story.paragraphs) == text

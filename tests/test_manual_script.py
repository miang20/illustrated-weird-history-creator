from src.manual_script import build_manual_story, script_length_report


def _long_script():
    return (
        "# A SAVAGE HISTORY\n\n"
        "## SCENE 1 — THE HOOK\n"
        + ("What the hell happened next? The stickman recoiled, pointed at the cave, and ran like absolute chaos had arrived. " * 32)
        + "\n\nSCENE 2 — THE TWIST\n"
        + ("The next character crouched behind a rock, then made a dramatic gesture toward the dangerous forest. " * 32)
    )


def test_manual_script_preserves_narration_and_removes_scene_labels():
    story = build_manual_story("Test Documentary", _long_script())
    joined = " ".join(story.paragraphs)
    assert story.title == "Test Documentary"
    assert "What the hell happened next?" in joined
    assert "SCENE 1" not in joined
    assert "SCENE 2" not in joined
    assert story.sources == []
    assert story.word_count >= 250


def test_manual_script_splits_single_wall_of_text_into_speech_beats():
    text = " ".join(
        "The caveman stickman ducked, pointed toward the cave, and ran into the dark forest."
        for _ in range(55)
    )
    story = build_manual_story("One Paragraph", text)
    assert len(story.paragraphs) > 1
    assert "ducked" in " ".join(story.paragraphs)


def test_script_length_report_flags_mismatched_duration():
    assert script_length_report(675, 5)["within_target"] is True
    assert script_length_report(1000, 5)["within_target"] is False

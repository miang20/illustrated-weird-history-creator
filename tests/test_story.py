from src.story import WORDS_PER_MINUTE, _sentences, _select_sentences_for_target, _script_quality_issues, _title_relevance, weekly_topic, WEEKLY_TOPICS

def test_sentence_splitter_returns_distinct_facts():
    result = _sentences("The event began in 1518. It affected several people in the city. Historians still debate the causes of the event.")
    assert len(result) == 3

def test_sentence_splitter_removes_reference_markers():
    result = _sentences("The event was recorded in a chronicle [12]. It later became famous.")
    assert all("[12]" not in item for item in result)


def test_weekly_topic_is_from_curated_rotation():
    assert weekly_topic() in WEEKLY_TOPICS
    assert len(WEEKLY_TOPICS) >= 10


def test_fallback_sentence_selection_scales_to_requested_runtime():
    sentences = [
        f"Documented historical fact number {i} contains several specific words about the event and its consequences."
        for i in range(1, 81)
    ]
    selected = _select_sentences_for_target(sentences, target_words=660)
    assert len(selected) >= 20
    assert sum(len(sentence.split()) for sentence in selected) >= int(660 * 0.96)
    assert len(set(selected)) == len(selected)


def test_fallback_sentence_selection_uses_available_facts_without_repeating():
    sentences = ["The event began in 1518.", "Several people recorded what happened next."]
    selected = _select_sentences_for_target(sentences, target_words=660)
    assert selected == sentences


def test_narration_word_target_uses_calibrated_kokoro_pace():
    assert WORDS_PER_MINUTE == 100
    # The generation prompt targets the nominal word count; the gate allows modest model variance.
    assert int(5 * WORDS_PER_MINUTE * 1.12) == 560
    assert 5 * WORDS_PER_MINUTE == 500
    assert 8 * WORDS_PER_MINUTE == 800


def test_research_title_relevance_distinguishes_subjects():
    assert _title_relevance("The Great Molasses Flood of 1919", "The Great Molasses Flood") >= 0.75
    assert _title_relevance("The Great Molasses Flood of 1919", "A completely unrelated article") == 0.0


def test_script_quality_gate_rejects_names_not_supported_by_research_source():
    paragraphs = [
        ("Halloween traditions evolved across communities over many generations. "
         + "People adapted local customs and celebrations over time. " * 8)
        for _ in range(8)
    ]
    paragraphs[2] += " A German immigrant named Carl Schenck documented the celebrations."
    issues = _script_quality_issues(
        "Halloween", paragraphs, target_minutes=5,
        source_text="Halloween developed from older seasonal customs in Europe.",
    )
    assert any("multi-word names/places not found" in issue for issue in issues)


def test_script_quality_gate_rejects_short_generic_script():
    issues = _script_quality_issues(
        "The Great Molasses Flood of 1919",
        ["Imagine a story where everything changes overnight."],
        target_minutes=5,
    )
    joined = " ".join(issues).lower()
    assert "paragraphs" in joined
    assert "target range" in joined
    assert "subject" in joined
    assert "opening hook" in joined



def test_script_quality_gate_rejects_overlong_five_minute_narration():
    paragraphs = [
        "Halloween traditions changed over many centuries across different communities. " * 10
    ]
    issues = _script_quality_issues("Halloween", paragraphs, target_minutes=5)
    assert any("target range 450-560" in issue for issue in issues)


def test_source_grounding_does_not_misread_sentence_initial_title_case_as_a_name():
    paragraphs = [
        "The Terrifying Origins of Halloween are more complicated than popular legends suggest. " * 8
    ]
    issues = _script_quality_issues(
        "The Terrifying Origins of Halloween",
        paragraphs,
        target_minutes=5,
        source_text="Halloween developed from older seasonal customs in Europe.",
    )
    assert not any("multi-word names/places not found" in issue for issue in issues)

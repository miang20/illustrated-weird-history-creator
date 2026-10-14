from src.story import _sentences, _select_sentences_for_target, weekly_topic, WEEKLY_TOPICS

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
    assert sum(len(sentence.split()) for sentence in selected) >= int(660 * 0.86)
    assert len(set(selected)) == len(selected)


def test_fallback_sentence_selection_uses_available_facts_without_repeating():
    sentences = ["The event began in 1518.", "Several people recorded what happened next."]
    selected = _select_sentences_for_target(sentences, target_words=660)
    assert selected == sentences

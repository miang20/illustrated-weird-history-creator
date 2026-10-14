from src.story import _sentences, weekly_topic, WEEKLY_TOPICS

def test_sentence_splitter_returns_distinct_facts():
    result = _sentences("The event began in 1518. It affected several people in the city. Historians still debate the causes of the event.")
    assert len(result) == 3

def test_sentence_splitter_removes_reference_markers():
    result = _sentences("The event was recorded in a chronicle [12]. It later became famous.")
    assert all("[12]" not in item for item in result)


def test_weekly_topic_is_from_curated_rotation():
    assert weekly_topic() in WEEKLY_TOPICS
    assert len(WEEKLY_TOPICS) >= 10

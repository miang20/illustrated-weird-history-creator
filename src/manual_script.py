from __future__ import annotations

import re

from src.story import Story


def build_manual_story(title: str, script: str) -> Story:
    """Parse user-written narration without rewriting, summarizing, or adding claims."""
    if not script or len(script.strip()) < 250:
        raise ValueError("Manual script is empty or too short. Paste the complete narration first.")

    kept_lines: list[str] = []
    for line in script.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        stripped = line.strip()
        if not stripped:
            kept_lines.append("")
            continue
        # Titles and scene labels guide production but are not narration.
        if re.match(r"^\s*#{1,6}\s*", stripped):
            continue
        if re.match(r"(?i)^\s*scene\s+\d+\b", stripped):
            continue
        kept_lines.append(stripped)

    normalized = "\n".join(kept_lines).strip()
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", normalized) if part.strip()]
    if not paragraphs:
        raise ValueError("No narration text remains after removing headings.")

    # A single wall of text is divided into speech beats for captions and scene matching.
    if len(paragraphs) < 6:
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", " ".join(paragraphs))
        chunks: list[str] = []
        current: list[str] = []
        words = 0
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_words = len(sentence.split())
            if current and words + sentence_words > 42:
                chunks.append(" ".join(current))
                current, words = [], 0
            current.append(sentence)
            words += sentence_words
        if current:
            chunks.append(" ".join(current))
        if chunks:
            paragraphs = chunks

    word_count = len(re.findall(r"[a-z0-9']+", " ".join(paragraphs).lower()))
    if word_count < 250:
        raise ValueError(f"Manual script has only {word_count} words after parsing; paste the full narration.")
    return Story(
        title=title.strip() or "Manual Script Documentary",
        paragraphs=paragraphs,
        sources=[],
        word_count=word_count,
    )


def script_length_report(word_count: int, target_minutes: int, words_per_minute: int = 135) -> dict[str, int | float | bool]:
    """Estimate narration length and flag a likely mismatch before expensive rendering."""
    estimated_minutes = word_count / words_per_minute if words_per_minute else 0.0
    target_words = target_minutes * words_per_minute
    lower = int(target_words * 0.90)
    upper = int(target_words * 1.12)
    return {
        "estimated_minutes": round(estimated_minutes, 2),
        "minimum_words": lower,
        "maximum_words": upper,
        "within_target": lower <= word_count <= upper,
    }

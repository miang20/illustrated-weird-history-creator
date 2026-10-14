from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

import requests

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "IllustratedWeirdHistoryCreator/1.0 (educational documentary generator)"}

@dataclass
class Research:
    title: str
    url: str
    extract: str
    description: str

@dataclass
class Story:
    title: str
    paragraphs: list[str]
    sources: list[dict[str, str]]
    word_count: int

def research_topic(topic: str) -> Research:
    topic = topic.strip()
    if len(topic) < 4:
        raise ValueError("Please enter a more specific historical topic.")
    response = requests.get(WIKI_API, params={"action":"query","list":"search","srsearch":topic,"format":"json","srlimit":5}, headers=HEADERS, timeout=25)
    response.raise_for_status()
    results = response.json().get("query", {}).get("search", [])
    if not results:
        raise ValueError(f"No Wikipedia research result found for '{topic}'. Try a more specific topic.")
    best = results[0]["title"]
    detail = requests.get(WIKI_API, params={
        "action":"query","prop":"extracts|description","explaintext":1,"exsectionformat":"plain",
        "exchars":18000,"titles":best,"format":"json",
    }, headers=HEADERS, timeout=25)
    detail.raise_for_status()
    page = next(iter(detail.json().get("query", {}).get("pages", {}).values()), {})
    extract = re.sub(r"\s+", " ", page.get("extract", "")).strip()
    if len(extract) < 350:
        raise ValueError("The source page has too little factual detail. Try a broader or more specific topic.")
    return Research(page.get("title", best), "https://en.wikipedia.org/wiki/" + quote(page.get("title", best).replace(" ", "_")), extract, page.get("description", ""))

def _sentences(text: str) -> list[str]:
    text = re.sub(r"\[[0-9]+\]", "", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'])", text)
    return [p.strip() for p in parts if len(p.strip()) > 45]

def build_story(topic: str, target_minutes: int = 6, angle: str = "") -> Story:
    research = research_topic(topic)
    sentences = _sentences(research.extract)
    if len(sentences) < 6:
        raise ValueError("Research source did not contain enough distinct facts to build a documentary.")
    target_words = target_minutes * 132
    selected = sentences[:min(len(sentences), max(8, target_minutes * 2 + 2))]
    title = research.title
    paragraphs = [
        f"Imagine discovering that one of the strangest stories in history was not a legend, but an event people tried to explain while it was happening. Today, we are looking at {title}. {selected[0]} "
        f"{'Our focus is ' + angle.strip() + '. ' if angle.strip() else ''}"
        "The challenge is to separate what the record actually tells us from the explanations added later."
    ]
    transitions = [
        "To understand why this mattered, we have to look at the world around the event.",
        "That detail changes the way the story looks. People were reacting with the knowledge and fears available to them at the time.",
        "Here is where the timeline becomes important. Small details can become remarkable when placed beside other evidence.",
        "The next part is less about a single dramatic moment and more about how the event unfolded.",
        "But the historical record has limits. Some details are documented, while other parts remain uncertain or disputed.",
        "That uncertainty is a reminder that historians work with surviving evidence, not a perfect recording of the past.",
        "As more details are placed together, the story becomes stranger and more understandable at the same time.",
        "The aftermath matters because it shows what people remembered and what later generations chose to emphasize.",
    ]
    for i, fact in enumerate(selected[1:]):
        paragraphs.append(f"{transitions[i % len(transitions)]} {fact}")
    paragraphs.append(
        f"So what should we take away from {title}? Keep documented facts separate from speculation. "
        "History can be astonishing without adding imaginary dialogue, invented motives, or details that sources cannot support. "
        "The mystery is often that people had to make decisions with incomplete information. And that is why this story still deserves a closer look."
    )
    expansions = [
        "Think of this as a sequence of clues rather than a finished explanation. Each clue adds context, but none proves more than it can establish.",
        "When a story survives for generations, retelling can become more dramatic than the evidence. A careful account lets verified details do the work.",
        "The useful question is not only what happened, but how people involved understood what they were seeing. Their assumptions shaped their reactions.",
        "Dates, places, and contemporary accounts help separate the event from myths and interpretations that grew afterward.",
    ]
    cursor = 0
    while sum(len(p.split()) for p in paragraphs) < int(target_words * 0.88) and cursor < 16:
        fact = selected[(cursor + 1) % len(selected)]
        paragraphs.insert(max(1, len(paragraphs)-1), f"{expansions[cursor % len(expansions)]} {fact}")
        cursor += 1
    normalized = []
    for paragraph in paragraphs:
        if len(paragraph.split()) > 115:
            bucket = ""
            for bit in re.split(r"(?<=[.!?])\s+", paragraph):
                if len((bucket + " " + bit).split()) > 85 and bucket:
                    normalized.append(bucket.strip())
                    bucket = bit
                else:
                    bucket += " " + bit
            if bucket.strip():
                normalized.append(bucket.strip())
        else:
            normalized.append(paragraph.strip())
    source = [{"title": research.title, "url": research.url, "note": "Research reference; narration is a structured summary, not a quotation transcript."}]
    return Story(title, normalized, source, sum(len(p.split()) for p in normalized))

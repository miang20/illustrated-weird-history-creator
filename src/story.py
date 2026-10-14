from __future__ import annotations

import os
import re
from datetime import date
from dataclasses import dataclass
from urllib.parse import quote

import requests

WIKI_API = "https://en.wikipedia.org/w/api.php"
HEADERS = {"User-Agent": "IllustratedWeirdHistoryCreator/1.0 (educational documentary generator)"}
# Kokoro at the configured speed runs slower than the generic 132 wpm estimate.
# This calibrated target leaves room for fallback transitions and closing narration.
WORDS_PER_MINUTE = 100

@dataclass
class Research:
    title: str
    url: str
    extract: str
    description: str
    sources: list[dict[str, str]]

@dataclass
class Story:
    title: str
    paragraphs: list[str]
    sources: list[dict[str, str]]
    word_count: int


WEEKLY_TOPICS = [
    "The dancing plague of 1518",
    "The Great Molasses Flood of 1919",
    "The Cadaver Synod",
    "The London Beer Flood of 1814",
    "The Mary Celeste mystery",
    "The Year Without a Summer",
    "The Great Emu War",
    "The London Necropolis Railway",
    "The Defenestrations of Prague",
    "The Tunguska event",
    "The Great Stink of London",
    "The War of the Stray Dog",
]

def weekly_topic() -> str:
    """Choose a deterministic, researchable weird-history topic for the current ISO week."""
    week_index = (date.today().isocalendar().week - 1) % len(WEEKLY_TOPICS)
    return WEEKLY_TOPICS[week_index]

def _topic_terms(topic: str) -> set[str]:
    ignored = {"the", "a", "an", "of", "and", "in", "on", "for", "history", "story", "documentary"}
    return {word for word in re.findall(r"[a-z0-9]+", topic.lower()) if len(word) > 2 and word not in ignored}

def _title_relevance(topic: str, title: str) -> float:
    terms = _topic_terms(topic)
    title_terms = set(re.findall(r"[a-z0-9]+", title.lower()))
    if not terms:
        return 0.0
    return len(terms & title_terms) / len(terms)

def research_topic(topic: str) -> Research:
    topic = topic.strip()
    if len(topic) < 4:
        raise ValueError("Please enter a more specific historical topic.")
    response = requests.get(
        WIKI_API,
        params={"action": "query", "list": "search", "srsearch": topic, "format": "json", "srlimit": 10},
        headers=HEADERS,
        timeout=25,
    )
    response.raise_for_status()
    results = response.json().get("query", {}).get("search", [])
    if not results:
        raise ValueError(f"No Wikipedia research result found for '{topic}'. Try a more specific topic.")

    # Never concatenate arbitrary search results: that caused unrelated books, films and albums
    # to be mixed into one narration. Pick one clearly relevant primary article.
    ranked = sorted(
        (result for result in results if result.get("title")),
        key=lambda item: (_title_relevance(topic, item["title"]), -int(item.get("size", 0))),
        reverse=True,
    )
    if not ranked or _title_relevance(topic, ranked[0]["title"]) < 0.34:
        choices = ", ".join(item.get("title", "") for item in ranked[:4])
        raise ValueError(
            f"Could not confidently match '{topic}' to a relevant Wikipedia article. "
            f"Closest results: {choices}. Please enter a more specific topic."
        )
    page_title = ranked[0]["title"].strip()
    detail = requests.get(
        WIKI_API,
        params={
            "action": "query", "prop": "extracts|description", "explaintext": 1,
            "exsectionformat": "plain", "exchars": 18000, "titles": page_title, "format": "json",
        },
        headers=HEADERS,
        timeout=25,
    )
    detail.raise_for_status()
    page = next(iter(detail.json().get("query", {}).get("pages", {}).values()), {})
    extract = re.sub(r"\\s+", " ", page.get("extract", "")).strip()
    actual_title = page.get("title", page_title)
    if len(extract) < 500:
        raise ValueError(f"The relevant article '{actual_title}' does not contain enough detail. Try a more specific topic.")
    url = "https://en.wikipedia.org/wiki/" + quote(actual_title.replace(" ", "_"))
    source = {
        "title": actual_title,
        "url": url,
        "note": "Primary research reference; verify important claims before publication.",
    }
    return Research(actual_title, url, extract, page.get("description", "") or "", [source])

def _sentences(text: str) -> list[str]:
    text = re.sub(r"\[[0-9]+\]", "", text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9“\"'])", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]

def _select_sentences_for_target(sentences: list[str], target_words: int) -> list[str]:
    """Keep distinct source sentences until the fallback can support the requested runtime."""
    selected: list[str] = []
    words = 0
    minimum = max(20, int(target_words * 0.96))
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        selected.append(sentence)
        words += len(sentence.split())
        if words >= minimum and len(selected) >= 20:
            break
    return selected


def _generate_local_script(title: str, extract: str, target_minutes: int, angle: str) -> list[str] | None:
    """Use a small public local instruction model; never requires an inference API key."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id = "Qwen/Qwen2.5-0.5B-Instruct"
    torch.set_num_threads(min(4, os.cpu_count() or 4))
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=torch.float32, low_cpu_mem_usage=True
    ).to("cpu")
    model.eval()
    prompt_messages = [
        {
            "role": "system",
            "content": (
                "You are an expert high-retention YouTube documentary storyteller specializing in strange, surprising real history. "
                "Write original, natural spoken English that sounds excellent aloud, never like an encyclopedia entry. "
                "Accuracy is mandatory: do not invent dialogue, dates, motives, quotations, scenes, or events. Use only claims supported by the research notes. "
                "Clearly distinguish documented facts from disputed explanations and mark uncertainty honestly. Paraphrase rather than copying source sentences. "
                "Every paragraph must either reveal a new fact, raise a meaningful question the evidence can answer, clarify stakes, or change the viewer's understanding. "
                "Avoid filler, repetitive transitions, fake cliffhangers, generic moral lessons, and sensational claims unsupported by evidence. "
                "No headings, bullet points, citations read aloud, or production directions. Output narration paragraphs only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a high-retention {target_minutes}-minute Weird History YouTube documentary narration about: {title}. "
                f"Editorial angle: {angle.strip() or 'Explain the event, its historical context, what is known, and what remains uncertain.'} "
                f"Aim for about {target_minutes * WORDS_PER_MINUTE} words. Follow this story architecture without adding headings: "
                "(1) COLD OPEN: begin with the most surprising specific verified fact and its immediate consequence; no question, no 'Imagine', no greeting. "
                "(2) PROMISE: establish the central mystery or contradiction and why the answer matters, without giving away every payoff. "
                "(3) CONTEXT: quickly orient the viewer in time, place, and the people involved. "
                "(4) ESCALATION: reveal the best documented details in a clear cause-and-effect sequence; every paragraph adds new information. "
                "(5) TURNING POINT: identify the moment when the situation changed, if the sources support one. "
                "(6) EXPLANATION: compare plausible explanations or conflicting accounts only where research supports them; explain what evidence favors each. "
                "(7) PAYOFF: resolve the opening curiosity as far as the evidence allows, then end on one specific, memorable historical implication rather than a generic lesson. "
                "Use short, varied sentences and natural spoken transitions. Add a small curiosity bridge at paragraph endings only when the next paragraph genuinely answers or deepens it. "
                "Avoid repetitive 'but here's the twist' phrasing, empty suspense, repeated facts, and modern assumptions projected onto historical people. "
                "Keep 10 to 16 short paragraphs. Do not overstate evidence. "
                "Before finishing, check that the opening is concrete, the middle keeps adding revelations, and the ending pays off the opening.\n\n"
                f"RESEARCH NOTES (reference only; do not copy verbatim):\n{extract[:24000]}"
            ),
        },
    ]
    prompt = tokenizer.apply_chat_template(prompt_messages, tokenize=False, add_generation_prompt=True)
    encoded = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=6500)
    with torch.inference_mode():
        output = model.generate(
            **encoded,
            max_new_tokens=target_minutes * 210,
            do_sample=True,
            temperature=0.72,
            top_p=0.9,
            repetition_penalty=1.12,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    generated = tokenizer.decode(output[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    del model, tokenizer
    generated = re.sub(r"(?m)^\s*(?:Title|Narration|Script)\s*:\s*.*$", "", generated).strip()
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", generated) if len(p.split()) >= 20]
    if len(paragraphs) < 6:
        sentences = _sentences(generated)
        paragraphs = [" ".join(sentences[i:i+3]) for i in range(0, len(sentences), 3) if sentences[i:i+3]]
    words = sum(len(p.split()) for p in paragraphs)
    target = target_minutes * WORDS_PER_MINUTE
    if len(paragraphs) < 6 or not int(target * 0.95) <= words <= int(target * 1.12):
        print(f"Local script model output did not meet length/structure checks ({words} words); using structured fallback.")
        return None
    return paragraphs

def build_story(topic: str, target_minutes: int = 6, angle: str = "") -> Story:
    research = research_topic(topic)
    title = research.title
    # Do not silently publish raw, unrelated encyclopedia snippets as a "documentary script".
    # If the local no-key model cannot produce a complete narration, stop before voice/image rendering.
    try:
        ai_paragraphs = _generate_local_script(title, research.extract, target_minutes, angle)
    except Exception as exc:
        raise RuntimeError(
            "The local script model could not generate a usable narration, so rendering was stopped "
            "before voice and image generation. This prevents spending a long CPU render on a broken script. "
            f"Model error: {type(exc).__name__}: {exc}"
        ) from exc
    if not ai_paragraphs:
        raise RuntimeError(
            "The local script model output failed narration quality checks. Rendering was stopped before "
            "voice and image generation instead of silently using copied encyclopedia sentences. "
            "Please retry or use a more specific topic."
        )
    words = sum(len(p.split()) for p in ai_paragraphs)
    return Story(
        title=title,
        paragraphs=ai_paragraphs,
        sources=research.sources,
        word_count=words,
    )

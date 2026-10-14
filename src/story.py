from __future__ import annotations

import os
import re
from datetime import date
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

def research_topic(topic: str) -> Research:
    topic = topic.strip()
    if len(topic) < 4:
        raise ValueError("Please enter a more specific historical topic.")
    response = requests.get(
        WIKI_API,
        params={"action": "query", "list": "search", "srsearch": topic, "format": "json", "srlimit": 6},
        headers=HEADERS,
        timeout=25,
    )
    response.raise_for_status()
    results = response.json().get("query", {}).get("search", [])
    if not results:
        raise ValueError(f"No Wikipedia research result found for '{topic}'. Try a more specific topic.")

    extracts: list[str] = []
    sources: list[dict[str, str]] = []
    # One article can have a short introduction. Gather several search-matched pages
    # so the no-key fallback has enough distinct facts for a 5–8 minute script.
    for result in results[:6]:
        page_title = result.get("title", "").strip()
        if not page_title:
            continue
        try:
            detail = requests.get(
                WIKI_API,
                params={
                    "action": "query", "prop": "extracts|description", "explaintext": 1,
                    "exsectionformat": "plain", "exchars": 6500, "titles": page_title, "format": "json",
                },
                headers=HEADERS,
                timeout=25,
            )
            detail.raise_for_status()
            page = next(iter(detail.json().get("query", {}).get("pages", {}).values()), {})
            extract = re.sub(r"\s+", " ", page.get("extract", "")).strip()
            actual_title = page.get("title", page_title)
            if len(extract) < 180:
                continue
            extracts.append(f"RESEARCH PAGE: {actual_title}. {extract}")
            sources.append({
                "title": actual_title,
                "url": "https://en.wikipedia.org/wiki/" + quote(actual_title.replace(" ", "_")),
                "note": "Research reference; used for factual context, not read aloud.",
            })
        except requests.RequestException as exc:
            print(f"Could not fetch related research page {page_title!r}: {type(exc).__name__}")

    if not extracts:
        raise ValueError("Wikipedia research pages did not provide enough factual detail. Try a broader or more specific topic.")
    combined = "\n\n".join(extracts)
    primary = sources[0]
    return Research(primary["title"], primary["url"], combined, "", sources)
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
                "You are a careful documentary writer. Write original, natural spoken English, not an encyclopedia article. "
                "Do not invent dialogue, dates, motives, quotations, or events. Use only claims supported by the research notes. "
                "Mark uncertainty honestly. Paraphrase the notes instead of copying their sentences. Avoid repeated filler and clichés. "
                "No headings, bullet points, citations read aloud, or production directions. Output narration paragraphs only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a high-retention {target_minutes}-minute Weird History documentary narration about: {title}. "
                f"Editorial angle: {angle.strip() or 'Explain the event, its historical context, what is known, and what remains uncertain.'} "
                f"Aim for about {target_minutes * 132} words. Open immediately with the most surprising specific verified fact, not a question, not 'Imagine', and not 'Today we are looking at'. The first two sentences must create curiosity without exaggeration. Use short, spoken-English sentences, clear chronology, "
                "specific verified details, competing interpretations where supported, and a memorable conclusion. "
                "Use 10 to 16 short paragraphs with natural spoken transitions. Do not overstate the evidence.\n\n"
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
    target = target_minutes * 132
    if len(paragraphs) < 6 or not int(target * 0.95) <= words <= int(target * 1.12):
        print(f"Local script model output did not meet length/structure checks ({words} words); using structured fallback.")
        return None
    return paragraphs

def build_story(topic: str, target_minutes: int = 6, angle: str = "") -> Story:
    research = research_topic(topic)
    sentences = _sentences(research.extract)
    if len(sentences) < 6:
        raise ValueError("Research source did not contain enough distinct facts to build a documentary.")
    target_words = target_minutes * 132
    # A fixed 6-sentences-per-minute cap produced short fallback narrations.
    selected = _select_sentences_for_target(sentences, target_words)
    title = research.title
    try:
        ai_paragraphs = _generate_local_script(title, research.extract, target_minutes, angle)
        if ai_paragraphs:
            return Story(
                title=title,
                paragraphs=ai_paragraphs,
                sources=research.sources,
                word_count=sum(len(p.split()) for p in ai_paragraphs),
            )
    except Exception as exc:
        print(f"Local script model unavailable; using structured no-key fallback: {type(exc).__name__}: {exc}")
    # High-quality deterministic fallback: use distinct source facts in sequence instead of padding with repeated filler.
    opening = selected[0]
    paragraphs = [
        f"{opening} This is the documented starting point of {title}. The story becomes more revealing when we follow what happened next and separate contemporary evidence from later interpretation."
    ]
    transitions = [
        "The surrounding context matters here.",
        "The next documented detail adds another piece to the timeline.",
        "This is where the surviving evidence becomes especially useful.",
        "It is worth separating what the sources record from what later retellings suggest.",
        "Seen in context, this detail helps explain why the event mattered.",
    ]
    for i, fact in enumerate(selected[1:]):
        # Use occasional transitions only; repeating one every other sentence inflated runtime
        # with generic filler and made the fallback narration feel mechanical.
        prefix = transitions[(i // 5) % len(transitions)] + " " if i % 5 == 0 else ""
        paragraphs.append((prefix + fact).strip())
    paragraphs.append(
        f"The lasting question about {title} is what the evidence can genuinely tell us. "
        "Some details are documented; others remain uncertain or disputed. "
        "That distinction does not make the story less extraordinary. It makes the real history more interesting than an embellished version."
    )
    normalized = []
    for paragraph in paragraphs:
        if len(paragraph.split()) > 85:
            bucket = ""
            for bit in re.split(r"(?<=[.!?])\s+", paragraph):
                if len((bucket + " " + bit).split()) > 65 and bucket:
                    normalized.append(bucket.strip())
                    bucket = bit
                else:
                    bucket += " " + bit
            if bucket.strip():
                normalized.append(bucket.strip())
        else:
            normalized.append(paragraph.strip())
    source = research.sources
    return Story(title, normalized, source, sum(len(p.split()) for p in normalized))

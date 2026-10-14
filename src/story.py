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
    "The Boston Molasses Disaster",
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
    return [p.strip() for p in parts if len(p.strip()) > 20]

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
                f"Write a compelling {target_minutes}-minute Weird History documentary narration about: {title}. "
                f"Editorial angle: {angle.strip() or 'Explain the event, its historical context, what is known, and what remains uncertain.'} "
                f"Aim for about {target_minutes * 132} words. Use a sharp but responsible opening hook, clear chronology, "
                "specific verified details, competing interpretations where supported, and a memorable conclusion. "
                "Use 10 to 16 short paragraphs with natural spoken transitions. Do not overstate the evidence.\n\n"
                f"RESEARCH NOTES (reference only; do not copy verbatim):\n{extract[:10500]}"
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
    if len(paragraphs) < 6 or not int(target * 0.72) <= words <= int(target * 1.4):
        print(f"Local script model output did not meet length/structure checks ({words} words); using structured fallback.")
        return None
    return paragraphs

def build_story(topic: str, target_minutes: int = 6, angle: str = "") -> Story:
    research = research_topic(topic)
    sentences = _sentences(research.extract)
    if len(sentences) < 6:
        raise ValueError("Research source did not contain enough distinct facts to build a documentary.")
    target_words = target_minutes * 132
    selected = sentences[:min(len(sentences), max(8, target_minutes * 2 + 2))]
    title = research.title
    try:
        ai_paragraphs = _generate_local_script(title, research.extract, target_minutes, angle)
        if ai_paragraphs:
            return Story(
                title=title,
                paragraphs=ai_paragraphs,
                sources=[{
                    "title": research.title,
                    "url": research.url,
                    "note": "Source used as factual reference; narration generated locally and paraphrased.",
                }],
                word_count=sum(len(p.split()) for p in ai_paragraphs),
            )
    except Exception as exc:
        print(f"Local script model unavailable; using structured no-key fallback: {type(exc).__name__}: {exc}")
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

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
    def search_wikipedia(query: str) -> list[dict]:
        response = requests.get(
            WIKI_API,
            params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": 10},
            headers=HEADERS,
            timeout=25,
        )
        response.raise_for_status()
        return response.json().get("query", {}).get("search", [])

    results = search_wikipedia(topic)

    # Descriptive documentary titles often include adjectives such as "terrifying" and
    # framing words such as "origins", which can hide the actual subject page in Wikipedia
    # search. Retry with the core subject instead of rejecting a valid topic.
    removable = {"terrifying", "terrible", "strange", "weird", "mysterious", "shocking",
                 "dark", "untold", "origins", "origin", "history", "story", "documentary",
                 "the", "a", "an", "of", "and", "in", "on", "for"}
    core_terms = [word for word in re.findall(r"[a-z0-9]+", topic.lower()) if word not in removable]
    fallback_query = " ".join(core_terms).strip()
    if fallback_query and fallback_query.casefold() != topic.casefold():
        known = {item.get("title", "").casefold() for item in results}
        results.extend(item for item in search_wikipedia(fallback_query)
                       if item.get("title", "").casefold() not in known)

    if not results:
        raise ValueError(f"No Wikipedia research result found for '{topic}'. Try a more specific topic.")

    # Never concatenate arbitrary search results: choose one relevant primary article.
    ranked = sorted(
        (result for result in results if result.get("title")),
        key=lambda item: (
            _title_relevance(topic, item["title"]),
            item["title"].strip().casefold() == fallback_query.casefold(),
            int(item.get("size", 0)),
        ),
        reverse=True,
    )
    if not ranked or _title_relevance(topic, ranked[0]["title"]) < 0.30:
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
    extract = re.sub(r"\s+", " ", page.get("extract", "")).strip()
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

    model_id = "Qwen/Qwen2.5-1.5B-Instruct"
    torch.set_num_threads(min(4, os.cpu_count() or 4))
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, dtype=torch.float32, low_cpu_mem_usage=True
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
                "Build a deliberate hook-story-rehook-story-payoff rhythm: paragraph 1 is a sharp, concrete cold-open hook; paragraphs 2-3 begin the actual story and orient the viewer; "
                "around paragraph 4 or 5, deliver a second hook (rehook) using a specific documented complication, reversal, surprising consequence, or unanswered contradiction that genuinely raises the stakes; "
                "then continue the story by answering that rehook with evidence, escalating through new facts, and finally paying off the opening hook. "
                "The rehook must be about this exact topic, not a generic teaser. Never use labels like HOOK or REHOOK. "
                "No headings, bullet points, citations read aloud, or production directions. Output narration paragraphs only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a high-retention {target_minutes}-minute Weird History YouTube documentary narration about: {title}. "
                f"Editorial angle: {angle.strip() or 'Explain the event, its historical context, what is known, and what remains uncertain.'} "
                f"STRICT LENGTH TARGET: produce {int(target_minutes * WORDS_PER_MINUTE * 0.90)} to {int(target_minutes * WORDS_PER_MINUTE)} words total, including all paragraphs. For a 5-minute video, aim for 450-500 words. Treat the upper number as a hard target, avoid extra explanations, and stop immediately after the payoff. Follow this story architecture without adding headings: "
                "STORY BEATS, in this order and without headings: "
                "(1) HOOK in paragraph 1: start with a concrete, documented event or consequence and immediate stakes. Never begin with a question or phrases such as 'Did you know', 'Imagine', 'Have you ever wondered', or 'What if'. No greeting. "
                "(2) STORY in paragraphs 2-3: begin the narrative, identify the time/place/people, and explain what was at stake in plain spoken English. "
                "(3) REHOOK around paragraph 4 or 5: introduce a new verified detail that changes what the viewer thinks is happening, raises a sharper question, or reveals an unexpected consequence. "
                "Do not repeat the first hook; make this a genuine new development. "
                "(4) STORY CONTINUES: explain how events unfolded through cause and effect, escalating discoveries, a turning point, and evidence-backed explanation. "
                "(5) PAYOFF: answer the opening hook and the rehook as far as the evidence allows, then end on one specific memorable historical implication, not a generic lesson. "
                "Use short, varied sentences and natural spoken transitions. Add a small curiosity bridge at paragraph endings only when the next paragraph genuinely answers or deepens it. "
                "Avoid repetitive 'but here's the twist' phrasing, empty suspense, repeated facts, and modern assumptions projected onto historical people. "
                "Keep 10 to 16 short paragraphs. Do not overstate evidence. "
                "Before finishing, check that the opening is concrete, the middle keeps adding revelations, and the ending pays off the opening.\n\n"
                f"RESEARCH NOTES (reference only; do not copy verbatim):\n{extract[:24000]}"
            ),
        },
    ]
    paragraphs = []
    issues = []
    # A second concise generation attempt prevents one overlong or weak draft from
    # failing the entire preview when the local model can correct itself.
    for attempt in range(2):
        attempt_messages = list(prompt_messages)
        if attempt:
            attempt_messages.append({
                "role": "user",
                "content": (
                    "REVISION: The previous draft failed the quality gate. Write a fresh, "
                    "complete narration with a concrete, documented opening hook, a genuinely "
                    "new mid-story rehook, evidence-led story development, and a complete payoff. "
                    f"Keep it strictly between {int(target_minutes * WORDS_PER_MINUTE * 0.90)} and "
                    f"{int(target_minutes * WORDS_PER_MINUTE * 1.08)} words. Never start with a generic "
                    "question or 'Did you know', 'Imagine', 'Have you ever wondered', or 'What if'. "
                    "Do not add headings."
                ),
            })
        attempt_prompt = tokenizer.apply_chat_template(
            attempt_messages, tokenize=False, add_generation_prompt=True
        )
        encoded = tokenizer(attempt_prompt, return_tensors="pt", truncation=True, max_length=6500)
        with torch.inference_mode():
            output = model.generate(
                **encoded,
                max_new_tokens=target_minutes * (135 if attempt == 0 else 125),
                do_sample=True,
                temperature=0.55 if attempt else 0.62,
                top_p=0.88,
                repetition_penalty=1.12,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        generated = tokenizer.decode(output[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        generated = re.sub(r"(?m)^\s*(?:Title|Narration|Script)\s*:\s*.*$", "", generated).strip()
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", generated) if len(p.split()) >= 20]
        if len(paragraphs) < 6:
            sentences = _sentences(generated)
            paragraphs = [" ".join(sentences[i:i+3]) for i in range(0, len(sentences), 3) if sentences[i:i+3]]
        issues = _script_quality_issues(title, paragraphs, target_minutes, source_text=extract)
        if not issues:
            break
        print(f"Script quality gate attempt {attempt + 1} rejected narration: " + "; ".join(issues))
    del model, tokenizer
    if issues:
        print("Script quality gate rejected narration after both attempts.")
        return None
    return paragraphs


def _script_quality_issues(title: str, paragraphs: list[str], target_minutes: int, source_text: str = "") -> list[str]:
    """Reject scripts that are too short, repetitive, generic, or disconnected from the subject."""
    text = "\n".join(paragraphs).strip()
    words = re.findall(r"[a-z0-9']+", text.lower())
    target = target_minutes * WORDS_PER_MINUTE
    issues: list[str] = []
    if len(paragraphs) < 8:
        issues.append(f"only {len(paragraphs)} narration paragraphs; need at least 8")
    if not int(target * 0.90) <= len(words) <= int(target * 1.12):
        issues.append(f"{len(words)} words is outside the target range {int(target * 0.90)}-{int(target * 1.12)}")
    terms = _topic_terms(title)
    word_set = set(words)
    if terms and len(terms & word_set) < max(1, (len(terms) + 1) // 2):
        issues.append("the narration does not clearly stay anchored to the requested historical subject")
    normalized_sentences = [re.sub(r"[^a-z0-9 ]", "", s.lower()).strip() for s in _sentences(text)]
    normalized_sentences = [s for s in normalized_sentences if len(s.split()) >= 8]
    if len(normalized_sentences) != len(set(normalized_sentences)):
        issues.append("the narration repeats one or more sentences")
    lower_text = text.lower()
    filler_phrases = (
        "the surrounding context matters here", "this is where things get interesting",
        "but here's the twist", "as we can see", "in conclusion",
        "this teaches us an important lesson", "the story doesn't end there",
    )
    found_filler = [phrase for phrase in filler_phrases if lower_text.count(phrase) > 0]
    if found_filler:
        issues.append("generic filler detected: " + ", ".join(found_filler))
    # Reject unsupported multi-word named entities while avoiding false positives from
    # sentence-initial title case (for example, 'The strange event changed everything').
    if source_text:
        source_lower = re.sub(r"\s+", " ", source_text).casefold()
        # These established cultural/geographic terms may be omitted from a truncated
        # overview article; they are not invented people or fabricated events.
        accepted_contextual_entities = {
            "united states", "all souls", "all saints", "catholic church", "christian church",
            "north america", "western europe", "great britain", "northern ireland", "samhain",
        }
        sentence_starters = {
            "after", "across", "as", "at", "before", "by", "during", "for", "from",
            "he", "her", "his", "in", "it", "its", "on", "over", "she", "the", "these",
            "they", "this", "those", "through", "while", "when", "where", "which", "who",
        }
        entities = re.findall(r"\b[A-Z][a-z]+(?:[-’'][A-Za-z]+)?(?:\s+(?:(?:of|the|and)\s+)?[A-Z][a-z]+(?:[-’'][A-Za-z]+)?){1,3}\b", text)
        unsupported = []
        for entity in entities:
            words_in_entity = entity.split()
            if words_in_entity[0].casefold() in sentence_starters:
                continue
            entity = entity.strip()
            if entity.casefold() in accepted_contextual_entities:
                continue
            if len(entity.split()) < 2 or entity.casefold() not in source_lower:
                if len(entity.split()) >= 2 and entity.casefold() not in source_lower and entity not in unsupported:
                    unsupported.append(entity)
        if unsupported:
            issues.append("multi-word names/places not found in the selected research source: " + ", ".join(unsupported[:6]))
    first = paragraphs[0].strip().lower() if paragraphs else ""
    if first.startswith(("imagine ", "have you ever wondered", "what if ", "did you know")):
        issues.append("the opening hook is generic rather than a concrete documented moment")
    return issues

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

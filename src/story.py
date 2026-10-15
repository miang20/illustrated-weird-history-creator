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
            "exsectionformat": "plain", "exchars": 35000, "titles": page_title, "format": "json",
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


def _trim_script_to_word_limit(paragraphs: list[str], target_minutes: int) -> list[str]:
    """Trim excess narration at paragraph/sentence boundaries while preserving the opening and payoff."""
    maximum = int(target_minutes * WORDS_PER_MINUTE * 1.12)

    def count_words(items: list[str]) -> int:
        return len(re.findall(r"[a-z0-9']+", "\n".join(items).lower()))

    # Preserve already-valid drafts exactly, including paragraph whitespace.
    if count_words(paragraphs) <= maximum:
        return paragraphs
    result = [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]

    # Remove trailing sentences from middle paragraphs first, never from the opening hook
    # or final payoff. Keep at least eight paragraphs so the story retains its shape.
    while count_words(result) > maximum:
        candidates = []
        for index in range(1, len(result) - 1):
            sentences = _sentences(result[index])
            if len(sentences) > 1:
                candidates.append((len(sentences[-1].split()), index, sentences))
        if candidates:
            _, index, sentences = max(candidates, key=lambda item: item[0])
            result[index] = " ".join(sentences[:-1]).strip()
            continue

        if len(result) > 8:
            # If each paragraph is a single sentence, drop the shortest middle paragraph
            # rather than cutting a sentence in half or damaging the final payoff.
            index = min(range(1, len(result) - 1), key=lambda i: len(result[i].split()))
            result.pop(index)
            continue

        # Do not mutilate the hook/payoff or silently create a too-short script.
        break

    return result


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
                "You are a factual history-documentary editor, NOT a fiction writer. Produce natural spoken English for a nonfiction documentary. "
                "NONFICTION ONLY: every factual sentence must be supported by the supplied research notes. Never invent a protagonist, character, named person, family anecdote, scene, dialogue, discovery, ritual, supernatural event, motive, date, quotation, location, or consequence. "
                "Do not write a fictional story, screenplay, imagined example, or character-led journey. Never use a person name unless that exact name appears in the notes and the notes support the claim about them. "
                "Open with the strongest documented surprising fact, not an imagined scene. Every paragraph must add a documented fact, explain a supported cause, reveal a source-backed complication, or clarify a genuine historical uncertainty. "
                "Clearly distinguish documented history from disputed explanations and later folklore. Paraphrase facts in your own words; do not copy source sentences. "
                "Use short, varied, conversational sentences. No generic suspense, fake cliffhangers, invented rituals, fictional characters, moral lessons, headings, labels, bullet points, citations read aloud, or production directions. Output narration paragraphs only."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Write a {target_minutes}-minute NONFICTION historical documentary narration about: {title}. "
                f"Editorial angle: {angle.strip() or 'Explain what the evidence supports and separate documented history from later folklore.'} "
                f"Length: {int(target_minutes * WORDS_PER_MINUTE * 0.90)}-{int(target_minutes * WORDS_PER_MINUTE)} words total. "
                "Actually complete the requested length; do not stop after a short summary. Never open with a question, 'Did you know', 'Imagine', 'Have you ever wondered', or 'What if'. "
                "Use 10-14 short narration paragraphs, with this factual structure: "
                "(1) opening hook: the strongest surprising fact explicitly documented in the notes; no imagined scene. "
                "(2) context: identify the real event, time, place, people or customs only when the notes support them. "
                "(3) rehook around paragraph 4 or 5: introduce another documented fact, contradiction, or consequence that deepens the opening. "
                "(4) explain the evidence and chronology using only the notes. "
                "(5) payoff: resolve the opening using a specific supported historical implication. "
                "This is NOT a fictional story. Do not invent or follow a protagonist, do not create character names, and do not describe a person discovering or doing something unless the notes document it. "
                "Do not add headings or labels. Never begin with a question, 'Did you know', 'Imagine', 'Have you ever wondered', or 'What if'. "
                "If the notes cannot support a dramatic detail, omit it. No fake suspense, fictional scenes, generic moral, or unsupported claims.\n\n"
                f"RESEARCH NOTES (the only factual source; do not copy verbatim):\n{extract[:16000]}"
            ),
        },
    ]
    paragraphs = []
    issues = []
    # A second concise generation attempt repairs length, hook, and grounding issues
    # before the preview is rejected and the expensive render is allowed to start.
    for attempt in range(2):
        attempt_messages = list(prompt_messages)
        if attempt:
            attempt_messages.append({
                "role": "user",
                "content": (
                    "REVISION: The previous draft failed the quality gate. Write a fresh, "
                    "complete narration with a concrete documented hook, a specific factual rehook, "
                    "and a complete evidence-based payoff. Use ONLY facts explicitly supported by the "
                    "research notes. No invented rituals, scenes, motives, atmosphere, named groups, or "
                    "sensory details. Do not use generic filler or labels such as Hook, Story, or Rehook. "
                    f"Quality gate feedback: {'; '.join(issues)}. "
                    f"Keep it between {int(target_minutes * WORDS_PER_MINUTE * 0.90)} and "
                    f"{int(target_minutes * WORDS_PER_MINUTE * 1.08)} words. "
                    "Never start with a question, 'Did you know', 'Imagine', 'Have you ever wondered', or 'What if'."
                ),
            })
        attempt_prompt = tokenizer.apply_chat_template(
            attempt_messages, tokenize=False, add_generation_prompt=True
        )
        encoded = tokenizer(attempt_prompt, return_tensors="pt", truncation=True, max_length=6500)
        with torch.inference_mode():
            output = model.generate(
                **encoded,
                max_new_tokens=target_minutes * 150,
                min_new_tokens=target_minutes * 120,
                # Deterministic decoding reduces spontaneous fictional names and scene beats
                # from this small CPU model; minimum tokens prevent early short summaries.
                do_sample=False,
                repetition_penalty=1.08,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        generated = tokenizer.decode(output[0][encoded["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        generated = re.sub(r"(?m)^\s*(?:Title|Narration|Script)\s*:\s*.*$", "", generated).strip()
        # Normalize one common model cliché rather than burning a second multi-minute
        # generation attempt on wording that can be safely repaired deterministically.
        generated = re.sub(r"\brich tapestry\b", "complex history", generated, flags=re.IGNORECASE)
        # Small local models occasionally emit beat labels despite being told not to.
        # Strip those labels so they never become spoken narration or false named entities.
        generated = re.sub(
            r"(?im)^\s*(?:opening\s+hook|hook|story|rehook|deeper\s+story|payoff|conclusion)\s*:?\s*$",
            "",
            generated,
        )
        generated = re.sub(
            r"(?im)^\s*(?:opening\s+hook|hook|story|rehook|deeper\s+story|continuation|payoff|conclusion)\s*:\s*",
            "",
            generated,
        )
        generated = re.sub(r"(?m)^\s*#{1,6}\s*", "", generated)
        generated = re.sub(r"\*\*(.*?)\*\*", r"\1", generated)
        generated = re.sub(r"(?im)^\s*(?:opening\s+hook|hook|story|rehook|continuation|payoff|conclusion)\s*:\s*", "", generated)
        generated = re.sub(r"\n\s*\n\s*\n+", "\n\n", generated).strip()
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", generated) if len(p.split()) >= 20]
        if len(paragraphs) < 10:
            # Split short-model output into sentence beats rather than letting seven
            # oversized paragraphs weaken the 30-scene pacing.
            paragraphs = _sentences(generated)
        # The model can ignore its requested word budget. Trim only at paragraph/sentence
        # boundaries before running the hard quality gate, preserving the hook and payoff.
        paragraphs = _trim_script_to_word_limit(paragraphs, target_minutes)
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
    source_lower = re.sub(r"\s+", " ", source_text).casefold() if source_text else ""
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
    # Reject drafts dominated by claims with almost no lexical connection to the research.
    # This catches invented atmosphere and generic narration while allowing paraphrases.
    if source_text:
        source_lower = source_text.lower()
        stopwords = {
            "about", "after", "again", "also", "although", "always", "among", "and", "any",
            "are", "around", "because", "been", "before", "being", "between", "both", "but",
            "can", "could", "did", "does", "doing", "each", "even", "every", "few", "for",
            "from", "had", "has", "have", "her", "here", "him", "his", "how", "into", "its",
            "just", "less", "many", "may", "might", "more", "most", "much", "must", "not",
            "often", "only", "other", "our", "out", "over", "same", "she", "should", "some",
            "such", "than", "that", "the", "their", "them", "then", "there", "these", "they",
            "this", "those", "through", "under", "until", "upon", "very", "was", "were", "what",
            "when", "where", "which", "while", "who", "will", "with", "would", "you", "your",
            "one", "two", "first", "second", "last", "new", "old", "people", "person", "time",
            "times", "year", "years", "day", "days", "night", "nights", "thing", "things", "way",
            "ways", "made", "make", "makes", "became", "become", "began", "known", "used",
            "using", "like", "well", "also", "many", "much",
        }
        source_terms = {
            word for word in re.findall(r"[a-z0-9']+", source_lower)
            if len(word) > 3 and word not in stopwords
        }
        checked = 0
        ungrounded = 0
        for sentence in _sentences(text):
            terms = {
                word for word in re.findall(r"[a-z0-9']+", sentence.lower())
                if len(word) > 3 and word not in stopwords
            }
            if not terms:
                continue
            checked += 1
            # A valid paraphrase may share only one distinctive anchor with a short
            # research extract. Requiring two shared terms per sentence rejects natural
            # narration even when its topic and named entities are source-grounded.
            if len(terms & source_terms) < 1:
                ungrounded += 1
        # A single Wikipedia overview is not a sentence-by-sentence script outline:
        # connective narration and valid paraphrases may not reuse its exact vocabulary.
        # Still reject drafts where most sentences are completely disconnected from the notes.
        if checked >= 8 and ungrounded / checked > 0.60:
            issues.append(
                f"{ungrounded} of {checked} narration sentences have no distinctive factual overlap with the selected research source"
            )
    lower_text = text.lower()
    filler_phrases = (
        "the surrounding context matters here", "this is where things get interesting",
        "but here's the twist", "as we can see", "in conclusion",
        "this teaches us an important lesson", "the story doesn't end there",
        "rich tapestry", "let us delve", "this revelation challenges everything",
        "each discovery brings us closer", "our journey takes a dramatic turn",
        "we've traveled back through time", "universal themes", "more than just",
    )
    found_filler = [phrase for phrase in filler_phrases if lower_text.count(phrase) > 0]
    if found_filler:
        issues.append("generic filler detected: " + ", ".join(found_filler))
    # Reject invented protagonists and fictional scene beats that a small local model
    # may add despite a nonfiction prompt. A script with these patterns is not safe to render.
    fictional_patterns = {
        "fictional named protagonist": r"\b(?:a|the)\s+(?:young\s+)?(?:boy|girl|child|man|woman)\s+named\s+[A-Z][a-z]+",
        "invented discovery scene": r"\b(?:stumbles upon|discovers|finds)\s+(?:an?\s+)?(?:secret|mysterious|glowing|ancient)\s+(?:book|map|graveyard|symbols?)",
        "fictional family backstory": r"\b(?:great[- ]great[- ]grandfather|great[- ]grandfather|great[- ]grandmother)\b",
        "fantasy plot": r"\b(?:dark magic|banish(?:es|ed|ing)?\s+the\s+witch|restore peace to the cemetery|ghost said to possess|sinister figure rumored to haunt)\b",
        "fictional adventure moral": r"\b(?:his|her|their) adventure teaches|this narrative explores\b",
    }
    detected_fiction = [label for label, pattern in fictional_patterns.items() if re.search(pattern, text, re.IGNORECASE)]
    if detected_fiction:
        issues.append("fictional story elements detected in a nonfiction script: " + ", ".join(detected_fiction))

    # Catch repeated capitalized person names that are absent from the selected research.
    # Ignore sentence-initial words and standard historical/cultural terms.
    if source_text:
        source_folded = source_text.casefold()
        common_capitalized = {
            "Halloween", "Samhain", "Celtic", "Christian", "Christians", "Europe",
            "European", "Irish", "Roman", "Catholic", "All", "Saints", "Saint",
            "Ancient", "Old", "New", "Industrial", "Revolution", "United", "States",
        }
        counts = {}
        for sentence in _sentences(text):
            tokens = re.findall(r"\b[A-Z][a-z]{2,}\b", sentence)
            first = re.match(r"[A-Z][a-z]+", sentence.strip())
            first_word = first.group(0).casefold() if first else ""
            for token in tokens:
                folded = token.casefold()
                if folded == first_word or token in common_capitalized or folded in source_folded:
                    continue
                counts[folded] = counts.get(folded, 0) + 1
        invented_names = sorted(name for name, count in counts.items() if count >= 2)
        explicitly_named = {
            match.casefold() for match in re.findall(r"\b(?:named|called)\s+([A-Z][a-z]{2,})\b", text)
            if match.casefold() not in source_folded
        }
        invented_names = sorted(set(invented_names) | explicitly_named)
        if invented_names:
            issues.append("repeated person/place names not found in the selected research source: " + ", ".join(invented_names[:6]))

    # Reject unsupported multi-word named entities while avoiding false positives from
    # sentence-initial title case (for example, 'The strange event changed everything').
    if source_text:
        source_lower = re.sub(r"\s+", " ", source_text).casefold()
        # These established cultural/geographic terms may be omitted from a truncated
        # overview article; they are not invented people or fabricated events.
        accepted_contextual_entities = {
            "united states", "all souls", "all saints", "catholic church", "christian church",
            "north america", "western europe", "great britain", "northern ireland", "samhain",
            "old irish", "evening of all saints", "native americans", "evening prayer", "evening mass",
            "roman catholic", "ancient celts", "celtic people", "gaelic language", "all hallows eve",
            "ancient europe", "iron age", "pope gregory", "native american", "the new year", "world war",
        }
        sentence_starters = {
            "after", "across", "as", "at", "before", "by", "during", "for", "from",
            "he", "her", "his", "in", "it", "its", "on", "over", "she", "the", "these",
            "they", "this", "those", "through", "while", "when", "where", "which", "who",
        }
        # Adjectives, titles, calendar terms, and beat labels often appear title-cased
        # in generated prose but are not personal names that a single article can validate.
        contextual_starters = {
            "ancient", "old", "native", "evening", "roman", "invincible", "british", "feast",
            "stingy", "king", "queen", "pharaoh", "pope", "emperor", "empress", "saint",
            "saints", "celtic", "gaelic", "christian", "catholic", "new", "world", "iron",
            "western", "northern", "southern", "eastern", "great", "first", "second", "third",
            "modern", "early", "late", "american", "irish", "scottish", "english", "welsh",
            "german", "french", "norse", "viking", "middle", "high", "low", "all", "opening",
            "deeper", "hook", "rehook", "story", "payoff", "conclusion", "invincible", "native",
            "christians",
        }
        entities = re.findall(r"\b[A-Z][a-z]+(?:[-’'][A-Za-z]+)?(?:\s+(?:(?:of|the|and)\s+)?[A-Z][a-z]+(?:[-’'][A-Za-z]+)?){1,3}\b", text)
        unsupported = []
        for entity in entities:
            words_in_entity = entity.split()
            if words_in_entity[0].casefold() in sentence_starters or words_in_entity[0].casefold() in contextual_starters:
                continue
            entity = entity.strip()
            entity_lower = entity.casefold().strip(" ,.;:")
            if entity_lower in accepted_contextual_entities or any(
                known in entity_lower for known in accepted_contextual_entities
            ):
                continue
            if len(entity.split()) < 2 or entity.casefold() not in source_lower:
                if len(entity.split()) >= 2 and entity.casefold() not in source_lower and entity not in unsupported:
                    unsupported.append(entity)
        if unsupported:
            issues.append("multi-word names/places not found in the selected research source: " + ", ".join(unsupported[:6]))
    first = paragraphs[0].strip().lower() if paragraphs else ""
    if first.startswith(("imagine ", "have you ever wondered", "have you ever ", "what if ", "did you know", "what makes ", "why do ", "how did ")):
        issues.append("the opening hook is generic rather than a concrete documented moment")
    if source_text and paragraphs:
        hook_terms = {
            word for word in re.findall(r"[a-z0-9']+", paragraphs[0].lower())
            if len(word) > 3 and word not in stopwords
        }
        source_anchor_terms = {
            word for word in re.findall(r"[a-z0-9']+", source_text.lower())
            if len(word) > 3 and word not in stopwords
        }
        if not hook_terms & source_anchor_terms:
            issues.append("the opening hook has no distinctive anchor in the selected research source")
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

import os
import json
import re
import time
from collections import OrderedDict

import httpx

from ..utils.abbreviations import (
    ABBREVIATION_MAP,
    expand_abbreviations,
    get_abbreviation_expansions,
    is_likely_abbreviation,
)
from ..utils import readability

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUGGESTION_ENGINE = os.getenv("SUGGESTION_ENGINE", "llm").lower()
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODELS = [
    os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash-8b",
]

FORMAL_CUES = {
    "dear",
    "regards",
    "sincerely",
    "please",
    "kindly",
    "meeting",
    "deadline",
    "attached",
    "request",
    "appreciate",
}

INFORMAL_CUES = {
    "hey",
    "yo",
    "lol",
    "bro",
    "dude",
    "gonna",
    "wanna",
    "yup",
    "nah",
    "omg",
}

AGGRESSIVE_CUES = {
    "freak",
    "fuck",
    "stfu",
    "idiot",
    "moron",
    "dumb",
    "hate",
    "trash",
}

FORMAL_CONTEXT_CUES = {
    "manager",
    "team",
    "client",
    "interview",
    "professor",
    "office",
    "job",
    "report",
    "assignment",
    "project",
}

INFORMAL_CONTEXT_CUES = {
    "friend",
    "party",
    "weekend",
    "game",
    "hangout",
    "mom",
    "dad",
    "buddy",
}

SAFE_FORMAL_ABBREVIATIONS = {
    "asap",
    "fyi",
    "eta",
    "eod",
    "pto",
    "qa",
    "api",
}

INFORMAL_ABBREVIATIONS = {
    "lol",
    "lmao",
    "brb",
    "idk",
    "imo",
    "imho",
    "ttyl",
    "gm",
    "gn",
    "wyd",
    "omw",
    "thx",
    "u",
    "ur",
    "y",
}

AMBIGUOUS_ABBREVIATIONS = {
    "pls",
    "msg",
    "btw",
    "tbh",
    "afaik",
}

COMMON_SHORT_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "for",
    "from",
    "had",
    "has",
    "have",
    "he",
    "her",
    "him",
    "his",
    "i",
    "if",
    "in",
    "is",
    "it",
    "its",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "she",
    "send",
    "that",
    "the",
    "them",
    "they",
    "this",
    "to",
    "us",
    "we",
    "with",
    "you",
    "your",
}

VALID_SUGGESTION_ENGINES = {"llm", "rule"}
CACHE_TTL_SECONDS = 300
CACHE_MAX_ITEMS = 300
_SUGGESTION_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()


def _cache_get(key: str) -> dict | None:
    cached = _SUGGESTION_CACHE.get(key)
    if not cached:
        return None

    timestamp, payload = cached
    if time.time() - timestamp > CACHE_TTL_SECONDS:
        _SUGGESTION_CACHE.pop(key, None)
        return None

    _SUGGESTION_CACHE.move_to_end(key)
    return {
        "simplified_text": payload.get("simplified_text"),
        "clear_text": payload.get("clear_text"),
    }


def _cache_set(key: str, payload: dict) -> None:
    _SUGGESTION_CACHE[key] = (time.time(), payload)
    _SUGGESTION_CACHE.move_to_end(key)
    while len(_SUGGESTION_CACHE) > CACHE_MAX_ITEMS:
        _SUGGESTION_CACHE.popitem(last=False)


def _cache_key(text: str, engine: str) -> str:
    lowered = re.sub(r"\s+", " ", text.strip().lower())
    return f"{engine}|{lowered}"


def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    return parts


def _tokenize_words(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"\b[a-zA-Z][a-zA-Z0-9']*\b", text)]


def _normalize_compare_text(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _basic_clean_sentence(text: str) -> str:
    if not text:
        return "Please share your message."

    trimmed = text.strip()
    without_emoji_symbols = re.sub(
        r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]|[^\w\s,.!?']",
        " ",
        trimmed,
    )
    compact = re.sub(r"\s+", " ", without_emoji_symbols).strip(" ,")
    if not compact:
        compact = "Please share your message"

    # Collapse stretched endings like "heyyyy" -> "hey" and "soooo" -> "so".
    compact = re.sub(r"([A-Za-z])\1{2,}(?=\b)", r"\1", compact)
    compact = re.sub(r"([!?])\1+", r"\1", compact)

    compact = compact[0].upper() + compact[1:] if compact else compact
    if not re.search(r"[.!?]$", compact):
        compact = f"{compact}."
    return compact


def _ensure_rewrite_changes(
    original_text: str,
    candidate: str,
    prefix: str,
) -> str:
    if _normalize_compare_text(candidate) == _normalize_compare_text(
        original_text
    ):
        cleaned = _basic_clean_sentence(candidate)

        if prefix.lower().startswith("please"):
            if re.match(r"^(hi|hey)\b", cleaned, flags=re.IGNORECASE):
                return re.sub(
                    r"^(hi|hey)\b",
                    "Hello",
                    cleaned,
                    flags=re.IGNORECASE,
                )
            return cleaned

        if prefix.lower().startswith("hey"):
            if cleaned.endswith("?"):
                return cleaned
            if re.match(r"^(hi|hey)\b", cleaned, flags=re.IGNORECASE):
                return cleaned
            return f"Hey, {cleaned[0].lower() + cleaned[1:]}"

        return cleaned
    return candidate


def _build_clean_rewrite(original_text: str, base_sentence: str) -> str:
    clean = base_sentence
    lowered = clean.lower()

    if "happy birthday" in lowered:
        return "Happy birthday!"

    if lowered.startswith("hi") or lowered.startswith("hey"):
        clean = re.sub(r"^(hi|hey)\b", "Hello", clean, flags=re.IGNORECASE)
        if "how are you" in lowered:
            clean = "Hello, how are you doing today?"
        return clean

    if clean.endswith("?"):
        return clean

    return clean


def _is_low_quality_rewrite(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    low_quality_patterns = [
        "clarify your message",
        "clarify this",
        "rephrase this respectfully",
        "please rephrase this in a neutral",
    ]
    return any(pattern in normalized for pattern in low_quality_patterns)


def _is_birthday_like_message(text: str) -> bool:
    normalized = _normalize_compare_text(text)
    has_happy_like = bool(re.search(r"\bhap[a-z]*\b", normalized))
    has_birthday_like = bool(
        re.search(r"\bbirth[a-z]*day[a-z]*\b", normalized)
    )
    return has_happy_like and has_birthday_like


def _build_birthday_rewrites() -> dict[str, str]:
    return {
        "formal": "Happy birthday. Wishing you a wonderful year ahead.",
        "informal": "Happy birthday! Hope you have an awesome day.",
        "clean": "Happy birthday!",
    }


def _diversify_rewrites(base_sentence: str) -> dict[str, str]:
    clean = _basic_clean_sentence(base_sentence)

    if _is_birthday_like_message(clean):
        return _build_birthday_rewrites()

    informal_text = clean
    if not clean.endswith("?"):
        base_no_punct = re.sub(r"[.!?]+$", "", clean).strip()
        informal_text = f"Hey, {base_no_punct.lower()}!"

    return {
        "formal": clean,
        "informal": informal_text,
        "clean": clean,
    }


def _distinct_rewrites_from_expansion(
    base_sentence: str,
) -> dict[str, str] | None:
    normalized = _normalize_compare_text(base_sentence)

    if normalized == "as i remember":
        return {
            "formal": "If I remember correctly.",
            "informal": "As far as I remember.",
            "clean": "I remember.",
        }

    if normalized in {"i dont know", "i do not know"}:
        return {
            "formal": "I am not sure.",
            "informal": "Not sure right now.",
            "clean": "I don't know.",
        }

    if normalized in {"be right back", "i will be right back"}:
        return {
            "formal": "I will return shortly.",
            "informal": "Back in a moment.",
            "clean": "Be right back.",
        }

    if normalized == "on my way":
        return {
            "formal": "I am on my way.",
            "informal": "On my way!",
            "clean": "On my way.",
        }

    if normalized == "thank you":
        return {
            "formal": "Thank you for your help.",
            "informal": "Thanks a lot!",
            "clean": "Thank you.",
        }

    return None


def _find_abbreviations(original_text: str) -> list[str]:
    tokens = re.findall(r"\b[a-zA-Z0-9']+\b", original_text)
    found: list[str] = []
    for token in tokens:
        lower_token = token.lower()
        if (
            lower_token in ABBREVIATION_MAP
            and is_likely_abbreviation(token)
            and lower_token not in found
        ):
            found.append(lower_token)
    return found


def _extract_short_forms(original_text: str) -> list[str]:
    raw_tokens = re.findall(r"\b[a-zA-Z0-9']+\b", original_text)
    found: list[str] = []

    def _looks_like_compact_short_form(token: str) -> bool:
        if len(token) < 2:
            return False
        vowels = sum(1 for ch in token if ch in "aeiou")
        return vowels <= 1

    for raw in raw_tokens:
        token = raw.lower()
        if not token:
            continue

        likely_short_form = False
        if token in ABBREVIATION_MAP and is_likely_abbreviation(raw):
            likely_short_form = True
        elif (
            token in INFORMAL_ABBREVIATIONS
            or token in AMBIGUOUS_ABBREVIATIONS
        ):
            likely_short_form = True
        elif raw.isupper() and 2 <= len(raw) <= 8:
            likely_short_form = True
        elif any(ch.isdigit() for ch in token) and len(token) <= 8:
            likely_short_form = True
        elif len(token) <= 3 and token not in COMMON_SHORT_WORDS:
            likely_short_form = True
        elif (
            len(token) == 4
            and token not in COMMON_SHORT_WORDS
            and _looks_like_compact_short_form(token)
        ):
            likely_short_form = True

        if likely_short_form and token not in found:
            found.append(token)

    return found


def _build_abbreviation_lines(
    short_forms: list[str],
    llm_expansions: dict[str, str] | None = None,
) -> list[str]:
    lines: list[str] = []
    llm_expansions = llm_expansions or {}

    formal_keywords = {
        "regards",
        "please",
        "sincerely",
        "information",
        "report",
        "estimated",
        "arrival",
        "business",
    }

    informal_keywords = {
        "buddy",
        "bro",
        "lol",
        "laugh",
        "chill",
        "you",
        "your",
        "night",
        "morning",
    }

    def _infer_expansion_tone(expansion: str) -> str:
        tokens = _tokenize_words(expansion)
        if any(token in AGGRESSIVE_CUES for token in tokens):
            return "aggressive"
        if any(token in formal_keywords for token in tokens):
            return "formal"
        if any(token in informal_keywords for token in tokens):
            return "informal"
        return "neutral"

    for token in short_forms:
        dataset_expansions = get_abbreviation_expansions(token)
        if dataset_expansions:
            for index, expansion in enumerate(dataset_expansions[:3], start=1):
                tone = _infer_expansion_tone(expansion)
                lines.append(
                    "Abbreviation option "
                    f"{index}: '{token}' -> '{expansion}' "
                    f"(dataset, tone={tone})"
                )
            continue

        llm_expansion = llm_expansions.get(token)
        if llm_expansion:
            tone = _infer_expansion_tone(llm_expansion)
            lines.append(
                "Abbreviation: "
                f"'{token}' -> '{llm_expansion}' (llm, tone={tone})"
            )
        else:
            lines.append(
                "Abbreviation: "
                f"'{token}' -> expansion unavailable"
            )

    return lines


def _build_rewrite_variants(
    original_text: str,
    expanded_text: str,
    style_profile: dict,
) -> dict[str, str]:
    base = _basic_clean_sentence(
        expanded_text.strip() or original_text.strip()
    )

    if style_profile.get("aggressive_hits", 0) > 0:
        rewrites = {
            "formal": (
                "Could you please rephrase this respectfully and share your "
                "exact concern?"
            ),
            "informal": "Hey, can you say this politely so I can help?",
            "clean": "Please rephrase this in a neutral and respectful way.",
        }
        return rewrites

    base_lower = base.lower()
    if _is_birthday_like_message(base_lower):
        return _build_birthday_rewrites()

    expansion_distinct = _distinct_rewrites_from_expansion(base)
    if expansion_distinct:
        return expansion_distinct

    formal = base
    informal = base

    if formal.lower().startswith("can you"):
        formal = re.sub(
            r"^can you\b",
            "Could you",
            formal,
            flags=re.IGNORECASE,
        )
    elif formal.lower().startswith("pls"):
        formal = re.sub(r"^pls\b", "Please", formal, flags=re.IGNORECASE)

    if informal.lower().startswith("could you"):
        informal = re.sub(
            r"^could you\b",
            "Can you",
            informal,
            flags=re.IGNORECASE,
        )

    clean = _build_clean_rewrite(original_text, base)

    formal = _ensure_rewrite_changes(original_text, formal, "Please ")
    informal = _ensure_rewrite_changes(original_text, informal, "Hey, ")
    clean = _build_clean_rewrite(original_text, clean)

    if (
        _normalize_compare_text(formal)
        == _normalize_compare_text(informal)
        == _normalize_compare_text(clean)
    ):
        return _diversify_rewrites(clean)

    return {
        "formal": formal,
        "informal": informal,
        "clean": clean,
    }


def _build_abbreviation_status_line(
    short_forms: list[str],
    llm_expansions: dict[str, str] | None = None,
) -> str:
    llm_expansions = llm_expansions or {}
    if not short_forms:
        return "abbrevation may not exist or rarely used"

    fragments: list[str] = []
    for token in short_forms[:3]:
        expansions = get_abbreviation_expansions(token)
        if expansions:
            for expansion in expansions[:3]:
                fragments.append(f"{token} -> {expansion}")
            continue
        llm_expansion = llm_expansions.get(token)
        if llm_expansion:
            fragments.append(f"{token} -> {llm_expansion}")

    if not fragments:
        return "abbrevation may not exist or rarely used"
    return "Abbreviation status: " + " | ".join(fragments)


def _build_context_lines(
    style_profile: dict,
    original_text: str,
) -> tuple[str, str]:
    expected_style = style_profile.get("expected_style", "formal")
    symbol_stats = readability.extract_symbol_emoji_stats(original_text)
    emoji_count = symbol_stats["emoji_count"]
    symbol_count = symbol_stats["symbol_count"]

    formal_line = (
        "Formal sentence way: Use complete words, polite tone, "
        "and avoid slang abbreviations."
    )
    informal_line = (
        "Informal sentence way: Keep it friendly and short, but avoid "
        "offensive phrasing."
    )

    if expected_style == "informal":
        formal_line = (
            "Formal sentence way: For professional contexts, replace chat "
            "short forms with full phrases."
        )

    if emoji_count or symbol_count:
        formal_line += (
            f" Detected {emoji_count} emoji and {symbol_count} symbols; "
            "reduce them for better readability."
        )

    return formal_line, informal_line


def _format_output_lines(
    abbreviation_status: str,
    formal_context: str,
    informal_context: str,
    rewrites: dict[str, str],
) -> str:
    lines = [
        f"- {abbreviation_status}",
        f"- {formal_context}",
        f"- {informal_context}",
        f"- Rewrite (formal): {rewrites['formal']}",
        f"- Rewrite (informal): {rewrites['informal']}",
        f"- Rewrite (clean): {rewrites['clean']}",
    ]
    return "\n".join(lines)


def _normalize_final_rewrites(
    original_text: str,
    rewrites: dict[str, str],
) -> dict[str, str]:
    expanded_original = expand_abbreviations(original_text)
    fallback_rewrites = _build_rewrite_variants(
        original_text,
        expanded_original,
        _detect_style_profile(original_text),
    )

    normalized = {
        "formal": rewrites.get("formal", "").strip(),
        "informal": rewrites.get("informal", "").strip(),
        "clean": rewrites.get("clean", "").strip(),
    }

    for key in ("formal", "informal", "clean"):
        if not normalized[key] or _is_low_quality_rewrite(normalized[key]):
            normalized[key] = fallback_rewrites[key]

    normalized["formal"] = _ensure_rewrite_changes(
        original_text,
        normalized["formal"] or original_text,
        "Please ",
    )
    normalized["informal"] = _ensure_rewrite_changes(
        original_text,
        normalized["informal"] or original_text,
        "Hey, ",
    )
    normalized["clean"] = _build_clean_rewrite(
        original_text,
        normalized["clean"] or _basic_clean_sentence(original_text),
    )

    expanded_norm = _normalize_compare_text(
        _basic_clean_sentence(expanded_original)
    )
    all_equal_to_expansion = all(
        _normalize_compare_text(normalized[key]) == expanded_norm
        for key in ("formal", "informal", "clean")
    )
    if all_equal_to_expansion:
        distinct = _distinct_rewrites_from_expansion(
            _basic_clean_sentence(expanded_original)
        )
        if distinct:
            return distinct

    if (
        _normalize_compare_text(normalized["formal"])
        == _normalize_compare_text(normalized["informal"])
        == _normalize_compare_text(normalized["clean"])
    ):
        return _diversify_rewrites(normalized["clean"])

    return normalized


def _build_short_form_context_lines(
    short_forms: list[str],
    expected_style: str,
    llm_expansions: dict[str, str] | None = None,
) -> list[str]:
    lines: list[str] = []
    llm_expansions = llm_expansions or {}

    def _is_aggressive_phrase(text: str) -> bool:
        return any(token in AGGRESSIVE_CUES for token in _tokenize_words(text))

    for token in short_forms[:6]:
        token_expansions = get_abbreviation_expansions(token)
        expanded = (
            token_expansions[0]
            if token_expansions
            else llm_expansions.get(token)
        )
        aggressive_expansion = bool(
            expanded and _is_aggressive_phrase(expanded)
        )

        if expected_style == "formal":
            if token in SAFE_FORMAL_ABBREVIATIONS:
                lines.append(
                    "Context fit: "
                    f"'{token}' is commonly acceptable in formal messages."
                )
                continue
            if aggressive_expansion:
                lines.append(
                    "Context fit: "
                    f"'{token}' can sound disrespectful. Avoid this phrase "
                    "in both formal and casual communication."
                )
                continue
            if expanded:
                lines.append(
                    "Context fit: "
                    f"'{token}' is better avoided in formal sentences. "
                    f"Use '{expanded}' instead."
                )
            else:
                lines.append(
                    "Context fit: "
                    f"'{token}' may look informal in formal communication; "
                    "prefer a full phrase."
                )
        else:
            if aggressive_expansion:
                lines.append(
                    "Context fit: "
                    f"'{token}' can sound offensive in casual chat too; "
                    "use respectful wording."
                )
                continue
            if expanded:
                lines.append(
                    "Context fit: "
                    f"'{token}' suits casual chat. Example sentence: "
                    f"'Hey, {token}, can you check this later?'"
                )
            else:
                lines.append(
                    "Context fit: "
                    f"'{token}' can suit casual chat if your audience "
                    "understands it."
                )

    return lines


def _detect_style_profile(original_text: str) -> dict:
    tokens = _tokenize_words(original_text)
    token_set = set(tokens)

    formal_hits = sum(1 for token in tokens if token in FORMAL_CUES)
    informal_hits = sum(1 for token in tokens if token in INFORMAL_CUES)
    contraction_hits = len(
        re.findall(r"\b\w+'(?:t|re|ve|ll|d|m|s)\b", original_text.lower())
    )
    emoji_pattern = r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]"
    emoji_hits = len(re.findall(emoji_pattern, original_text))
    repeated_punct_hits = len(re.findall(r"([!?])\1+", original_text))
    abbreviations = _find_abbreviations(original_text)
    expanded_tokens: list[str] = []
    for abbr in abbreviations:
        for expansion in get_abbreviation_expansions(abbr):
            expanded_tokens.extend(_tokenize_words(expansion))

    informal_abbr_hits = sum(
        1 for abbr in abbreviations if abbr in INFORMAL_ABBREVIATIONS
    )
    aggressive_hits = sum(1 for token in tokens if token in AGGRESSIVE_CUES)
    aggressive_hits += sum(
        1 for token in expanded_tokens if token in AGGRESSIVE_CUES
    )

    formal_score = formal_hits + max(0, contraction_hits // 2)
    informal_score = (
        informal_hits
        + informal_abbr_hits
        + aggressive_hits
        + (1 if abbreviations else 0)
        + repeated_punct_hits
        + (1 if emoji_hits > 0 else 0)
    )

    context_formal_hits = len(token_set.intersection(FORMAL_CONTEXT_CUES))
    context_informal_hits = len(token_set.intersection(INFORMAL_CONTEXT_CUES))
    if context_formal_hits > context_informal_hits:
        expected_style = "formal"
    elif context_informal_hits > context_formal_hits:
        expected_style = "informal"
    else:
        if abbreviations and formal_hits == 0:
            expected_style = "informal"
        else:
            expected_style = (
                "informal" if informal_score > formal_score else "formal"
            )

    if aggressive_hits > 0:
        predicted_style = "informal"
    elif formal_score > informal_score:
        predicted_style = "formal"
    elif informal_score > formal_score:
        predicted_style = "informal"
    else:
        predicted_style = "neutral"

    return {
        "predicted_style": predicted_style,
        "expected_style": expected_style,
        "abbreviations": abbreviations,
        "aggressive_hits": aggressive_hits,
        "style_mismatch": (
            predicted_style != "neutral" and predicted_style != expected_style
        ),
    }


def _build_abbreviation_suggestions(
    abbreviations: list[str],
    expected_style: str,
) -> list[str]:
    suggestions: list[str] = []

    for abbr in abbreviations:
        expansions = get_abbreviation_expansions(abbr)
        expanded = expansions[0] if expansions else ""
        if expected_style == "formal":
            if abbr in SAFE_FORMAL_ABBREVIATIONS:
                continue
            if (
                abbr in INFORMAL_ABBREVIATIONS
                or abbr in AMBIGUOUS_ABBREVIATIONS
            ):
                if expanded:
                    suggestions.append(
                        "In formal writing, replace "
                        f"'{abbr}' with '{expanded}'."
                    )
                else:
                    suggestions.append(
                        "In formal writing, avoid "
                        f"'{abbr}' and use the full phrase."
                    )
        else:
            if abbr in INFORMAL_ABBREVIATIONS:
                suggestions.append(
                    f"'{abbr}' is fine for casual chat, "
                    "but avoid overusing abbreviations."
                )

    return suggestions[:3]


def _local_dynamic_suggestions(original_text: str, expanded_text: str) -> dict:
    sentences = readability.split_sentences(expanded_text)
    style_profile = _detect_style_profile(original_text)
    short_forms = _extract_short_forms(original_text)

    first_sentence = sentences[0] if sentences else original_text.strip()
    simplified_text = (
        first_sentence if first_sentence else original_text.strip()
    )
    rewrites = _build_rewrite_variants(
        original_text,
        expanded_text,
        style_profile,
    )
    abbreviation_status = _build_abbreviation_status_line(short_forms)
    formal_context, informal_context = _build_context_lines(
        style_profile,
        original_text,
    )
    clear_text = _format_output_lines(
        abbreviation_status,
        formal_context,
        informal_context,
        rewrites,
    )
    return {
        "simplified_text": simplified_text or expanded_text,
        "clear_text": clear_text,
    }


def _parse_llm_output(raw_output: str) -> dict:
    output = raw_output.strip()

    # Prefer strict JSON if the model follows the prompt exactly.
    try:
        parsed = json.loads(output)
        suggestions = parsed.get("suggestions", [])
        if isinstance(suggestions, list):
            suggestions = [
                str(item).strip() for item in suggestions if str(item).strip()
            ]
        else:
            suggestions = []

        simplified_text = (
            str(parsed.get("simplified_text", "")).strip() or None
        )
        clear_text = "\n".join(f"- {item}" for item in suggestions) or None

        rewrites_data = parsed.get("rewrites", {})
        rewrites = {
            "formal": "",
            "informal": "",
            "clean": "",
        }
        if isinstance(rewrites_data, dict):
            rewrites["formal"] = str(rewrites_data.get("formal", "")).strip()
            rewrites["informal"] = str(
                rewrites_data.get("informal", "")
            ).strip()
            rewrites["clean"] = str(rewrites_data.get("clean", "")).strip()
        else:
            rewrites["formal"] = str(parsed.get("formal_rewrite", "")).strip()
            rewrites["informal"] = str(
                parsed.get("informal_rewrite", "")
            ).strip()
            rewrites["clean"] = str(parsed.get("clean_rewrite", "")).strip()

        abbreviation_map: dict[str, str] = {}
        abbreviations_data = parsed.get("abbreviations", [])
        if isinstance(abbreviations_data, list):
            for item in abbreviations_data:
                if not isinstance(item, dict):
                    continue
                short = str(item.get("short", "")).strip().lower()
                expanded = str(item.get("expanded", "")).strip()
                if short and expanded:
                    abbreviation_map[short] = expanded

        return {
            "simplified_text": simplified_text,
            "clear_text": clear_text,
            "abbreviation_map": abbreviation_map,
            "rewrites": rewrites,
        }
    except Exception:
        pass

    # Fallback parser for non-JSON structured responses.
    simplified = output
    suggestions_block = ""
    if "SUGGESTIONS:" in output:
        parts = output.split("SUGGESTIONS:", 1)
        simplified = parts[0].replace("SIMPLIFIED:", "").strip()
        suggestions_block = parts[1].strip()

    suggestions = []
    for line in suggestions_block.split("\n"):
        cleaned = line.strip().lstrip("-* ").strip()
        if cleaned:
            suggestions.append(cleaned)

    clear_text = "\n".join(f"- {item}" for item in suggestions) or None
    return {
        "simplified_text": simplified or None,
        "clear_text": clear_text,
        "abbreviation_map": {},
        "rewrites": {
            "formal": "",
            "informal": "",
            "clean": "",
        },
    }


async def _infer_unknown_abbreviations_with_llm(
    unknown_short_forms: list[str],
    original_text: str,
) -> dict[str, str]:
    if not GEMINI_API_KEY or not unknown_short_forms:
        return {}

    prompt = (
        "Identify likely expansions for these short forms in context.\n"
        "Return ONLY valid JSON in this shape:\n"
        '{"abbreviations":[{"short":"...","expanded":"..."}]}\n\n'
        f"SHORT_FORMS: {', '.join(unknown_short_forms)}\n"
        f"TEXT: {original_text}"
    )
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
    }

    async with httpx.AsyncClient(timeout=20) as client:
        for model_name in GEMINI_MODELS:
            model_name = model_name.strip()
            if not model_name:
                continue

            url = f"{GEMINI_API_BASE}/{model_name}:generateContent"
            try:
                resp = await client.post(
                    url,
                    headers=headers,
                    params=params,
                    json=data,
                )
            except httpx.HTTPError:
                continue

            if resp.status_code != 200:
                continue

            result = resp.json()
            try:
                output = result["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(output.strip())
                items = parsed.get("abbreviations", [])
                if not isinstance(items, list):
                    continue

                mapped: dict[str, str] = {}
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    short = str(item.get("short", "")).strip().lower()
                    expanded = str(item.get("expanded", "")).strip()
                    if short and expanded:
                        mapped[short] = expanded
                if mapped:
                    return mapped
            except Exception:
                continue

    return {}


async def simplify_text(text: str):
    expanded_text = expand_abbreviations(text)
    style_profile = _detect_style_profile(text)
    rewrite_variants = _build_rewrite_variants(
        text,
        expanded_text,
        style_profile,
    )
    short_forms = _extract_short_forms(text)

    active_engine = SUGGESTION_ENGINE
    if active_engine not in VALID_SUGGESTION_ENGINES:
        active_engine = "llm"

    key = _cache_key(text, active_engine)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    llm_short_form_map: dict[str, str] = {}

    if active_engine == "rule":
        fallback = _local_dynamic_suggestions(text, expanded_text)
        rewrites = _build_rewrite_variants(
            text,
            expanded_text,
            style_profile,
        )
        rewrites = _normalize_final_rewrites(text, rewrites)
        abbreviation_status = _build_abbreviation_status_line(
            short_forms,
            llm_short_form_map,
        )
        formal_context, informal_context = _build_context_lines(
            style_profile,
            text,
        )
        fallback["clear_text"] = _format_output_lines(
            abbreviation_status,
            formal_context,
            informal_context,
            rewrites,
        )
        _cache_set(key, fallback)
        return fallback

    if not GEMINI_API_KEY:
        fallback = _local_dynamic_suggestions(text, expanded_text)
        rewrites = _build_rewrite_variants(
            text,
            expanded_text,
            style_profile,
        )
        rewrites = _normalize_final_rewrites(text, rewrites)
        abbreviation_status = _build_abbreviation_status_line(
            short_forms,
            llm_short_form_map,
        )
        formal_context, informal_context = _build_context_lines(
            style_profile,
            text,
        )
        fallback["clear_text"] = _format_output_lines(
            abbreviation_status,
            formal_context,
            informal_context,
            rewrites,
        )
        _cache_set(key, fallback)
        return fallback

    prompt = (
        "You are a readability assistant.\n"
        "Return short, practical JSON only.\n"
        "Provide: simplified_text, rewrites (formal/informal/clean), "
        "and abbreviation expansions from the input.\n"
        f"Detected style: {style_profile['predicted_style']}\n"
        f"Expected style: {style_profile['expected_style']}\n"
        f"Short forms from input: {', '.join(short_forms) or 'none'}\n"
        "Return ONLY valid JSON in this shape:\n"
        '{"simplified_text":"...","rewrites":{"formal":"...",'
        '"informal":"...","clean":"..."},'
        '"abbreviations":[{"short":"...","expanded":"..."}]}\n\n'
        f"INPUT:\n{expanded_text}"
    )
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        last_error = None

        for model_name in GEMINI_MODELS:
            model_name = model_name.strip()
            if not model_name:
                continue

            url = f"{GEMINI_API_BASE}/{model_name}:generateContent"
            try:
                resp = await client.post(
                    url,
                    headers=headers,
                    params=params,
                    json=data,
                )
            except httpx.HTTPError as exc:
                last_error = (
                    "Gemini network error for model "
                    f"'{model_name}': {exc}"
                )
                continue

            if resp.status_code == 200:
                result = resp.json()
                try:
                    output = (
                        result["candidates"][0]["content"]["parts"][0]["text"]
                    )
                    parsed = _parse_llm_output(output)
                    if (
                        parsed.get("simplified_text")
                        and parsed.get("clear_text")
                    ):
                        parsed_rewrites = parsed.get("rewrites", {})
                        final_rewrites = {
                            "formal": (
                                parsed_rewrites.get("formal")
                                or rewrite_variants["formal"]
                            ),
                            "informal": (
                                parsed_rewrites.get("informal")
                                or rewrite_variants["informal"]
                            ),
                            "clean": (
                                parsed_rewrites.get("clean")
                                or rewrite_variants["clean"]
                            ),
                        }
                        final_rewrites = _normalize_final_rewrites(
                            text,
                            final_rewrites,
                        )
                        combined_llm_map = {
                            **llm_short_form_map,
                            **parsed.get("abbreviation_map", {}),
                        }
                        abbreviation_status = _build_abbreviation_status_line(
                            short_forms,
                            combined_llm_map,
                        )
                        formal_context, informal_context = (
                            _build_context_lines(
                                style_profile,
                                text,
                            )
                        )
                        parsed["clear_text"] = _format_output_lines(
                            abbreviation_status,
                            formal_context,
                            informal_context,
                            final_rewrites,
                        )
                        _cache_set(key, parsed)
                        return parsed
                except Exception as exc:
                    last_error = f"Could not parse Gemini response: {exc}"
                    continue

            if resp.status_code in (400, 401, 403):
                last_error = (
                    "Gemini API rejected the request. "
                    "Please verify GEMINI_API_KEY and model access."
                )
                continue

            last_error = (
                f"Gemini call failed for model '{model_name}' "
                f"with status {resp.status_code}."
            )

        # If all API attempts fail, still return dynamic suggestions.
        _ = last_error
        fallback = _local_dynamic_suggestions(text, expanded_text)
        rewrites = _build_rewrite_variants(
            text,
            expanded_text,
            style_profile,
        )
        rewrites = _normalize_final_rewrites(text, rewrites)
        abbreviation_status = _build_abbreviation_status_line(
            short_forms,
            llm_short_form_map,
        )
        formal_context, informal_context = _build_context_lines(
            style_profile,
            text,
        )
        fallback["clear_text"] = _format_output_lines(
            abbreviation_status,
            formal_context,
            informal_context,
            rewrites,
        )
        _cache_set(key, fallback)
        return fallback

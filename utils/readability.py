import re

SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
WORD_RE = re.compile(r"\b[a-zA-Z0-9']+\b")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\U00002700-\U000027BF]")
SYMBOL_RE = re.compile(r"[^\w\s,.!?']")
MULTI_PUNCT_RE = re.compile(r"([!?])\1+")


def split_sentences(text: str) -> list[str]:
    if not text:
        return []
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]


def count_sentences(text: str) -> int:
    return max(1, len(split_sentences(text)))


def tokenize_words(text: str) -> list[str]:
    return WORD_RE.findall(text)


def extract_symbol_emoji_stats(text: str) -> dict:
    if not text:
        return {
            "emoji_count": 0,
            "symbol_count": 0,
        }

    emoji_count = len(EMOJI_RE.findall(text))
    symbol_count = len(SYMBOL_RE.findall(text))

    return {
        "emoji_count": emoji_count,
        "symbol_count": symbol_count,
    }


def count_words(text: str) -> int:
    return len(tokenize_words(text))


def count_syllables_in_word(word: str) -> int:
    cleaned = re.sub(r"[^a-z]", "", word.lower())
    if not cleaned:
        return 1

    vowels = "aeiouy"
    syllables = 0
    prev_is_vowel = False
    for char in cleaned:
        is_vowel = char in vowels
        if is_vowel and not prev_is_vowel:
            syllables += 1
        prev_is_vowel = is_vowel

    if cleaned.endswith("e") and syllables > 1:
        syllables -= 1

    return max(1, syllables)


def total_syllables(text: str) -> int:
    words = tokenize_words(text)
    if not words:
        return 0
    return sum(count_syllables_in_word(word) for word in words)


def flesch_reading_ease(sentences: int, words: int, syllables: int) -> float:
    safe_sentences = max(1, sentences)
    safe_words = max(1, words)
    return 206.835 - 1.015 * (words / safe_sentences) - 84.6 * (
        syllables / safe_words
    )


def flesch_kincaid_grade(sentences: int, words: int, syllables: int) -> float:
    safe_sentences = max(1, sentences)
    safe_words = max(1, words)
    return 0.39 * (words / safe_sentences) + 11.8 * (
        syllables / safe_words
    ) - 15.59


def analyze_text_profile(original_text: str, metrics_text: str) -> dict:
    sentences = split_sentences(metrics_text)
    words = tokenize_words(metrics_text)
    sentence_count = max(1, len(sentences))
    word_count = len(words)
    syllables = total_syllables(metrics_text)

    reading_ease = flesch_reading_ease(
        sentence_count,
        max(1, word_count),
        syllables,
    )
    grade_level = flesch_kincaid_grade(
        sentence_count,
        max(1, word_count),
        syllables,
    )

    avg_sentence_len = 0.0
    if sentence_count:
        avg_sentence_len = word_count / sentence_count

    avg_word_len = 0.0
    if word_count:
        avg_word_len = sum(len(word) for word in words) / word_count

    lexical_diversity = 0.0
    if word_count:
        lexical_diversity = len({w.lower() for w in words}) / word_count

    punctuation_emphasis = len(MULTI_PUNCT_RE.findall(original_text))
    uppercase_tokens = len(
        [word for word in tokenize_words(original_text) if word.isupper()]
    )
    symbol_emoji_stats = extract_symbol_emoji_stats(original_text)

    return {
        "sentences": sentence_count,
        "words": word_count,
        "syllables": syllables,
        "reading_ease": round(min(121.22, max(0.0, reading_ease)), 2),
        "grade_level": round(max(0.0, grade_level), 2),
        "avg_sentence_len": round(avg_sentence_len, 2),
        "avg_word_len": round(avg_word_len, 2),
        "lexical_diversity": round(lexical_diversity, 2),
        "punctuation_emphasis": punctuation_emphasis,
        "uppercase_tokens": uppercase_tokens,
        "emoji_count": symbol_emoji_stats["emoji_count"],
        "symbol_count": symbol_emoji_stats["symbol_count"],
    }

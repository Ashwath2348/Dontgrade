import csv
import re
from pathlib import Path

ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "archive (4)"
DATASET_PATHS = [
    ARCHIVE_DIR / "abbrevations.csv",
    (
        ARCHIVE_DIR
        / "Abbreviations short forms slangs and their meanings - Sheet1.csv"
    ),
]


def _split_abbreviation_keys(raw_abbr: str) -> list[str]:
    cleaned = raw_abbr.strip().strip('"').strip("'")
    if not cleaned:
        return []

    # Some rows store multiple keys in one cell (e.g. "FYI / JFYI", "B2K BTK").
    parts = re.split(r"\s*/\s*|\s*,\s*|\s+", cleaned)
    keys: list[str] = []
    for part in parts:
        token = part.strip().lower()
        if not token:
            continue
        token = token.strip('"').strip("'")
        if token and token not in keys:
            keys.append(token)
    return keys


def _split_abbreviation_keys_raw(raw_abbr: str) -> list[str]:
    cleaned = raw_abbr.strip().strip('"').strip("'")
    if not cleaned:
        return []
    return [
        part.strip().strip('"').strip("'")
        for part in re.split(r"\s*/\s*|\s*,\s*|\s+", cleaned)
        if part.strip().strip('"').strip("'")
    ]


def load_abbreviation_multi_map() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for dataset_path in DATASET_PATHS:
        if not dataset_path.exists():
            continue

        with dataset_path.open(
            "r",
            encoding="utf-8",
            errors="ignore",
        ) as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                if len(row) < 2:
                    continue

                raw_abbr = row[0].strip()
                expanded = row[1].strip()
                if not raw_abbr or not expanded:
                    continue

                if raw_abbr.lower() in {"word", "abbreviation"}:
                    continue
                if expanded.lower() == "meaning":
                    continue

                keys = _split_abbreviation_keys(raw_abbr)
                if not keys:
                    continue

                for abbr in keys:
                    values = mapping.setdefault(abbr, [])
                    if expanded not in values:
                        values.append(expanded)
    return mapping


def load_uppercase_dataset_keys() -> set[str]:
    keys: set[str] = set()
    for dataset_path in DATASET_PATHS:
        if not dataset_path.exists():
            continue

        with dataset_path.open(
            "r",
            encoding="utf-8",
            errors="ignore",
        ) as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                if len(row) < 2:
                    continue

                raw_abbr = row[0].strip()
                for token in _split_abbreviation_keys_raw(raw_abbr):
                    if (
                        token.isalpha()
                        and token.isupper()
                        and len(token) >= 3
                    ):
                        keys.add(token.lower())
    return keys


def load_lowercase_dataset_keys() -> set[str]:
    keys: set[str] = set()
    for dataset_path in DATASET_PATHS:
        if not dataset_path.exists():
            continue

        with dataset_path.open(
            "r",
            encoding="utf-8",
            errors="ignore",
        ) as csv_file:
            reader = csv.reader(csv_file)
            for row in reader:
                if len(row) < 2:
                    continue

                raw_abbr = row[0].strip()
                for token in _split_abbreviation_keys_raw(raw_abbr):
                    if (
                        token.isalpha()
                        and token.islower()
                        and 3 <= len(token) <= 6
                    ):
                        keys.add(token)
    return keys


ABBREVIATION_MULTI_MAP = load_abbreviation_multi_map()
UPPERCASE_DATASET_KEYS = load_uppercase_dataset_keys()
LOWERCASE_DATASET_KEYS = load_lowercase_dataset_keys()
ABBREVIATION_MAP = {
    abbr: expansions[0]
    for abbr, expansions in ABBREVIATION_MULTI_MAP.items()
    if expansions
}

LOWERCASE_SAFE_EXPANSIONS = {
    "asap",
    "fyi",
    "idk",
    "imo",
    "imho",
    "brb",
    "ttyl",
    "lol",
    "lmao",
    "gm",
    "gn",
    "wyd",
    "omw",
    "thx",
    "pls",
    "tbh",
    "btw",
    "afaik",
}

COMMON_WORD_BLOCKLIST = {
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
    "have",
    "he",
    "her",
    "him",
    "his",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "she",
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


def get_abbreviation_expansions(abbr: str) -> list[str]:
    return ABBREVIATION_MULTI_MAP.get(abbr.lower(), [])


def is_likely_abbreviation(token: str) -> bool:
    lower_token = token.lower()
    if lower_token not in ABBREVIATION_MAP:
        return False

    if lower_token in COMMON_WORD_BLOCKLIST and not token.isupper():
        return False

    if any(char.isdigit() for char in token):
        return True
    if token.isupper() and len(token) >= 2:
        return True
    if lower_token in UPPERCASE_DATASET_KEYS:
        return True
    if lower_token in LOWERCASE_DATASET_KEYS:
        return True
    if lower_token.isalpha() and len(lower_token) >= 3:
        return True
    if len(lower_token) <= 2 and lower_token not in {"a", "i"}:
        return True
    if lower_token in LOWERCASE_SAFE_EXPANSIONS:
        return True
    if token != lower_token:
        return True
    return False


def expand_abbreviations(text: str) -> str:
    if not text or not ABBREVIATION_MAP:
        return text

    # Replace tokens while preserving punctuation around words.
    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        if not is_likely_abbreviation(token):
            return token
        lower_token = token.lower()
        return ABBREVIATION_MAP.get(lower_token, token)

    return re.sub(r"\b[\w@#'*/^;<>?]+\b", _replace, text)

import csv
import re
from pathlib import Path

DATASET_PATH = Path(__file__).resolve(
).parents[2] / "archive (4)" / "abbrevations.csv"


def load_abbreviation_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not DATASET_PATH.exists():
        return mapping

    with DATASET_PATH.open("r", encoding="utf-8", errors="ignore") as csv_file:
        reader = csv.reader(csv_file)
        for row in reader:
            if len(row) < 2:
                continue
            abbr = row[0].strip().lower()
            expanded = row[1].strip()
            if not abbr or not expanded:
                continue
            mapping.setdefault(abbr, expanded)
    return mapping


ABBREVIATION_MAP = load_abbreviation_map()


def expand_abbreviations(text: str) -> str:
    if not text or not ABBREVIATION_MAP:
        return text

    # Replace tokens while preserving punctuation around words.
    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        lower_token = token.lower()
        return ABBREVIATION_MAP.get(lower_token, token)

    return re.sub(r"\b[\w@#'*/^;<>?]+\b", _replace, text)

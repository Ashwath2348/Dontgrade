import os

import httpx

from ..utils.abbreviations import expand_abbreviations

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-1.5-flash-latest:generateContent"
)


def _fallback_suggestions(text: str) -> dict:
    trimmed = " ".join(text.split())
    if not trimmed:
        return {"simplified_text": None, "clear_text": None}

    normalized = trimmed.replace("!", ".").replace("?", ".")
    sentences = [s.strip() for s in normalized.split(".") if s.strip()]
    base = sentences[0] if sentences else trimmed
    suggestions = [
        f"Use direct language: {base}.",
        "Split long ideas into shorter sentences for better readability.",
        "Prefer concrete words and remove filler phrases where possible.",
    ]
    return {
        "simplified_text": base,
        "clear_text": "\n".join(f"- {item}" for item in suggestions),
    }


async def simplify_text(text: str):
    expanded_text = expand_abbreviations(text)
    if not GEMINI_API_KEY:
        return _fallback_suggestions(expanded_text)

    prompt = (
        "You are a readability assistant.\n"
        "1) Expand informal abbreviations where needed.\n"
        "2) Provide one simplified paragraph.\n"
        "3) Provide 3 short bullet rewrite suggestions for clarity.\n\n"
        "Return exact format:\n"
        "SIMPLIFIED:\n<paragraph>\n\n"
        "SUGGESTIONS:\n- <suggestion 1>\n"
        "- <suggestion 2>\n- <suggestion 3>\n\n"
        f"INPUT:\n{expanded_text}"
    )
    headers = {"Content-Type": "application/json"}
    params = {"key": GEMINI_API_KEY}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
    }
    async with httpx.AsyncClient(
        timeout=30,
    ) as client:
        resp = await client.post(
            GEMINI_API_URL,
            headers=headers,
            params=params,
            json=data,
        )
        if resp.status_code == 200:
            result = resp.json()
            try:
                output = result["candidates"][0]["content"]["parts"][0]["text"]
                simplified = output
                suggestions = output
                if "SUGGESTIONS:" in output:
                    parts = output.split("SUGGESTIONS:", 1)
                    simplified = parts[0].replace("SIMPLIFIED:", "").strip()
                    suggestions = parts[1].strip()
                if not suggestions.strip():
                    return _fallback_suggestions(expanded_text)
                return {
                    "simplified_text": simplified,
                    "clear_text": suggestions,
                }
            except Exception:
                return _fallback_suggestions(expanded_text)

        return _fallback_suggestions(expanded_text)

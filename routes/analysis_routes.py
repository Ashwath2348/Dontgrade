from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..services import gemini
from ..utils.abbreviations import expand_abbreviations
from ..utils import readability

router = APIRouter()


@router.post("/analyze", response_model=schemas.TextAnalysisOut)
async def analyze(
    req: schemas.TextAnalysisCreate,
    db: Session = Depends(auth.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    text = req.input_text
    metrics_text = expand_abbreviations(text)
    sentences = readability.count_sentences(metrics_text)
    words = readability.count_words(metrics_text)
    syllables = readability.total_syllables(metrics_text)

    reading_ease_raw = readability.flesch_reading_ease(
        sentences,
        words,
        syllables,
    )
    grade_level_raw = readability.flesch_kincaid_grade(
        sentences,
        words,
        syllables,
    )

    # Clamp formula output to practical UI ranges.
    reading_ease = round(min(121.22, max(0.0, reading_ease_raw)), 2)
    grade_level = round(max(0.0, grade_level_raw), 2)

    symbol_emoji_stats = readability.extract_symbol_emoji_stats(text)
    noise_count = (
        symbol_emoji_stats["emoji_count"]
        + symbol_emoji_stats["symbol_count"]
    )
    if noise_count > 0:
        # Penalize readability slightly for heavy symbol/emoji usage.
        reading_ease = round(
            max(0.0, reading_ease - min(15.0, noise_count * 1.5)),
            2,
        )
        grade_level = round(grade_level + min(2.5, noise_count * 0.2), 2)

    gemini_result = await gemini.simplify_text(text)

    simplified_text = gemini_result.get("simplified_text")
    clear_text = gemini_result.get("clear_text")
    analysis = models.TextAnalysis(
        user_id=current_user.id,
        input_text=text,
        grade_level=grade_level,
        reading_ease=reading_ease,
        simplified_text=simplified_text,
        clear_text=clear_text
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return analysis


@router.get("/history", response_model=list[schemas.TextAnalysisOut])
def history(
    db: Session = Depends(auth.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    analyses = (
        db.query(models.TextAnalysis)
        .filter(models.TextAnalysis.user_id == current_user.id)
        .order_by(models.TextAnalysis.created_at.desc())
        .all()
    )
    return analyses

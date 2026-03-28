from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas, auth
from ..services import gemini
from ..utils import readability

router = APIRouter()


@router.post("/analyze", response_model=schemas.TextAnalysisOut)
async def analyze(
    req: schemas.TextAnalysisCreate,
    db: Session = Depends(auth.get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    text = req.input_text
    sentences = readability.count_sentences(text)
    words = readability.count_words(text)
    syllables = readability.total_syllables(text)
    reading_ease = readability.flesch_reading_ease(sentences, words, syllables)
    grade_level = readability.flesch_kincaid_grade(sentences, words, syllables)
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

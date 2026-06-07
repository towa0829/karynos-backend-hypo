import uuid
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from models import Job, History, DreamerProfile
from schemas import AnalyzeRequest, RecommendResponse, Recommendation
from vector import generate_profile_with_openai, search_jobs

router = APIRouter(prefix="/api/v1/recommend", tags=["recommend"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _save_profile(dreamer_id: str, job_scores: list, db: Session):
    data = json.dumps(job_scores)
    db.execute(
        text("""
            INSERT INTO dreamer_profiles (dreamer_id, job_scores, updated_at)
            VALUES (:did, CAST(:data AS jsonb), NOW())
            ON CONFLICT (dreamer_id)
            DO UPDATE SET job_scores = CAST(:data AS jsonb), updated_at = NOW()
        """),
        {"did": dreamer_id, "data": data},
    )
    db.commit()


def _load_profile(dreamer_id: str, db: Session) -> list:
    row = db.query(DreamerProfile).filter_by(dreamer_id=dreamer_id).first()
    if not row:
        return []
    scores = row.job_scores
    return scores if isinstance(scores, list) else []


def _pop_next(dreamer_id: str, db: Session):
    """Return head job_score dict and persist the tail."""
    scores = _load_profile(dreamer_id, db)
    if not scores:
        return None
    head, tail = scores[0], scores[1:]
    _save_profile(dreamer_id, tail, db)
    return head


def _reorder(dreamer_id: str, job_id: int, boost: bool, db: Session):
    scores = _load_profile(dreamer_id, db)
    target = [s for s in scores if s["job_id"] == job_id]
    others = [s for s in scores if s["job_id"] != job_id]
    if not target:
        return
    if boost:
        # 好評 → 先頭へ
        new_scores = target + others
    else:
        # 不評 → 末尾へ
        new_scores = others + target
    _save_profile(dreamer_id, new_scores, db)


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/analyze")
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db)):
    """Analyze answers and build ranked job list."""
    answers = [a.dict() for a in req.answers]
    profile_text = generate_profile_with_openai(answers)
    job_scores = search_jobs(profile_text)

    # Filter to existing jobs only
    db.expire_all()
    all_jobs = db.query(Job).all()
    job_id_set = {j.job_id for j in all_jobs}
    job_scores = [s for s in job_scores if s["job_id"] in job_id_set]

    _save_profile(req.dreamer_id, job_scores, db)
    return {"status": "ok", "matched": len(job_scores)}


@router.get("/{dreamer_id}", response_model=RecommendResponse)
def recommend(dreamer_id: str, db: Session = Depends(get_db)):
    """Return the next recommended job."""
    item = _pop_next(dreamer_id, db)
    if not item:
        raise HTTPException(status_code=404, detail="No more recommendations")

    job_id = item["job_id"]
    score = item.get("score", 0.0)

    db.expire_all()
    job = db.query(Job).filter_by(job_id=job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    history = History(
        history_id=uuid.uuid4(),
        dreamer_id=dreamer_id,
        job_id=job_id,
    )
    db.add(history)
    db.commit()
    db.refresh(history)

    return RecommendResponse(
        recommendation=Recommendation(
            job_id=job.job_id,
            history_id=str(history.history_id),
            name=job.name,
            salary=job.salary or 0,
            age=job.age or 0,
            imgs=job.imgs or [],
            description=job.description or "",
            similarity_score=score,
        )
    )


@router.post("/{dreamer_id}/good")
def good(dreamer_id: str, history_id: str, db: Session = Depends(get_db)):
    history = db.query(History).filter_by(history_id=history_id).first()
    if not history:
        raise HTTPException(status_code=404, detail="History not found")
    history.good = True
    db.commit()
    _reorder(dreamer_id, history.job_id, boost=True, db=db)
    return {"status": "ok"}


@router.post("/{dreamer_id}/bad")
def bad(dreamer_id: str, history_id: str, db: Session = Depends(get_db)):
    history = db.query(History).filter_by(history_id=history_id).first()
    if not history:
        raise HTTPException(status_code=404, detail="History not found")
    history.bad = True
    db.commit()
    _reorder(dreamer_id, history.job_id, boost=False, db=db)
    return {"status": "ok"}

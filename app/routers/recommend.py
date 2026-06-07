import uuid
import json
import re
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from sqlalchemy import func
from models import Job, JobImage, JobFeedback, History, DreamerProfile
from schemas import (
    AnalyzeRequest,
    RecommendResponse,
    Recommendation,
    JobSummary,
    ResultResponse,
)
from vector import generate_profile_with_openai, search_jobs

router = APIRouter(prefix="/api/v1/recommend", tags=["recommend"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _save_profile(dreamer_id: str, job_scores: list, db: Session):
    """Update only the consumable queue (job_scores)."""
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


def _init_profile(dreamer_id: str, job_scores: list, profile_text: str, db: Session):
    """Initialize profile at analyze time: consumable queue + immutable ranking + text."""
    data = json.dumps(job_scores)
    db.execute(
        text("""
            INSERT INTO dreamer_profiles (dreamer_id, job_scores, original_scores, profile_text, updated_at)
            VALUES (:did, CAST(:data AS jsonb), CAST(:data AS jsonb), :ptext, NOW())
            ON CONFLICT (dreamer_id)
            DO UPDATE SET job_scores = CAST(:data AS jsonb),
                          original_scores = CAST(:data AS jsonb),
                          profile_text = :ptext,
                          updated_at = NOW()
        """),
        {"did": dreamer_id, "data": data, "ptext": profile_text},
    )
    db.commit()


def _job_detail(job_id: int, score: float, db: Session) -> dict:
    """Fetch job name/description + avg salary/age + image list."""
    job = db.query(Job).filter_by(job_id=job_id).first()
    if not job:
        return None

    fb = db.query(
        func.round(func.avg(JobFeedback.salary)).label("salary"),
        func.round(func.avg(JobFeedback.age)).label("age"),
    ).filter(JobFeedback.job_id == job_id).first()

    imgs = [r.img_url for r in db.query(JobImage).filter_by(job_id=job_id).all()]

    return {
        "job_id": job.job_id,
        "name": job.name,
        "salary": int(fb.salary) if fb and fb.salary else 0,
        "age": int(fb.age) if fb and fb.age else 0,
        "imgs": imgs,
        "description": job.description or "",
        "similarity_score": score,
    }


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
    # profile_text は表示用の HTML フラグメント
    profile_text = generate_profile_with_openai(answers)
    # 検索には HTML タグを除去したプレーンテキストを使う（検索精度を保つ）
    search_text = re.sub(r"<[^>]+>", " ", profile_text)
    job_scores = search_jobs(search_text)

    # Filter to existing jobs only
    db.expire_all()
    all_jobs = db.query(Job.job_id).all()
    job_id_set = {j.job_id for j in all_jobs}
    job_scores = [s for s in job_scores if s["job_id"] in job_id_set]

    _init_profile(req.dreamer_id, job_scores, profile_text, db)
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
    detail = _job_detail(job_id, score, db)
    if not detail:
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
            history_id=str(history.history_id),
            **detail,
        )
    )


@router.get("/{dreamer_id}/result", response_model=ResultResponse)
def result(dreamer_id: str, db: Session = Depends(get_db)):
    """診断結果: 性格分析文 + いいねした職業 + 適合度トップ5"""
    db.expire_all()
    profile = db.query(DreamerProfile).filter_by(dreamer_id=dreamer_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    original = profile.original_scores if isinstance(profile.original_scores, list) else []
    score_map = {s["job_id"]: s.get("score", 0.0) for s in original}

    # いいねした職業 (good=true)、重複job_id排除、適合度順
    liked_ids = [
        h.job_id
        for h in db.query(History)
        .filter_by(dreamer_id=dreamer_id, good=True)
        .all()
    ]
    seen = set()
    unique_liked = []
    for jid in liked_ids:
        if jid not in seen:
            seen.add(jid)
            unique_liked.append(jid)
    unique_liked.sort(key=lambda j: score_map.get(j, 0.0), reverse=True)

    liked_jobs = []
    for jid in unique_liked:
        d = _job_detail(jid, score_map.get(jid, 0.0), db)
        if d:
            liked_jobs.append(JobSummary(**d))

    # 適合度トップ5
    top_matches = []
    for s in original[:5]:
        d = _job_detail(s["job_id"], s.get("score", 0.0), db)
        if d:
            top_matches.append(JobSummary(**d))

    return ResultResponse(
        personality_text=profile.profile_text or "",
        liked_jobs=liked_jobs,
        top_matches=top_matches,
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

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Dreamer
from schemas import CreateDreamerRequest, CreateDreamerResponse

router = APIRouter(prefix="/api/v1/dreamers", tags=["dreamers"])


@router.post("", response_model=CreateDreamerResponse)
def create_dreamer(req: CreateDreamerRequest, db: Session = Depends(get_db)):
    dreamer = Dreamer(
        dreamer_id=uuid.uuid4(),
        name_family=req.name_family,
        name_given=req.name_given,
    )
    db.add(dreamer)
    db.commit()
    db.refresh(dreamer)
    return CreateDreamerResponse(dreamer_id=str(dreamer.dreamer_id))

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.security import HealthRead

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthRead)
def health_check(db: OrmSession = Depends(get_db)) -> HealthRead:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    return HealthRead(status="ok", service=get_settings().app_name, database="connected")

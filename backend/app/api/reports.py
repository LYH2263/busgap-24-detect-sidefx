import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import BunchReport
from app.services.detection_runs import LineNotFoundError, run_detection
from app.services.timeline_marks import build_timeline

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("")
def list_reports(db: Session = Depends(get_db)):
    rows = db.scalars(select(BunchReport).order_by(BunchReport.id.desc())).all()
    return [
        {
            "id": r.id,
            "line_id": r.line_id,
            "stop_name": r.stop_name,
            "created_at": r.created_at.isoformat(),
            "events": json.loads(r.summary_json),
        }
        for r in rows
    ]


@router.post("/run")
def run_report(line_id: int, stop_name: str | None = None, dry_run: bool = False, db: Session = Depends(get_db)):
    """真检落库；dry_run=true 仅试算，报告与时间轴零增量。"""
    try:
        outcome = run_detection(db, line_id=line_id, stop_name=stop_name, dry_run=dry_run)
    except LineNotFoundError as exc:
        raise HTTPException(status_code=404, detail="线路不存在") from exc
    return {
        "id": outcome.report_id,
        "dry_run": outcome.dry_run,
        "persisted": outcome.persisted,
        "events": list(outcome.events),
    }


@router.get("/suggestions")
def suggestions(line_id: int, db: Session = Depends(get_db)):
    """建议是只读视图：以试算方式检测，不向报告表写行。"""
    try:
        outcome = run_detection(db, line_id=line_id, stop_name=None, dry_run=True)
    except LineNotFoundError as exc:
        raise HTTPException(status_code=404, detail="线路不存在") from exc
    return {
        "line_id": line_id,
        "suggestions": [e for e in outcome.events if e["status"] != "normal"],
    }


@router.get("/timeline")
def timeline(line_id: int, stop_name: str = "市民中心", db: Session = Depends(get_db)):
    return build_timeline(db, line_id, stop_name).as_dict()

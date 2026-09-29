"""报告表巡检：数行数、读最新报告、确认串车事件。

场景脚本通过本模块核对检测写库的副作用，不直接拼 SQL，也不在脚本里写死
报告应当有几行——基准一律来自 :mod:`app.services.seed_anchor`。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import BunchReport


@dataclass(frozen=True)
class LatestReport:
    id: int
    line_id: int
    stop_name: str
    events: tuple[dict, ...]

    def events_at(self, stop_name: str) -> tuple[dict, ...]:
        return tuple(e for e in self.events if e.get("stop_name") == stop_name)


@dataclass(frozen=True)
class StopEvent:
    """最新报告里某站点最后一条串车事件（即“最新事件”）。"""

    report_id: int
    stop_name: str
    earlier_trip: str
    later_trip: str
    gap_min: float


def count_reports(db: Session, line_id: int | None = None) -> int:
    stmt = select(func.count()).select_from(BunchReport)
    if line_id is not None:
        stmt = stmt.where(BunchReport.line_id == line_id)
    return int(db.scalar(stmt) or 0)


def latest_report(db: Session, line_id: int | None = None) -> LatestReport | None:
    stmt = select(BunchReport).order_by(BunchReport.id.desc())
    if line_id is not None:
        stmt = stmt.where(BunchReport.line_id == line_id)
    row = db.scalars(stmt).first()
    if row is None:
        return None
    return LatestReport(
        id=row.id,
        line_id=row.line_id,
        stop_name=row.stop_name,
        events=tuple(json.loads(row.summary_json or "[]")),
    )


def latest_bunching_event(
    db: Session, line_id: int, stop_name: str = "市民中心"
) -> StopEvent | None:
    """最新报告里该站点的最后一条 bunching 事件。

    检测按站点分组、每组按时间相邻产生事件；“最新事件”取最新报告中该站点
    事件列表的最后一条（列表顺序即入库快照顺序）。
    """
    report = latest_report(db, line_id=line_id)
    if report is None:
        return None
    matches = [e for e in report.events if e.get("stop_name") == stop_name and e.get("status") == "bunching"]
    if not matches:
        return None
    e = matches[-1]
    return StopEvent(
        report_id=report.id,
        stop_name=stop_name,
        earlier_trip=e["earlier_trip"],
        later_trip=e["later_trip"],
        gap_min=float(e["gap_min"]),
    )


def assert_latest_report_shows_bunching(
    db: Session, line_id: int, stop_name: str = "市民中心"
) -> StopEvent:
    """独立巡检断言：最新报告必须含该站点的串车事件。"""
    count = count_reports(db)
    assert count > 0, "报告表为空，真检必须落一行报告"
    report = latest_report(db, line_id=line_id)
    assert report is not None, f"最新报告不属于线路 {line_id}"
    event = latest_bunching_event(db, line_id=line_id, stop_name=stop_name)
    assert event is not None, (
        f"最新报告 id={report.id} 未记录站点「{stop_name}」串车，"
        "真检成功不得写成空事件或空跑"
    )
    return event

"""检测写库的副作用合同。

唯一允许把检测结果写入 ``bunch_reports`` 的入口。合同条款：

* 线路不存在 —— 抛 :class:`LineNotFoundError`，报告表零增量，时间轴零增量；
* ``dry_run=True``（试算）—— 只算不写，报告行数、时间轴点数相对调用前都不变；
* ``dry_run=False``（真检）—— 报告表恰好新增一行并返回其主键，事件随报告落库，
  不得写成拒绝、不得空跑（事件为空也照常落审计行，由调用方决定如何解读）。

场景脚本只调用本模块触发写库，不直接操作 ORM 的 add/delete。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Arrival, BunchReport, Line, Trip
from app.services.bunch_engine import detect_bunching, events_to_dicts


class LineNotFoundError(LookupError):
    """非法线路编号：检测前置条件不成立。"""


@dataclass(frozen=True)
class DetectionOutcome:
    line_id: int
    stop_name: str
    dry_run: bool
    report_id: int | None
    events: tuple[dict, ...]

    @property
    def persisted(self) -> bool:
        """真检成功落库为 True；试算为 False。"""
        return self.report_id is not None


def _load_events(db: Session, line: Line, stop_name: str | None) -> list[dict]:
    trips = db.scalars(select(Trip).where(Trip.line_id == line.id)).all()
    trip_no_map = {t.id: t.trip_no for t in trips}
    arrivals = db.scalars(
        select(Arrival).where(Arrival.trip_id.in_(list(trip_no_map)))
    ).all()
    payload = [
        {"stop_name": a.stop_name, "trip_no": trip_no_map[a.trip_id], "actual_arrive": a.actual_arrive}
        for a in arrivals
        if stop_name is None or a.stop_name == stop_name
    ]
    return events_to_dicts(
        detect_bunching(payload, line.planned_headway_min, line.bunch_threshold, line.large_threshold)
    )


def run_detection(
    db: Session,
    line_id: int,
    stop_name: str | None = None,
    dry_run: bool = False,
) -> DetectionOutcome:
    """执行检测并按合同处理写库副作用。"""
    line = db.get(Line, line_id)
    if line is None:
        # 非法编号：不允许产生任何待刷新对象，保证报告/时间轴双零增量。
        raise LineNotFoundError(f"线路不存在: {line_id}")

    data = _load_events(db, line, stop_name)
    effective_stop = stop_name or "*"

    if dry_run:
        # 试算：绝不 add，报告表与时间轴点数均不变。
        return DetectionOutcome(
            line_id=line_id, stop_name=effective_stop, dry_run=True, report_id=None, events=tuple(data)
        )

    report = BunchReport(
        line_id=line_id,
        stop_name=effective_stop,
        created_at=datetime.utcnow(),
        summary_json=json.dumps(data, ensure_ascii=False),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return DetectionOutcome(
        line_id=line_id, stop_name=effective_stop, dry_run=False, report_id=report.id, events=tuple(data)
    )

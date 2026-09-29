"""时间轴点的唯一规范构造。

``/reports/timeline`` 接口与时间轴巡检共用本模块，杜绝“接口算一份、
巡检算一份”导致的对不上。时间轴点 = 指定线路、指定站点的全部到站记录，
按实际到站时间排序，点上的班次号即该站点的通过班次。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Arrival, Trip


@dataclass(frozen=True)
class TimelineMark:
    trip_no: str
    actual_arrive: datetime
    pct: float

    def as_dict(self) -> dict:
        return {"trip_no": self.trip_no, "actual_arrive": self.actual_arrive.isoformat(), "pct": self.pct}


@dataclass(frozen=True)
class TimelineView:
    line_id: int
    stop_name: str
    marks: tuple[TimelineMark, ...]

    @property
    def point_count(self) -> int:
        return len(self.marks)

    def trip_nos(self) -> list[str]:
        return [m.trip_no for m in self.marks]

    def index_of(self, trip_no: str) -> int | None:
        nos = self.trip_nos()
        return nos.index(trip_no) if trip_no in nos else None

    def has_point(self, trip_no: str) -> bool:
        return self.index_of(trip_no) is not None

    def as_dict(self) -> dict:
        return {"stop_name": self.stop_name, "marks": [m.as_dict() for m in self.marks]}


def build_timeline(db: Session, line_id: int, stop_name: str = "市民中心") -> TimelineView:
    trips = db.scalars(select(Trip).where(Trip.line_id == line_id)).all()
    trip_no_map = {t.id: t.trip_no for t in trips}
    arrivals = db.scalars(
        select(Arrival).where(Arrival.trip_id.in_(list(trip_no_map)), Arrival.stop_name == stop_name)
    ).all()
    arrivals = sorted(arrivals, key=lambda a: a.actual_arrive)
    if not arrivals:
        return TimelineView(line_id=line_id, stop_name=stop_name, marks=())
    t0 = arrivals[0].actual_arrive
    span = max((arrivals[-1].actual_arrive - t0).total_seconds(), 1)
    marks = tuple(
        TimelineMark(
            trip_no=trip_no_map[a.trip_id],
            actual_arrive=a.actual_arrive,
            pct=round((a.actual_arrive - t0).total_seconds() / span * 100, 2),
        )
        for a in arrivals
    )
    return TimelineView(line_id=line_id, stop_name=stop_name, marks=marks)

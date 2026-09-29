"""种子行数锚点:场景基准的唯一来源。

种子数据就位后捕获一次基准(报告行数与主键集合、市民中心时间轴可见点),
场景里的所有断言都相对锚点算增量,禁止写死魔术数。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import BunchReport, Line


@dataclass(frozen=True)
class TimelinePoint:
    """时间轴可见点(与接口返回的班次号 + 到站时间一一对应)。"""
    trip_no: str
    actual_arrive: str


@dataclass(frozen=True)
class SeedAnchor:
    line_id: int
    stop_name: str
    report_count: int
    report_ids: frozenset[int]
    timeline_points: tuple[TimelinePoint, ...]

    @property
    def timeline_point_count(self) -> int:
        return len(self.timeline_points)

    @classmethod
    def capture(cls, db: Session, client, line_code: str, stop_name: str) -> "SeedAnchor":
        line = db.scalar(select(Line).where(Line.code == line_code))
        assert line is not None, f"种子线路 {line_code} 不存在,锚点无效"
        report_ids = frozenset(db.scalars(select(BunchReport.id)).all())
        marks = client.get(
            "/api/reports/timeline", params={"line_id": line.id, "stop_name": stop_name}
        ).json()["marks"]
        points = tuple(TimelinePoint(m["trip_no"], m["actual_arrive"]) for m in marks)
        assert points, f"种子时间轴在{stop_name}不可见任何点,锚点无效"
        return cls(line_id=line.id, stop_name=stop_name,
                   report_count=len(report_ids), report_ids=report_ids,
                   timeline_points=points)

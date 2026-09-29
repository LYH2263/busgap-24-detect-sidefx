"""时间轴巡检:市民中心点位对账最新报告前后班次号、场景结束恢复种子可见点。

恢复(DELETE)只允许发生在本模块内;裁报告时必须同步恢复时间轴,
禁止只清报告留脏点。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.models.models import Arrival, Trip
from tests.sidefx.anchor import SeedAnchor, TimelinePoint


class TimelineInspector:
    def __init__(self, client, session_factory: sessionmaker, line_id: int, stop_name: str):
        self._client = client
        self._session_factory = session_factory
        self._line_id = line_id
        self._stop_name = stop_name

    def points(self) -> list[TimelinePoint]:
        """当前市民中心时间轴可见点(走接口,即用户可见状态)。"""
        marks = self._client.get(
            "/api/reports/timeline", params={"line_id": self._line_id, "stop_name": self._stop_name}
        ).json()["marks"]
        return [TimelinePoint(m["trip_no"], m["actual_arrive"]) for m in marks]

    def trip_numbers(self) -> set[str]:
        return {p.trip_no for p in self.points()}

    def assert_covers(self, events: list[dict]) -> None:
        """每个事件的前后班次号都必须能在市民中心点位里对上。"""
        trip_numbers = self.trip_numbers()
        for event in events:
            assert event["earlier_trip"] in trip_numbers, \
                f"时间轴{self._stop_name}点位对不上前班次 {event['earlier_trip']}"
            assert event["later_trip"] in trip_numbers, \
                f"时间轴{self._stop_name}点位对不上后班次 {event['later_trip']}"

    def restore_to(self, anchor: SeedAnchor) -> None:
        """恢复种子可见点:删掉锚点之外的脏点,并校验可见点与锚点一致。"""
        wanted = {(p.trip_no, p.actual_arrive) for p in anchor.timeline_points}
        with self._session_factory() as db:
            rows = db.scalars(
                select(Arrival).join(Trip)
                .where(Trip.line_id == self._line_id, Arrival.stop_name == self._stop_name)
            ).all()
            for row in rows:
                key = (row.trip.trip_no, row.actual_arrive.isoformat())
                if key not in wanted:
                    db.delete(row)
            db.commit()
        assert self.points() == list(anchor.timeline_points), \
            f"时间轴{self._stop_name}未恢复种子可见点"

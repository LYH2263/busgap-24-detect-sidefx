"""种子行数锚点：场景基准的唯一来源。

任何场景脚本/测试都不得在自己的代码里写死 ``lines=1``、``arrivals=16``
之类的魔术数；需要基准时，调用本模块的 :func:`capture_seed_anchor` 取得
各表种子 id 集合与行数，场景结束再按它裁回。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Arrival, BunchReport, Line, Trip


def _ids(db: Session, model: type) -> frozenset[int]:
    return frozenset(db.scalars(select(model.id)).all())


@dataclass(frozen=True)
class SeedAnchor:
    """种子状态下各表的 id 集合与行数。"""

    line_ids: frozenset[int]
    trip_ids: frozenset[int]
    arrival_ids: frozenset[int]
    report_ids: frozenset[int]

    @property
    def line_count(self) -> int:
        return len(self.line_ids)

    @property
    def trip_count(self) -> int:
        return len(self.trip_ids)

    @property
    def arrival_count(self) -> int:
        return len(self.arrival_ids)

    @property
    def report_count(self) -> int:
        return len(self.report_ids)

    def as_row_counts(self) -> dict[str, int]:
        """行数视图，供场景脚本断言“裁回种子行数”。"""
        return {
            "lines": self.line_count,
            "trips": self.trip_count,
            "arrivals": self.arrival_count,
            "bunch_reports": self.report_count,
        }


def capture_seed_anchor(db: Session) -> SeedAnchor:
    """在种子数据装载之后、场景写入之前捕获基准。

    基准来自数据库实际状态而非代码常量，因此种子数据调整时锚点自动跟随，
    场景侧永远不需要写死行数。
    """
    return SeedAnchor(
        line_ids=_ids(db, Line),
        trip_ids=_ids(db, Trip),
        arrival_ids=_ids(db, Arrival),
        report_ids=_ids(db, BunchReport),
    )

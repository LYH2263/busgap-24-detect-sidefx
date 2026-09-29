"""报告表巡检:数行数、确认最新报告含市民中心串车、场景结束裁回种子行数。

裁剪(DELETE)只允许发生在本模块内,场景脚本不得自行删除。
"""
from __future__ import annotations

import json

from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from app.models.models import BunchReport
from tests.sidefx.anchor import SeedAnchor


class ReportInspector:
    def __init__(self, session_factory: sessionmaker, stop_name: str):
        self._session_factory = session_factory
        self._stop_name = stop_name

    def count(self) -> int:
        """数行数。"""
        with self._session_factory() as db:
            return db.scalar(select(func.count()).select_from(BunchReport)) or 0

    def ids(self) -> set[int]:
        with self._session_factory() as db:
            return set(db.scalars(select(BunchReport.id)).all())

    def latest_events(self) -> list[dict]:
        with self._session_factory() as db:
            row = db.scalar(select(BunchReport).order_by(BunchReport.id.desc()).limit(1))
            assert row is not None, "报告表为空,没有可巡检的最新报告"
            return json.loads(row.summary_json)

    def civic_events_of_latest(self) -> list[dict]:
        """最新报告里市民中心的全部事件。"""
        return [e for e in self.latest_events() if e["stop_name"] == self._stop_name]

    def assert_latest_has_civic_bunching(self) -> dict:
        """确认最新报告含市民中心串车事件,并返回该事件。"""
        for event in self.civic_events_of_latest():
            if event["status"] == "bunching":
                return event
        raise AssertionError(f"最新报告缺少{self._stop_name}串车事件")

    def trim_to(self, anchor: SeedAnchor) -> None:
        """裁回种子行数:删掉锚点之外的新增报告,并校验行数归位。"""
        with self._session_factory() as db:
            db.execute(delete(BunchReport).where(BunchReport.id.notin_(anchor.report_ids)))
            db.commit()
        assert self.count() == anchor.report_count, "报告表未裁回种子行数"

"""场景裁回：全系统唯一允许执行 DELETE 的模块。

场景脚本禁止在自身代码里出现 ``DELETE`` / ``session.delete``；场景结束统一
调用 :func:`reset_to_anchor`。裁回顺序本身就是对账合同：

1. 先恢复时间轴 —— 删除锚点之外的全部到站点（“时间轴脏点”），
2. 再裁报告 —— 删除锚点之外的报告行，
3. 再清锚点外的班次、线路。

禁止只清报告留脏点，因此第 1 步先于第 2 步，且两者在同一事务内完成；
裁回后立即按锚点重新数行数，行数不符直接抛错。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.models import Arrival, BunchReport, Line, Trip
from app.services.seed_anchor import SeedAnchor


@dataclass(frozen=True)
class ResetResult:
    deleted: dict[str, int]

    def as_row_counts(self) -> dict[str, int]:
        return dict(self.deleted)


def _count(db: Session, model: type) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _delete_other_ids(db: Session, model: type, keep: frozenset[int]) -> int:
    keep_list = list(keep)
    # 锚点为空（全新库场景）时 in_([]) 恒假，会删全表 —— 仍属本模块统一管控。
    rows = db.execute(delete(model).where(~model.id.in_(keep_list)) if keep_list else delete(model))
    return int(rows.rowcount or 0)


def reset_to_anchor(db: Session, anchor: SeedAnchor) -> ResetResult:
    """把四张表裁回种子锚点。时间轴先于报告，禁止留脏点。"""
    deleted_arrivals = _delete_other_ids(db, Arrival, anchor.arrival_ids)
    deleted_reports = _delete_other_ids(db, BunchReport, anchor.report_ids)
    deleted_trips = _delete_other_ids(db, Trip, anchor.trip_ids)
    deleted_lines = _delete_other_ids(db, Line, anchor.line_ids)
    db.commit()

    actual = {
        "lines": _count(db, Line),
        "trips": _count(db, Trip),
        "arrivals": _count(db, Arrival),
        "bunch_reports": _count(db, BunchReport),
    }
    expected = anchor.as_row_counts()
    assert actual == expected, f"裁回后行数 {actual} 与种子锚点 {expected} 不一致"
    return ResetResult(
        deleted={
            "arrivals": deleted_arrivals,
            "bunch_reports": deleted_reports,
            "trips": deleted_trips,
            "lines": deleted_lines,
        }
    )

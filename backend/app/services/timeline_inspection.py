"""时间轴巡检：时间轴点必须与最新报告对账。

对账规则：取最新一份报告里指定站点的串车事件（报告与时间轴共同锚定的
业务事实），事件的前班次号 ``earlier_trip`` 与后班次号 ``later_trip``
必须都是该站点时间轴上真实存在的点。报告裁掉时，时间轴必须同步恢复到
种子可见点（见 :mod:`app.services.scenario_reset`），禁止只清报告留脏点。
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.services.report_inspection import latest_bunching_event, latest_report
from app.services.timeline_marks import TimelineView, build_timeline


@dataclass(frozen=True)
class Reconciliation:
    report_id: int
    stop_name: str
    earlier_trip: str
    later_trip: str
    timeline: TimelineView


def reconcile_stop(db: Session, line_id: int, stop_name: str = "市民中心") -> Reconciliation:
    """核对某站点最新串车事件的前后班次号与时间轴点。

    无最新报告、该站点无串车事件、或任一班次在时间轴上找不到对应点，
    都抛 :class:`AssertionError`，绝不静默通过。
    """
    report = latest_report(db, line_id=line_id)
    assert report is not None, f"线路 {line_id} 没有任何报告，无法与时间轴对账"
    event = latest_bunching_event(db, line_id=line_id, stop_name=stop_name)
    assert event is not None, f"最新报告 id={report.id} 不含站点「{stop_name}」的串车事件"
    timeline = build_timeline(db, line_id, stop_name)
    missing = [no for no in (event.earlier_trip, event.later_trip) if not timeline.has_point(no)]
    assert not missing, (
        f"时间轴对账失败：报告 id={report.id} 站点「{stop_name}」事件 "
        f"{event.earlier_trip}→{event.later_trip}，但时间轴缺点 {missing}；"
        "报告与时间轴必须同步裁回，禁止只清报告留脏点"
    )
    before = timeline.index_of(event.earlier_trip)
    after = timeline.index_of(event.later_trip)
    assert before is not None and after is not None and after == before + 1, (
        f"时间轴对账失败：{event.earlier_trip} 与 {event.later_trip} 在「{stop_name}」"
        "时间轴上不是相邻点，无法构成串车班次对"
    )
    return Reconciliation(
        report_id=report.id,
        stop_name=stop_name,
        earlier_trip=event.earlier_trip,
        later_trip=event.later_trip,
        timeline=timeline,
    )


def timeline_matches_latest_report(db: Session, line_id: int, stop_name: str = "市民中心") -> bool:
    """布尔版对账，供场景脚本直接断言。"""
    try:
        reconcile_stop(db, line_id, stop_name)
    except AssertionError:
        return False
    return True

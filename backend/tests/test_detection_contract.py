"""检测写库副作用合同 · 场景脚本。

场景纪律：
* 只调用 services 下的合同模块（detection_runs / report_inspection /
  timeline_inspection / seed_anchor / scenario_reset / scenario_fixtures /
  timeline_marks），脚本内不出现任何 DELETE；
* 基准行数全部来自 seed_anchor 现场捕获，不写死魔术数；
* 每个场景结束都显式调用 reset_to_anchor 裁回种子行数。
"""
from __future__ import annotations

import pytest

from app.services.detection_runs import LineNotFoundError, run_detection
from app.services.report_inspection import (
    assert_latest_report_shows_bunching,
    count_reports,
    latest_report,
)
from app.services.scenario_fixtures import plant_dirty_timeline_point
from app.services.scenario_reset import reset_to_anchor
from app.services.seed_anchor import capture_seed_anchor
from app.services.timeline_inspection import (
    reconcile_stop,
    timeline_matches_latest_report,
)
from app.services.timeline_marks import build_timeline

CIVIC_CENTER = "市民中心"


def seed_timeline_points(db, line_id: int) -> int:
    """种子可见的时间轴点数基准（由库内现状计算，非魔术数）。"""
    return build_timeline(db, line_id, CIVIC_CENTER).point_count


def test_b12_real_run_report_plus_one_and_timeline_reconciles(db, anchor, b12_line_id):
    """B12 真检一次：报告 +1、含市民中心串车，时间轴点位与事件前后班次对得上。"""
    reports_before = count_reports(db)
    points_before = seed_timeline_points(db, b12_line_id)

    outcome = run_detection(db, line_id=b12_line_id, dry_run=False)

    # 真检成功：必须落库，不得写成拒绝（无 id）或空跑（无事件）。
    assert outcome.persisted is True
    assert outcome.report_id is not None
    assert len(outcome.events) > 0
    assert count_reports(db) == reports_before + 1

    # 独立报告表巡检：最新事件含市民中心串车，前后班次号明确。
    event = assert_latest_report_shows_bunching(db, b12_line_id, CIVIC_CENTER)
    assert event.report_id == outcome.report_id
    assert event.earlier_trip and event.later_trip
    assert event.earlier_trip != event.later_trip

    # 独立时间轴巡检：市民中心点位对得上最新报告的前后班次号且相邻。
    reconciliation = reconcile_stop(db, b12_line_id, CIVIC_CENTER)
    assert reconciliation.earlier_trip == event.earlier_trip
    assert reconciliation.later_trip == event.later_trip
    assert timeline_matches_latest_report(db, b12_line_id, CIVIC_CENTER) is True
    # 真检只新增报告行，不新增时间轴点。
    assert build_timeline(db, b12_line_id, CIVIC_CENTER).point_count == points_before

    result = reset_to_anchor(db, anchor)
    assert result.deleted["bunch_reports"] == 1
    assert count_reports(db) == anchor.report_count


def test_two_consecutive_real_runs_report_plus_two_distinct_ids(db, anchor, b12_line_id):
    """连检两次：报告 +2，两行主键不同。"""
    reports_before = count_reports(db)

    first = run_detection(db, line_id=b12_line_id)
    second = run_detection(db, line_id=b12_line_id)

    assert first.persisted and second.persisted
    assert count_reports(db) == reports_before + 2
    assert first.report_id != second.report_id
    # 最新报告仍是第二次真检，且仍含市民中心串车。
    assert latest_report(db, b12_line_id).id == second.report_id
    assert_latest_report_shows_bunching(db, b12_line_id, CIVIC_CENTER)

    result = reset_to_anchor(db, anchor)
    assert result.deleted["bunch_reports"] == 2
    assert count_reports(db) == anchor.report_count


def test_invalid_line_id_zero_increment_in_report_and_timeline(db, anchor, b12_line_id, missing_line_id):
    """非法线路编号：报告与时间轴都零增量。"""
    reports_before = count_reports(db)
    points_before = seed_timeline_points(db, b12_line_id)

    with pytest.raises(LineNotFoundError):
        run_detection(db, line_id=missing_line_id, dry_run=False)

    assert count_reports(db) == reports_before
    # 既有线路时间轴点一个不多；非法线路本身也不可能有点。
    assert build_timeline(db, b12_line_id, CIVIC_CENTER).point_count == points_before
    assert build_timeline(db, missing_line_id, CIVIC_CENTER).point_count == 0

    reset_to_anchor(db, anchor)


def test_success_then_invalid_line_keeps_success_row_and_points(db, anchor, b12_line_id, missing_line_id):
    """先成功再非法编号：成功行与对应时间轴点仍在。"""
    success = run_detection(db, line_id=b12_line_id)
    success_id = success.report_id

    with pytest.raises(LineNotFoundError):
        run_detection(db, line_id=missing_line_id)

    report = latest_report(db, b12_line_id)
    assert report is not None and report.id == success_id
    # 成功行对应的市民中心事件与时间轴点依然可对账。
    reconciliation = reconcile_stop(db, b12_line_id, CIVIC_CENTER)
    timeline = build_timeline(db, b12_line_id, CIVIC_CENTER)
    assert timeline.has_point(reconciliation.earlier_trip)
    assert timeline.has_point(reconciliation.later_trip)

    reset_to_anchor(db, anchor)


def test_dry_run_changes_neither_report_rows_nor_timeline_points(db, anchor, b12_line_id):
    """试算：报告行数与时间轴点数相对试算前都不变。"""
    reports_before = count_reports(db)
    points_before = seed_timeline_points(db, b12_line_id)

    outcome = run_detection(db, line_id=b12_line_id, dry_run=True)

    assert outcome.persisted is False
    assert outcome.report_id is None
    assert len(outcome.events) > 0  # 试算也算得出事件，只是不落库
    assert count_reports(db) == reports_before
    assert build_timeline(db, b12_line_id, CIVIC_CENTER).point_count == points_before

    # 试算后再真检，仍恰好 +1，证明试算没留下任何待写状态。
    real = run_detection(db, line_id=b12_line_id, dry_run=False)
    assert real.persisted is True
    assert count_reports(db) == reports_before + 1

    reset_to_anchor(db, anchor)


def test_reset_trims_reports_and_dirty_timeline_points_together(db, b12_line_id):
    """裁报告时必须同步把时间轴恢复到种子可见点，禁止只清报告留脏点。"""
    anchor = capture_seed_anchor(db)  # 锚点在任何场景写入之前捕获
    seed_points = build_timeline(db, b12_line_id, CIVIC_CENTER)

    # 场景写入：一次真检（锚点外报告）+ 一颗市民中心脏点（锚点外 trip/arrival）。
    run_detection(db, line_id=b12_line_id)
    dirty_trip_no = plant_dirty_timeline_point(db, b12_line_id, CIVIC_CENTER)

    polluted = build_timeline(db, b12_line_id, CIVIC_CENTER)
    assert polluted.point_count == seed_points.point_count + 1
    assert polluted.has_point(dirty_trip_no)

    result = reset_to_anchor(db, anchor)

    # 报告与时间轴脏点同事务一起裁掉。
    assert result.deleted["bunch_reports"] == 1
    assert result.deleted["arrivals"] >= 1
    restored = build_timeline(db, b12_line_id, CIVIC_CENTER)
    assert restored.point_count == seed_points.point_count
    assert not restored.has_point(dirty_trip_no)
    assert [m.trip_no for m in restored.marks] == [m.trip_no for m in seed_points.marks]
    assert count_reports(db) == anchor.report_count


def test_reconcile_fails_without_report(db, anchor, b12_line_id):
    """无报告时时间轴巡检必须判失败，而不是编造对账成功。"""
    assert count_reports(db) == anchor.report_count
    assert timeline_matches_latest_report(db, b12_line_id, CIVIC_CENTER) is False
    with pytest.raises(AssertionError):
        reconcile_stop(db, b12_line_id, CIVIC_CENTER)
    reset_to_anchor(db, anchor)


def test_reconcile_fails_when_latest_report_lacks_civic_event(db, anchor, b12_line_id):
    """最新报告只检了别的站点：市民中心点仍在，但报告无该站事件，对账必须失败。"""
    run_detection(db, line_id=b12_line_id, stop_name="火车站", dry_run=False)
    # 时间轴上的市民中心点客观存在。
    assert build_timeline(db, b12_line_id, CIVIC_CENTER).point_count > 0
    # 但最新报告不含市民中心事件 —— 报告与时间轴对不上，巡检判失败。
    assert timeline_matches_latest_report(db, b12_line_id, CIVIC_CENTER) is False
    with pytest.raises(AssertionError):
        reconcile_stop(db, b12_line_id, CIVIC_CENTER)
    reset_to_anchor(db, anchor)

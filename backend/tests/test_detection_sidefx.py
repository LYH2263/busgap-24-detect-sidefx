"""检测写库副作用合同 · 场景脚本。

合同条款 → 场景映射:
  1. B12 真检一次:报告 +1 且含市民中心串车,时间轴市民中心与事件对得上
     → test_real_detection_once
  2. 连检两次:报告 +2 且主键不同
     → test_real_detection_twice
  3. 非法线路编号:报告与时间轴都零增量
     → test_illegal_line_zero_delta
  4. 先成功再非法编号:成功行与对应时间轴点仍在
     → test_success_then_illegal_keeps_row_and_points
  5. 试算:报告行数与时间轴点数相对试算前都不变
     → test_dry_run_zero_delta
  6. 真检成功不得写成拒绝或空跑
     → test_real_detection_committed_not_rejected_or_noop

脚本只调种子行数锚点 / 报告表巡检 / 时间轴巡检三个模块与 HTTP 接口;
禁止在脚本内执行任何 DELETE——裁剪与恢复由巡检模块在场景结束对账时完成。
"""
import pytest

UNKNOWN_LINE_ID = 10**9  # 非法线路编号:不可能存在的线路主键


@pytest.fixture(autouse=True)
def reconcile_to_seed(anchor, report_inspector, timeline_inspector):
    """场景结束对账:报告裁回种子行数,时间轴同步恢复种子可见点。

    禁止只清报告留脏点——两个巡检必须在同一步里一起归位。
    """
    yield
    report_inspector.trim_to(anchor)
    timeline_inspector.restore_to(anchor)


def _run_detection(client, line_id: int):
    return client.post("/api/reports/run", params={"line_id": line_id})


def test_real_detection_once(sidefx_env, anchor, report_inspector, timeline_inspector):
    """B12 真检一次:报告 +1 且含市民中心串车,时间轴市民中心与事件对得上。"""
    resp = _run_detection(sidefx_env.client, anchor.line_id)
    assert resp.status_code == 200, "真检不得被拒绝"
    report_id = resp.json()["id"]

    assert report_inspector.count() == anchor.report_count + 1
    assert report_inspector.ids() == anchor.report_ids | {report_id}
    report_inspector.assert_latest_has_civic_bunching()
    timeline_inspector.assert_covers(report_inspector.civic_events_of_latest())
    assert timeline_inspector.points() == list(anchor.timeline_points), \
        "真检只写报告表,时间轴不得有增量"


def test_real_detection_twice(sidefx_env, anchor, report_inspector):
    """连检两次:报告 +2 且两次主键不同。"""
    first_id = _run_detection(sidefx_env.client, anchor.line_id).json()["id"]
    second_id = _run_detection(sidefx_env.client, anchor.line_id).json()["id"]

    assert first_id != second_id, "两次真检的主键必须不同"
    assert report_inspector.count() == anchor.report_count + 2
    assert report_inspector.ids() == anchor.report_ids | {first_id, second_id}


def test_illegal_line_zero_delta(sidefx_env, anchor, report_inspector, timeline_inspector):
    """非法线路编号:报告与时间轴都零增量。"""
    resp = _run_detection(sidefx_env.client, UNKNOWN_LINE_ID)
    assert resp.status_code == 404

    assert report_inspector.count() == anchor.report_count
    assert timeline_inspector.points() == list(anchor.timeline_points)


def test_success_then_illegal_keeps_row_and_points(sidefx_env, anchor,
                                                   report_inspector, timeline_inspector):
    """先成功再非法编号:成功行与对应时间轴点仍在。"""
    report_id = _run_detection(sidefx_env.client, anchor.line_id).json()["id"]
    civic_events = report_inspector.civic_events_of_latest()

    resp = _run_detection(sidefx_env.client, UNKNOWN_LINE_ID)
    assert resp.status_code == 404

    assert report_id in report_inspector.ids(), "成功行不得被非法请求冲掉"
    assert report_inspector.count() == anchor.report_count + 1
    timeline_inspector.assert_covers(civic_events)
    assert timeline_inspector.points() == list(anchor.timeline_points)


def test_dry_run_zero_delta(sidefx_env, anchor, report_inspector, timeline_inspector):
    """试算(建议接口):报告行数与时间轴点数相对试算前都不变。"""
    resp = sidefx_env.client.get("/api/reports/suggestions", params={"line_id": anchor.line_id})
    assert resp.status_code == 200
    assert resp.json()["suggestions"], "试算应真实给出建议,不得空跑"

    assert report_inspector.count() == anchor.report_count, "试算不得写报告表"
    assert timeline_inspector.points() == list(anchor.timeline_points), "试算不得动时间轴"


def test_real_detection_committed_not_rejected_or_noop(sidefx_env, anchor, report_inspector):
    """真检成功不得写成拒绝或空跑:接口 200、事件非空、报告行真实落库可见。"""
    resp = _run_detection(sidefx_env.client, anchor.line_id)
    assert resp.status_code == 200, "真检被拒绝"
    body = resp.json()
    assert body["events"], "真检空跑:没有产生任何事件"

    assert report_inspector.count() == anchor.report_count + 1, "真检未落库"
    listed = sidefx_env.client.get("/api/reports").json()
    assert any(r["id"] == body["id"] for r in listed), "真检报告在列表中不可见"

"""检测写库副作用合同 · 三个独立巡检模块。

- 种子行数锚点(SeedAnchor):场景基准的唯一来源,禁止场景写死魔术数。
- 报告表巡检(ReportInspector):数行数、验最新报告含市民中心串车、裁回种子行数。
- 时间轴巡检(TimelineInspector):市民中心点位对账报告前后班次号、恢复种子可见点。

裁剪与恢复所需的 DELETE 只允许发生在两个巡检模块内部;
场景脚本(test_detection_sidefx.py)只调本包模块与 HTTP 接口。
"""
from tests.sidefx.anchor import SeedAnchor, TimelinePoint
from tests.sidefx.report_inspector import ReportInspector
from tests.sidefx.timeline_inspector import TimelineInspector

__all__ = ["SeedAnchor", "TimelinePoint", "ReportInspector", "TimelineInspector"]

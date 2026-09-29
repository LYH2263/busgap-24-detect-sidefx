"""场景写入支持：场景脚本只允许调用模块，不直接操作 ORM。

检测写库走 :mod:`app.services.detection_runs`；需要制造“时间轴脏点”来
验证裁回合同时，走本模块。删除在任何地方都不允许，只有
:mod:`app.services.scenario_reset` 能执行 DELETE。
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Arrival, Trip


def plant_dirty_timeline_point(
    db: Session,
    line_id: int,
    stop_name: str = "市民中心",
    trip_no: str = "DIRTY99",
) -> str:
    """在指定站点插一颗种子锚点之外的时间轴脏点。

    落点时间取该站最晚到站之后 1 分钟，保证排在种子班次末尾、不改变种子
    班次之间的相邻关系；同时产生锚点外的 trip 与 arrival，供裁回验证。
    """
    latest_at = db.scalar(
        select(func.max(Arrival.actual_arrive))
        .select_from(Arrival)
        .join(Trip, Trip.id == Arrival.trip_id)
        .where(Trip.line_id == line_id, Arrival.stop_name == stop_name)
    )
    arrive = latest_at + timedelta(minutes=1)
    trip = Trip(line_id=line_id, trip_no=trip_no, planned_depart=arrive, vehicle_no="场景脏点车")
    db.add(trip)
    db.flush()
    db.add(Arrival(trip_id=trip.id, stop_name=stop_name, stop_seq=1, actual_arrive=arrive))
    db.commit()
    return trip_no

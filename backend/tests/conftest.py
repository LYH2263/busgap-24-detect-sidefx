"""检测写库副作用合同 · 测试基座。

每个场景一份全新的内存 SQLite + 种子数据;接口依赖改指内存库,
不触发应用 lifespan,不连 Postgres。
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.seed import seed_if_empty
from tests.sidefx import ReportInspector, SeedAnchor, TimelineInspector

LINE_CODE = "B12"
STOP_NAME = "市民中心"


@pytest.fixture()
def sidefx_env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    session_factory = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with session_factory() as db:
        seed_if_empty(db)

    def _override_get_db():
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield SimpleNamespace(client=TestClient(app), session_factory=session_factory)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture()
def anchor(sidefx_env) -> SeedAnchor:
    """种子行数锚点:场景基准的唯一来源。"""
    with sidefx_env.session_factory() as db:
        return SeedAnchor.capture(db, sidefx_env.client, LINE_CODE, STOP_NAME)


@pytest.fixture()
def report_inspector(sidefx_env, anchor) -> ReportInspector:
    """报告表巡检。"""
    return ReportInspector(sidefx_env.session_factory, anchor.stop_name)


@pytest.fixture()
def timeline_inspector(sidefx_env, anchor) -> TimelineInspector:
    """时间轴巡检。"""
    return TimelineInspector(sidefx_env.client, sidefx_env.session_factory,
                             anchor.line_id, anchor.stop_name)

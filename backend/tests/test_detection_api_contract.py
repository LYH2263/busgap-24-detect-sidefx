"""HTTP 层副作用合同：真检/试算/非法编号/建议在 API 上的表现。

与服务层场景共用同一套合同语义，只是从 FastAPI 入口验证状态码与字段。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Line
from app.services.report_inspection import count_reports
from app.services.seed import seed_if_empty


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    seed_if_empty(session)

    def _get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    # 不进入 with：跳过 lifespan，避免触碰模块级 Postgres 引擎。
    yield TestClient(app), session
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def line_id(client) -> int:
    _, session = client
    value = session.scalar(select(Line.id).where(Line.code == "B12"))
    assert value is not None
    return int(value)


def test_run_real_persists(client, line_id):
    http, session = client
    before = count_reports(session)
    res = http.post(f"/api/reports/run?line_id={line_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["persisted"] is True and body["dry_run"] is False
    assert isinstance(body["id"], int)
    assert any(e["stop_name"] == "市民中心" and e["status"] == "bunching" for e in body["events"])
    assert count_reports(session) == before + 1


def test_run_invalid_line_404_zero_increment(client):
    http, session = client
    before = count_reports(session)
    missing = int(session.scalar(select(func.max(Line.id))) or 0) + 1000
    res = http.post(f"/api/reports/run?line_id={missing}")
    assert res.status_code == 404
    assert count_reports(session) == before


def test_run_dry_run_zero_increment(client, line_id):
    http, session = client
    before = count_reports(session)
    res = http.post(f"/api/reports/run?line_id={line_id}&dry_run=true")
    assert res.status_code == 200
    body = res.json()
    assert body["persisted"] is False and body["id"] is None
    assert len(body["events"]) > 0
    assert count_reports(session) == before


def test_suggestions_are_read_only(client, line_id):
    http, session = client
    before = count_reports(session)
    res = http.get(f"/api/reports/suggestions?line_id={line_id}")
    assert res.status_code == 200
    assert len(res.json()["suggestions"]) > 0
    # 建议是只读试算视图：不得顺手写报告。
    assert count_reports(session) == before


def test_timeline_endpoint_marks_civic_pair(client, line_id):
    http, _ = client
    res = http.get(f"/api/reports/timeline?line_id={line_id}&stop_name=市民中心")
    assert res.status_code == 200
    marks = res.json()["marks"]
    assert [m["trip_no"] for m in marks] == ["T01", "T02", "T03", "T04"]

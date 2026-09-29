"""场景公共基座：sqlite 内存种子库 + 种子行数锚点。

每个场景拿到全新种子库，基准一律经 ``capture_seed_anchor`` 现场捕获，
场景代码里不允许出现种子行数魔术数。
"""
from __future__ import annotations

import os

# 必须在导入 app.database 之前：场景测试走 sqlite，不依赖 Postgres 驱动/实例。
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.models import Line
from app.services.seed import seed_if_empty
from app.services.seed_anchor import SeedAnchor, capture_seed_anchor


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    seed_if_empty(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def anchor(db: Session) -> SeedAnchor:
    return capture_seed_anchor(db)


@pytest.fixture
def b12_line_id(db: Session) -> int:
    line_id = db.scalar(select(Line.id).where(Line.code == "B12"))
    assert line_id is not None, "种子数据缺少 B12 线路"
    return int(line_id)


@pytest.fixture
def missing_line_id(db: Session) -> int:
    """确定不存在的非法线路编号（由库内现状推导，不写死常量）。"""
    top = db.scalar(select(func.max(Line.id))) or 0
    return int(top) + 1000

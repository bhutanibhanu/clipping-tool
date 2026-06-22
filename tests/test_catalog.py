from __future__ import annotations

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session

from clipper.catalog import create_creator, get_creator, list_creators
from clipper.db.models import Creator
from clipper.db.session import init_db


@pytest.fixture
def engine() -> Engine:
    eng = create_engine("sqlite:///:memory:")
    init_db(eng)
    return eng


def test_create_creator_persists_one_row_with_id(engine: Engine) -> None:
    with Session(engine) as session:
        creator = create_creator(session, name="Authorized Owner")
        session.commit()

        assert creator.id is not None
        assert session.scalar(select(func.count()).select_from(Creator)) == 1
        assert get_creator(session, creator.id) is creator


def test_list_creators_returns_all_oldest_first(engine: Engine) -> None:
    with Session(engine) as session:
        first = create_creator(session, name="First")
        second = create_creator(session, name="Second")
        session.commit()

        assert [c.id for c in list_creators(session)] == [first.id, second.id]


def test_get_creator_returns_none_for_unknown_id(engine: Engine) -> None:
    with Session(engine) as session:
        assert get_creator(session, 999) is None

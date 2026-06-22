from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from clipper.db.models import Clip, ClipStatus, Creator, PermissionRecord, Source
from clipper.db.session import init_db


def test_schema_creates_and_roundtrips() -> None:
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)

    with Session(engine) as s:
        creator = Creator(name="Test Creator")
        perm = PermissionRecord(creator=creator, scope="youtube")
        source = Source(creator=creator, permission=perm, file_path="/tmp/video.mp4")
        clip = Clip(
            source=source,
            start_seconds=0.0,
            end_seconds=30.0,
            title="A hook",
            hashtags=["#a", "#b"],
        )
        s.add_all([creator, perm, source, clip])
        s.commit()

        got = s.scalars(select(Clip)).one()
        assert got.status is ClipStatus.pending
        assert got.hashtags == ["#a", "#b"]
        assert got.source.permission.scope == "youtube"
        assert got.source.creator.name == "Test Creator"

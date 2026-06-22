"""Data model (SQLAlchemy 2.0 typed ORM).

Five entities: Creator -> PermissionRecord -> Source -> (Job, Clip). The
permission link is load-bearing — a Source must reference a valid
PermissionRecord before it can be processed (the enforced account-safety
gate; enforcement logic lands with the pipeline, the schema is here).
"""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Base(DeclarativeBase):
    pass


class PermissionStatus(enum.StrEnum):
    active = "active"
    revoked = "revoked"


class JobStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    error = "error"


class ClipStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class Creator(Base):
    __tablename__ = "creators"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    handles: Mapped[str | None] = mapped_column(Text, default=None)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    permissions: Mapped[list[PermissionRecord]] = relationship(
        back_populates="creator", cascade="all, delete-orphan"
    )
    sources: Mapped[list[Source]] = relationship(back_populates="creator")


class PermissionRecord(Base):
    """Proof of consent for one creator: a DB row plus an uploaded authorization file."""

    __tablename__ = "permission_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"))
    scope: Mapped[str | None] = mapped_column(Text, default=None)
    authorization_file_path: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[PermissionStatus] = mapped_column(
        Enum(PermissionStatus), default=PermissionStatus.active
    )
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    creator: Mapped[Creator] = relationship(back_populates="permissions")
    sources: Mapped[list[Source]] = relationship(back_populates="permission")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("creators.id"))
    permission_id: Mapped[int] = mapped_column(ForeignKey("permission_records.id"))
    file_path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(128), default=None)
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    width: Mapped[int | None] = mapped_column(Integer, default=None)
    height: Mapped[int | None] = mapped_column(Integer, default=None)
    transcript_path: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    creator: Mapped[Creator] = relationship(back_populates="sources")
    permission: Mapped[PermissionRecord] = relationship(back_populates="sources")
    jobs: Mapped[list[Job]] = relationship(back_populates="source", cascade="all, delete-orphan")
    clips: Mapped[list[Clip]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    kind: Mapped[str] = mapped_column(String(50), default="process")
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued)
    stage: Mapped[str | None] = mapped_column(String(50), default=None)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    source: Mapped[Source] = relationship(back_populates="jobs")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    status: Mapped[ClipStatus] = mapped_column(Enum(ClipStatus), default=ClipStatus.pending)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    title: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    hashtags: Mapped[list[str]] = mapped_column(JSON, default=list)
    transcript_excerpt: Mapped[str | None] = mapped_column(Text, default=None)
    output_path: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_utcnow)

    source: Mapped[Source] = relationship(back_populates="clips")

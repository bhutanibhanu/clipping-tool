"""Publisher seam (reserved, not implemented in v1).

v1 explicitly does NOT post to any platform — this protocol exists only so
future YouTube Shorts / TikTok / Reels / X publishers have a stable contract
to implement. The only v1 "publisher" is local export (see clipper.export).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    detail: str = ""


@runtime_checkable
class Publisher(Protocol):
    def publish(self, clip_output_path: str) -> PublishResult: ...

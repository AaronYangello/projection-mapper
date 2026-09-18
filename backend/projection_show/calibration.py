"""Leased, transient calibration. Persisting geometry never rebuilds the running show."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from .config.models import Mapping, Model, Project


class Preview(Model):
    sequence: int
    mapping: Mapping
    pattern: Literal["show", "grid", "white", "border"] = "grid"
    black_others: bool = True


@dataclass
class Session:
    surface_id: str
    base_revision: int
    saved: Mapping
    mapping: Mapping
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    sequence: int = -1
    pattern: str = "grid"
    black_others: bool = True
    expires: float = field(default_factory=lambda: time.monotonic() + 45)

    @property
    def dirty(self) -> bool:
        return self.saved != self.mapping

    def response(self) -> dict:
        return {
            "id": self.id,
            "surface_id": self.surface_id,
            "revision": self.base_revision,
            "sequence": self.sequence,
            "mapping": self.mapping.model_dump(mode="json"),
            "dirty": self.dirty,
        }


class Calibration:
    def __init__(self):
        self.session: Session | None = None
        self.generation = 0

    def expire(self) -> bool:
        if self.session and time.monotonic() > self.session.expires:
            self.session = None
            self.generation += 1
            return True
        return False

    def begin(self, project: Project, revision: int, surface_id: str) -> dict:
        self.expire()
        if self.session:
            raise ValueError(
                "A calibration session is already active. Finish it or wait 45 seconds."
            )
        surface = next((s for s in project.surfaces if s.id == surface_id), None)
        if not surface or not surface.enabled:
            raise ValueError("Select an enabled surface")
        if not any(p.id == surface.projector_id and p.enabled for p in project.projectors):
            raise ValueError("Enable the surface's projector before calibrating")
        self.session = Session(
            surface.id,
            revision,
            surface.mapping.model_copy(deep=True),
            surface.mapping.model_copy(deep=True),
        )
        self.generation += 1
        return self.session.response()

    def owned(self, session_id: str) -> Session:
        self.expire()
        if not self.session or self.session.id != session_id:
            raise ValueError("Calibration session expired or belongs to another client")
        self.session.expires = time.monotonic() + 45
        return self.session

    def preview(self, session_id: str, update: Preview) -> dict:
        session = self.owned(session_id)
        if update.sequence <= session.sequence:
            raise ValueError("Out-of-order mapping update rejected")
        session.mapping = update.mapping
        session.sequence = update.sequence
        session.pattern = update.pattern
        session.black_others = update.black_others
        self.generation += 1
        return session.response()

    def project_to_save(self, project: Project, revision: int, session_id: str) -> Project:
        session = self.owned(session_id)
        if revision != session.base_revision:
            raise ValueError("Project changed; start a new calibration session")
        data = project.model_dump()
        for surface in data["surfaces"]:
            if surface["id"] == session.surface_id:
                surface["mapping"] = session.mapping.model_dump()
        return Project.model_validate(data)

    def saved(self, revision: int) -> dict:
        session = self.session
        session.saved = session.mapping.model_copy(deep=True)
        session.base_revision = revision
        return session.response()

    def end(self, session_id: str) -> None:
        self.owned(session_id)
        self.session = None
        self.generation += 1

    def render_state(self) -> dict | None:
        s = self.session
        return (
            None
            if s is None
            else {
                "surface_id": s.surface_id,
                "mapping": s.mapping.model_dump(mode="json"),
                "pattern": s.pattern,
                "black_others": s.black_others,
            }
        )

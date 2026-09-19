"""Validated YAML with atomic replacement and a last-good backup."""

import os
import tempfile
from pathlib import Path

import yaml

from .migrations import migrate  # noqa: F401 - public migration entry point
from .models import Project


def atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class ProjectStore:
    def __init__(self, path: Path):
        self.path = path.resolve()

    def load(self) -> Project:
        return Project.model_validate(migrate(yaml.safe_load(self.path.read_text())))

    def save(self, project: Project) -> None:
        validated = Project.model_validate(project.model_dump())
        if self.path.exists():
            # Only retain a validated last-good file; never overwrite backup with corrupt input.
            self.load()
            atomic_write(self.path.with_suffix(".yaml.bak"), self.path.read_text())
        atomic_write(self.path, yaml.safe_dump(validated.model_dump(mode="json"), sort_keys=False))

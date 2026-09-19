from unittest.mock import patch

import pytest
from projection_show.config.models import Mapping, Project
from projection_show.config.store import migrate
from pydantic import ValidationError


def test_demo_is_data_not_topology(demo):
    assert demo.canvas.width == 3840
    assert demo.canvas.preview_fps == 1
    assert demo.canvas.preview_width == 480
    assert len(demo.surfaces) == 7
    data = demo.model_dump()
    data["canvas"] = {"width": 1200, "height": 600}
    data["projectors"] = [
        {
            "id": "custom",
            "name": "Long output",
            "viewport": {"x": 100, "y": 50, "width": 1000, "height": 500},
        }
    ]
    data["surfaces"] = [{**data["surfaces"][0], "projector_id": "custom"}]
    data["surfaces"][0]["logical"] = {"width": 640, "height": 360}
    project = Project.model_validate(data)
    assert len(project.projectors) == len(project.surfaces) == 1


@pytest.mark.parametrize(
    "key,value",
    [
        ("projector_id", "missing"),
        ("ambient_profile", "missing"),
        ("logical", {"width": 0, "height": 1080}),
        ("mapping", {"top_left": [-0.1, 0]}),
    ],
)
def test_surface_validation(demo, key, value):
    data = demo.model_dump()
    data["surfaces"][0][key] = value
    with pytest.raises(ValidationError):
        Project.model_validate(data)


@pytest.mark.parametrize(
    "points",
    [
        [(0, 0), (1, 1), (1, 0), (0, 1)],  # crossed
        [(0, 0), (0, 0), (1, 1), (0, 1)],  # collapsed
        [(0, 0), (1, 0), (0.2, 0.2), (0, 1)],  # concave
        [(0, 0), (0, 1), (1, 1), (1, 0)],  # reversed
    ],
)
def test_invalid_quads(points):
    with pytest.raises(ValidationError):
        Mapping(
            **dict(
                zip(["top_left", "top_right", "bottom_right", "bottom_left"], points, strict=True)
            )
        )


@pytest.mark.parametrize("collection", ["projectors", "surfaces", "scenes", "ambient_profiles"])
def test_duplicate_ids(demo, collection):
    data = demo.model_dump()
    data[collection].append(data[collection][0])
    with pytest.raises(ValidationError, match="Duplicate"):
        Project.model_validate(data)


def test_outside_canvas_and_unknown_fields(demo):
    data = demo.model_dump()
    data["canvas"]["width"] = 1000
    with pytest.raises(ValidationError, match="outside"):
        Project.model_validate(data)
    with pytest.raises(ValidationError):
        Project.model_validate({**demo.model_dump(), "misspelled_setting": True})


@pytest.mark.parametrize(
    "timing", [{"min": 8, "max": 2}, {"min": 0, "max": 0}, {"min": float("nan"), "max": 4}]
)
def test_invalid_timing(demo, timing):
    data = demo.model_dump()
    data["show"]["hold_seconds"] = timing
    with pytest.raises(ValidationError):
        Project.model_validate(data)


def test_atomic_round_trip_and_backup(store, demo):
    demo.name = "Renamed installation"
    store.save(demo)
    assert store.load() == demo
    assert store.path.with_suffix(".yaml.bak").exists()
    before = store.path.read_text()
    with patch("projection_show.config.store.os.replace", side_effect=OSError("disk failed")):
        with pytest.raises(OSError):
            store.save(demo)
    assert store.path.read_text() == before
    assert list(store.path.parent.glob("*.tmp")) == []


def test_unknown_schema_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        migrate({"schema_version": 99})

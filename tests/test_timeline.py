import copy

import pytest
from projection_show.config.models import Project
from projection_show.config.store import migrate
from projection_show.config.timeline import Opacity
from projection_show.runtime import RenderBridge, Runtime
from projection_show.timeline import TimelineController, evaluate, opacity_at
from pydantic import ValidationError


@pytest.fixture
def timeline(demo):
    data = demo.model_dump(mode="json")
    data["show"].update(
        mode="timeline",
        auto_start=False,
        timeline={
            "duration_seconds": 10,
            "tracks": [
                {
                    "id": "t1",
                    "surface_id": demo.surfaces[0].id,
                    "clips": [
                        {
                            "id": "c1",
                            "scene_id": demo.scenes[0].id,
                            "start_seconds": 1,
                            "duration_seconds": 3,
                        },
                        {
                            "id": "c2",
                            "scene_id": demo.scenes[1].id,
                            "start_seconds": 4,
                            "duration_seconds": 3,
                        },
                    ],
                    "opacity": {
                        "default": 0,
                        "keyframes": [
                            {"time_seconds": 1, "value": 0},
                            {"time_seconds": 3, "value": 1},
                            {"time_seconds": 8, "value": 0},
                        ],
                    },
                }
            ],
        },
    )
    return Project.model_validate(data)


def test_v1_migrates_without_mutation_or_loss(demo):
    old = demo.model_dump(mode="json")
    old["schema_version"] = 1
    del old["show"]["timeline"]
    for s in old["surfaces"]:
        for key in ["role", "shape", "light"]:
            del s[key]
    before = copy.deepcopy(old)
    p = Project.model_validate(old)
    assert old == before
    assert p.schema_version == 2 and p == Project.model_validate(p.model_dump())
    for key in old["show"]:
        assert p.show.model_dump()[key] == old["show"][key]
    assert p.surfaces[0].mapping == demo.surfaces[0].mapping
    assert migrate(old)["schema_version"] == 2


@pytest.mark.parametrize("version", [0, 3, True, None, "1"])
def test_unknown_versions(version):
    with pytest.raises(ValueError):
        migrate({"schema_version": version})


@pytest.mark.parametrize(
    "time,value", [(0, 0.2), (1, 0), (2, 0.5), (3, 1), (4, 1), (5, 0.4), (100, 0.4)]
)
def test_opacity_interpolation(time, value):
    a = Opacity(
        default=0.2,
        keyframes=[
            {"time_seconds": 1, "value": 0},
            {"time_seconds": 3, "value": 1, "interpolation": "hold"},
            {"time_seconds": 5, "value": 0.4},
        ],
    )
    assert opacity_at(a, time) == pytest.approx(value)
    assert opacity_at(Opacity(), time) == 1


def test_clip_half_open_and_opacity_across_boundary(timeline):
    assert evaluate(timeline, 0)[0].source_id is None
    assert evaluate(timeline, 1)[0].clip_id == "c1"
    assert evaluate(timeline, 4)[0].clip_id == "c2"
    assert evaluate(timeline, 4)[0].opacity == pytest.approx(0.8)
    assert evaluate(timeline, 7)[0].source_id is None
    assert evaluate(timeline, 7)[0].opacity == pytest.approx(0.2)


@pytest.mark.parametrize(
    "change",
    ["overlap", "duplicate", "missing", "disabled", "audio", "duration", "order", "nan", "keys"],
)
def test_invalid_timeline(timeline, change):
    d = timeline.model_dump()
    t = d["show"]["timeline"]
    track = t["tracks"][0]
    if change == "overlap":
        track["clips"][1]["start_seconds"] = 2
    if change == "duplicate":
        track["clips"][1]["id"] = "c1"
    if change == "missing":
        track["surface_id"] = "missing"
    if change == "disabled":
        d["surfaces"][0]["enabled"] = False
    if change == "audio":
        t["audio"] = {"scene_id": d["scenes"][0]["id"], "duration_seconds": 2}
    if change == "duration":
        track["clips"][1]["duration_seconds"] = 9
    if change == "order":
        t["track_order"] = ["missing"]
    if change == "nan":
        t["duration_seconds"] = float("nan")
    if change == "keys":
        track["opacity"]["keyframes"].reverse()
    with pytest.raises(ValidationError):
        Project.model_validate(d)


def test_other_tracks_simultaneous_and_lights(timeline):
    d = timeline.model_dump()
    d["surfaces"][1].update(role="lighting", shape="circle", light={"color": "#ffaa11"})
    t = d["show"]["timeline"]
    t["tracks"].append(
        {"id": "light", "surface_id": d["surfaces"][1]["id"], "opacity": t["tracks"][0]["opacity"]}
    )
    p = Project.model_validate(d)
    layers = evaluate(p, 2)
    assert layers[0].opacity == layers[1].opacity == 0.5
    assert layers[1].color == "#ffaa11" and layers[1].shape == "circle"
    t["tracks"][1]["clips"] = t["tracks"][0]["clips"][:1]
    with pytest.raises(ValidationError):
        Project.model_validate(d)


def test_seek_loop_end(timeline):
    c = TimelineController(timeline)
    c.seek(9)
    c.tick(2)
    assert c.position == 10 and c.ended
    timeline.show.timeline.loop = True
    c.seek(9)
    c.tick(22)
    assert c.position == 1 and c.cycle == 3
    with pytest.raises(ValueError):
        c.seek(float("nan"))


def test_runtime_pause_blackout_seek_and_restart(store, timeline, monkeypatch):
    store.save(timeline)
    now = [10.0]
    monkeypatch.setattr("projection_show.runtime.time.monotonic", lambda: now[0])
    r = Runtime(store, RenderBridge())
    r.command("start")
    now[0] += 2
    r.tick(now[0])
    assert r.controller.position == 2
    r.command("pause")
    now[0] += 20
    r.tick(now[0])
    assert r.controller.position == 2
    r.seek(5)
    r.command("resume")
    r.command("blackout")
    now[0] += 10
    r.tick(now[0])
    assert r.controller.position == 5
    r.command("restore")
    now[0] += 1
    r.tick(now[0])
    assert r.controller.position == 6
    r.command("stop")
    assert r.controller.position == 0 and r.state == "READY"
    assert r.project.show.fade_in_seconds == timeline.show.fade_in_seconds

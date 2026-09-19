import wave
from pathlib import Path

import av
import numpy as np
import pytest
from projection_show.config.models import Project
from projection_show.config.store import ProjectStore


@pytest.fixture
def demo():
    return ProjectStore(Path(__file__).parents[1] / "projects/demo/project.yaml").load()


@pytest.fixture
def store(tmp_path, demo):
    store = ProjectStore(tmp_path / "project.yaml")
    store.save(demo)
    return store


@pytest.fixture
def movie(tmp_path):
    media = tmp_path / "media"
    media.mkdir()
    path = media / "fixture.mp4"
    with av.open(str(path), mode="w") as output:
        stream = output.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 32, "yuv420p"
        for index in range(20):
            pixels = np.zeros((32, 64, 3), dtype=np.uint8)
            pixels[:] = (230, 20, 20) if index < 10 else (20, 20, 230)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    return tmp_path, path


@pytest.fixture
def compiled_project(tmp_path, demo):
    data = demo.model_dump(mode="json")
    data["canvas"].update(width=1920, height=1080, refresh_rate=30)
    data["projectors"] = data["projectors"][:1]
    data["projectors"][0]["viewport"] = dict(x=0, y=0, width=1920, height=1080)
    data["surfaces"] = data["surfaces"][:4]
    for s in data["surfaces"]:
        s.update(projector_id=data["projectors"][0]["id"], logical={"width": 64, "height": 32})
    media = tmp_path / "media"
    media.mkdir(exist_ok=True)
    data["scenes"] = []
    tracks = []
    for i, color in enumerate([(240, 10, 10), (10, 230, 10), (10, 10, 240), (230, 230, 10)]):
        path = media / f"{i}.mp4"
        with av.open(str(path), "w") as out:
            stream = out.add_stream("mpeg4", rate=30)
            stream.width = 64
            stream.height = 32
            stream.pix_fmt = "yuv420p"
            pixels = np.zeros((32, 64, 3), dtype=np.uint8)
            pixels[:] = color
            for _ in range(60):
                for packet in stream.encode(av.VideoFrame.from_ndarray(pixels, format="rgb24")):
                    out.mux(packet)
            for packet in stream.encode():
                out.mux(packet)
        data["scenes"].append(
            dict(id=f"v{i}", name=f"Video {i}", type="video", path=f"media/{i}.mp4")
        )
        tracks.append(
            dict(
                id=f"t{i}",
                surface_id=data["surfaces"][i]["id"],
                clips=[dict(id=f"c{i}", scene_id=f"v{i}", start_seconds=0.5, duration_seconds=1.5)],
            )
        )
    with wave.open(str(media / "tone.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(
            (np.sin(np.arange(48000) * 2 * np.pi * 440 / 48000) * 12000).astype("<i2").tobytes()
        )
    data["scenes"].append(dict(id="audio", name="Master", type="audio", path="media/tone.wav"))
    data["show"].update(
        mode="timeline",
        auto_start=False,
        timeline={
            "duration_seconds": 2,
            "tracks": tracks,
            "audio": {"scene_id": "audio", "duration_seconds": 1, "start_seconds": 0.5},
        },
    )
    return Project.model_validate(data), tmp_path

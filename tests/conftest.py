from pathlib import Path

import av
import numpy as np
import pytest
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

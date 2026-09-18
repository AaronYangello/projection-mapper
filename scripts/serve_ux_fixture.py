"""Disposable API-only fixture for browser regression tests; never edits a user project."""

import tempfile
from pathlib import Path

import av
import numpy as np
import uvicorn
from PIL import Image
from projection_show.api import create_app
from projection_show.config.models import Project
from projection_show.config.store import ProjectStore
from projection_show.runtime import RenderBridge, Runtime

repo = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="projection-ux-") as directory:
    root = Path(directory)
    media = root / "media"
    media.mkdir()
    for name, color in (("sample", "#337799"), ("other", "#779944")):
        Image.new("RGB", (320, 200), color).save(media / f"{name}.png")
    with av.open(str(media / "clip.mp4"), mode="w") as output:
        stream = output.add_stream("mpeg4", rate=10)
        stream.width, stream.height, stream.pix_fmt = 64, 32, "yuv420p"
        for _ in range(20):
            frame = av.VideoFrame.from_ndarray(np.full((32, 64, 3), 100, dtype=np.uint8), "rgb24")
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    (media / "broken.mp4").write_bytes(b"Intentional invalid media fixture")
    data = ProjectStore(repo / "projects/demo/project.yaml").load().model_dump()
    data["scenes"] = [s for s in data["scenes"] if s["type"] == "color"] + [
        {"id": "sample", "name": "Sample image", "type": "image", "path": "media/sample.png"},
        {"id": "clip", "name": "Sample video", "type": "video", "path": "media/clip.mp4"},
    ]
    data["show"]["auto_start"] = False
    store = ProjectStore(root / "project.yaml")
    store.save(Project.model_validate(data))
    uvicorn.run(
        create_app(Runtime(store, RenderBridge()), repo / "frontend/dist"),
        host="127.0.0.1",
        port=8012,
        access_log=False,
    )

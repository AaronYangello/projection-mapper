"""Generate a disposable four-stem / sixteen-light / stereo-tone authoring project.

Never replaces an existing project. All generated media are synthetic.
"""

import argparse
import wave
from pathlib import Path

import av
import numpy as np
from projection_show.config.models import Project
from projection_show.config.store import ProjectStore


def create(root: Path, seconds=12):
    if root.exists():
        raise ValueError("Choose a new empty output path; fixture creation never overwrites")
    media = root / "media"
    media.mkdir(parents=True)
    surfaces, scenes, tracks = [], [], []
    colors = [(220, 45, 45), (30, 175, 105), (35, 95, 220), (220, 165, 35)]
    for i, color in enumerate(colors):
        sid = f"video-{i + 1}"
        with av.open(str(media / f"{sid}.mp4"), "w") as output:
            stream = output.add_stream("mpeg4", rate=30)
            stream.width, stream.height, stream.pix_fmt = 640, 360, "yuv420p"
            for index in range(seconds * 30):
                pixels = np.zeros((360, 640, 3), dtype=np.uint8)
                pixels[:] = color
                x = (index * 4) % 600
                pixels[:, x : x + 40] = (235, 235, 235)
                for packet in stream.encode(av.VideoFrame.from_ndarray(pixels, format="rgb24")):
                    output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)
        scenes.append(dict(id=sid, name=f"Stem {i + 1}", type="video", path=f"media/{sid}.mp4"))
        x, y = (i % 2) / 2, (i // 2) / 2
        surfaces.append(
            dict(
                id=sid,
                name=f"Video {i + 1}",
                projector_id="projector",
                logical=dict(width=960, height=540),
                mapping=quad(x, y, 0.5, 0.5),
            )
        )
        tracks.append(
            dict(
                id=f"track-{sid}",
                surface_id=sid,
                clips=[dict(id=f"clip-{sid}", scene_id=sid, duration_seconds=seconds)],
                opacity=dict(
                    default=0,
                    keyframes=[
                        dict(time_seconds=0, value=0),
                        dict(time_seconds=1, value=1),
                        dict(time_seconds=seconds - 1, value=1),
                        dict(time_seconds=seconds, value=0),
                    ],
                ),
            )
        )
    for i in range(16):
        sid = f"light-{i + 1}"
        surfaces.append(
            dict(
                id=sid,
                name=f"Light {i + 1}",
                projector_id="projector",
                role="lighting",
                shape="circle" if i % 2 else "rectangle",
                light=dict(color="#ffdda0"),
                logical=dict(width=100, height=100),
                mapping=quad(0.03 + (i % 8) * 0.12, 0.39 + (i // 8) * 0.5, 0.05, 0.088889),
            )
        )
        start = i % 4 + 1
        tracks.append(
            dict(
                id=f"track-{sid}",
                surface_id=sid,
                opacity=dict(
                    default=0,
                    keyframes=[
                        dict(time_seconds=start, value=0),
                        dict(time_seconds=start + 1, value=1),
                        dict(time_seconds=start + 3, value=0.3),
                        dict(time_seconds=seconds, value=0),
                    ],
                ),
            )
        )
    with wave.open(str(media / "master.wav"), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        t = np.arange(seconds * 48000) / 48000
        tone = (np.sin(t * 2 * np.pi * 440) * 4000 * ((t % 3) < 0.25)).astype("<i2")
        output.writeframes(np.column_stack((tone, tone)).tobytes())
    scenes.append(
        dict(id="audio", name="Synthetic timing tone", type="audio", path="media/master.wav")
    )
    p = Project.model_validate(
        dict(
            schema_version=2,
            id="timeline-fixture",
            name="Timeline commissioning fixture",
            canvas=dict(width=1920, height=1080, refresh_rate=30, fullscreen=False),
            projectors=[
                dict(
                    id="projector",
                    name="Projector output",
                    viewport=dict(x=0, y=0, width=1920, height=1080),
                )
            ],
            surfaces=surfaces,
            scenes=scenes,
            show=dict(
                mode="timeline",
                auto_start=False,
                timeline=dict(
                    duration_seconds=seconds,
                    loop=True,
                    tracks=tracks,
                    track_order=[s["id"] for s in surfaces],
                    audio=dict(scene_id="audio", duration_seconds=seconds),
                ),
            ),
        )
    )
    ProjectStore(root / "project.yaml").save(p)
    return root / "project.yaml"


def quad(x, y, w, h):
    return dict(
        top_left=[x, y], top_right=[x + w, y], bottom_right=[x + w, y + h], bottom_left=[x, y + h]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(create(args.output))

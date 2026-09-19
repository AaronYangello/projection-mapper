"""GL texture consumer for the native decoder; called only from the render thread."""

from pathlib import Path

import moderngl

from ..media.decoder import Decoder, fit_transform
from .shaders import QUAD_VERTEX

SOURCE_FRAGMENT = """
#version 330
in vec2 uv;
uniform sampler2D image;
uniform vec2 uv_scale;
uniform vec2 uv_offset;
uniform float opacity;
out vec4 frag;
void main() {
    vec2 p = uv * uv_scale + uv_offset;
    if (min(p.x,p.y) < 0.0 || max(p.x,p.y) > 1.0) {
        frag = vec4(0,0,0,opacity);
    } else {
        // FFmpeg rows are top-down, matching the logical surface's UV origin.
        frag = vec4(texture(image, p).rgb, opacity);
    }
}
"""


class MediaPlayback:
    def __init__(self, context, vertices):
        self.ctx = context
        self.program = context.program(vertex_shader=QUAD_VERTEX, fragment_shader=SOURCE_FRAGMENT)
        self.quad = context.vertex_array(self.program, [(vertices, "2f", "position")])
        self.decoder: Decoder | None = None
        self.retired: list[Decoder] = []
        self.texture = None
        self.key = None
        self.serial = -1
        self.scene = None
        self.max_texture_size = context.info["GL_MAX_TEXTURE_SIZE"]
        self.health = {"state": "IDLE", "backend": "FFmpeg / PyAV", "error": None}

    def clear(self):
        if self.decoder:
            self.decoder.close(wait=False)
            self.retired.append(self.decoder)
            self.decoder = None
        if self.texture:
            self.texture.release()
            self.texture = None
        self.retired = [d for d in self.retired if d.thread.is_alive()]
        self.serial, self.key = -1, None

    def update(self, frame: dict):
        cue = frame["scheduler"]["current"]
        scene = next(
            (s for s in frame["project"]["scenes"] if cue and s["id"] == cue["scene_id"]), None
        )
        if (
            not scene
            or scene.get("type", "color") == "color"
            or frame["transport"] == "READY"
            or frame["scheduler"].get("phase") == "GAP"
        ):
            self.clear()
            self.health = {"state": "IDLE", "backend": "FFmpeg / PyAV", "error": None}
            return
        key = (frame.get("playback_generation", 0), cue["id"], scene["id"])
        if key != self.key:
            self.clear()
            if len(self.retired) >= 2:
                self.health = {
                    "state": "ERROR",
                    "error": "Previous decoders did not stop promptly",
                    "cue_id": cue["id"],
                    "generation": key[0],
                }
                return
            self.decoder = Decoder(Path(frame["project_root"]), scene)
            self.key, self.scene = key, scene
        seconds = frame["scheduler"]["elapsed"]
        if scene["type"] == "video":
            duration = frame["media_durations"].get(scene["id"], 0)
            if duration <= 0:
                self.health = {
                    "state": "ERROR",
                    "error": "Video duration is unavailable",
                    "cue_id": cue["id"],
                    "generation": key[0],
                }
                return
            if scene["playback"] == "timed" and scene["end_behavior"] == "loop":
                seconds %= duration
            else:
                seconds = min(seconds, max(0, duration - 0.001))
            seconds += scene["start_seconds"]
        self.decoder.request(seconds)
        decoded, health = self.decoder.snapshot()
        self.health = {
            **health,
            "scene_id": scene["id"],
            "cue_id": cue["id"],
            "generation": key[0],
            "requested_seconds": seconds,
        }
        if decoded and decoded.serial != self.serial:
            try:
                if max(decoded.size) > self.max_texture_size:
                    raise ValueError(
                        f"Source exceeds GPU texture dimension limit ({self.max_texture_size}px)"
                    )
                if self.texture is None or self.texture.size != decoded.size:
                    if self.texture:
                        self.texture.release()
                        self.texture = None
                    self.texture = self.ctx.texture(decoded.size, 3)
                    self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
                    self.texture.repeat_x = self.texture.repeat_y = False
                self.texture.write(decoded.rgb, alignment=1)
                self.serial = decoded.serial
            except (ValueError, moderngl.Error) as exc:
                if self.texture:
                    self.texture.release()
                    self.texture = None
                self.health.update(state="ERROR", error=str(exc)[:300])

    def draw(self, size: tuple[int, int], opacity: float):
        if not self.texture:
            return
        scale, offset = fit_transform(
            self.texture.size, size, self.scene["fit"], self.scene["focal_point"]
        )
        self.texture.use(0)
        self.program["image"].value = 0
        self.program["uv_scale"].value = scale
        self.program["uv_offset"].value = offset
        self.program["opacity"].value = opacity
        self.quad.render(moderngl.TRIANGLE_STRIP)

    def close(self, *, wait=True):
        self.clear()
        for decoder in self.retired:
            decoder.close(wait=wait)
        self.quad.release()
        self.program.release()

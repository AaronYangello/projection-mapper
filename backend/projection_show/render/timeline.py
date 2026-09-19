"""Timeline composition shares homography and targets with shuffle; lights draw directly."""

from pathlib import Path

import moderngl

from ..mapping import color_rgb
from ..media.gstreamer import GstPlayback
from .media import MediaPlayback
from .shaders import WARP_VERTEX

FRAGMENT = """
#version 330
in vec2 uv;
uniform sampler2D image;
uniform vec4 region;
uniform bool use_image;
uniform bool flip_y;
uniform bool circle;
uniform vec2 logical;
uniform vec3 color;
uniform float opacity;
out vec4 frag;
void main() {
    if (circle && length((uv-vec2(.5))*logical)>min(logical.x,logical.y)*.5) discard;
    vec2 p=region.xy+uv*region.zw;
    if(flip_y) p.y=1.-p.y;
    vec3 rgb=use_image?texture(image,p).rgb:color;
    frag=vec4(rgb,opacity);
}
"""


class TimelineRenderer:
    def __init__(self, ctx, vertices):
        self.ctx = ctx
        self.vertices = vertices
        self.program = ctx.program(vertex_shader=WARP_VERTEX, fragment_shader=FRAGMENT)
        self.quad = ctx.vertex_array(self.program, [(vertices, "2f", "position")])
        self.sources = {}
        self.pipeline = None
        self.deployment_id = None
        self.pipeline_options = None
        self.texture = None
        self.serial = -1
        self.health = {"state": "IDLE", "backend": "native source preview"}
        self.fault_key = None

    def close_sources(self):
        for player in self.sources.values():
            player.close(wait=False)
        self.sources.clear()

    def update(self, frame):
        if frame.get("deployment"):
            d = frame["deployment"]
            ident = d["manifest"]["id"]
            generation = frame["playback_generation"]
            options = frame.get("playback_options", {})
            self.close_sources()
            if self.deployment_id != ident or self.pipeline_options != options:
                if self.pipeline:
                    self.pipeline.close()
                self.pipeline = None
                self.deployment_id = ident
                self.pipeline_options = options.copy()
                self.fault_key = None
                self.serial = -1
                if self.texture:
                    self.texture.release()
                    self.texture = None
            if self.fault_key == (ident, generation):
                return
            try:
                if (
                    self.pipeline
                    and self.health.get("state") == "ERROR"
                    and self.health.get("generation") != generation
                ):
                    self.pipeline.close()
                    self.pipeline = None
                if not self.pipeline:
                    self.pipeline = GstPlayback(
                        Path(d["directory"]) / "playback.mp4",
                        duration=frame["timeline"]["duration"],
                        **options,
                    )
                decoded, self.health = self.pipeline.update(
                    seconds=frame["timeline"]["position"],
                    generation=generation,
                    playing=frame["transport"] == "RUNNING" and not frame["blackout"],
                    loop=frame["timeline"]["loop"],
                    audio={
                        **(d["automation"]["timeline"]["audio"] or {}),
                        **frame.get("audio_overrides", {}),
                    },
                )
                if decoded and decoded.serial != self.serial:
                    if not self.texture:
                        self.texture = self.ctx.texture(decoded.size, 3)
                        self.texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
                        self.texture.repeat_x = self.texture.repeat_y = False
                    self.texture.write(decoded.rgb, alignment=1)
                    self.serial = decoded.serial
            except Exception as e:
                self.health = {
                    "state": "ERROR",
                    "backend": "GStreamer",
                    "error": str(e)[:300],
                    "generation": generation,
                }
                self.fault_key = (ident, generation)
            return
        if self.pipeline:
            self.pipeline.close()
            self.pipeline = None
            self.deployment_id = None
        active = {
            layer["id"]: layer
            for layer in frame["layers"]
            if layer["source_id"] and frame["transport"] != "READY"
        }
        for key in set(self.sources) - set(active):
            self.sources.pop(key).close(wait=False)
        scenes = {s["id"]: s for s in frame["project"]["scenes"]}
        health = []
        for key, layer in active.items():
            scene = scenes[layer["source_id"]]
            if scene["type"] == "color":
                continue
            if key not in self.sources:
                self.sources[key] = MediaPlayback(self.ctx, self.vertices)
            # Source timestamp is absolute in timeline mode; shuffle trims stay in shuffle.
            scene = {
                **scene,
                "start_seconds": 0,
                "end_seconds": None,
                "playback": "full_clip",
                "end_behavior": "hold",
            }
            proxy = {
                **frame,
                "project": {"scenes": [scene]},
                "scheduler": {
                    "current": {"id": layer["clip_id"], "scene_id": layer["source_id"]},
                    "elapsed": layer["source_seconds"],
                    "phase": "FOREGROUND",
                },
                "media_durations": frame.get("source_durations", {}),
            }
            self.sources[key].update(proxy)
            health.append(self.sources[key].health)
        failed = next((h for h in health if h["state"] == "ERROR"), None)
        self.health = {
            "state": "ERROR" if failed else "READY",
            "backend": "PyAV source preview (silent)",
            "streams": health,
            "error": failed.get("error") if failed else None,
            "generation": frame["playback_generation"],
        }

    def draw(self, frame, engine):
        self.update(frame)
        if frame["blackout"]:
            return
        project = frame["project"]
        projectors = {p["id"]: p for p in project["projectors"] if p["enabled"]}
        layers = {layer["surface_id"]: layer for layer in frame["layers"]}
        scenes = {s["id"]: s for s in project["scenes"]}
        self.ctx.enable(moderngl.BLEND)
        self.ctx.blend_func = (
            moderngl.SRC_ALPHA,
            moderngl.ONE_MINUS_SRC_ALPHA,
            moderngl.ONE,
            moderngl.ONE_MINUS_SRC_ALPHA,
        )
        for surface in project["surfaces"]:
            sid = surface["id"]
            layer = layers.get(sid)
            cal = frame.get("calibration")
            pattern = frame["pattern"]
            if not surface["enabled"] or surface["projector_id"] not in projectors:
                continue
            if cal and cal["black_others"] and cal["surface_id"] != sid:
                continue
            if cal and cal["surface_id"] == sid:
                pattern = cal["pattern"]
            texture = None
            region = (0, 0, 1, 1)
            flip = False
            color = "#000000"
            opacity = 0
            shape = surface.get("shape", "rectangle")
            if pattern != "show":
                target = engine.targets[sid]
                target.framebuffer.use()
                self.ctx.disable(moderngl.BLEND)
                p = engine.programs["pattern"]
                p["pattern"].value = {"grid": 1, "white": 2, "color": 3, "border": 4}[pattern]
                p["color"].value = (0.3, 0.6, 0.9)
                p["resolution"].value = tuple(surface["logical"][k] for k in ("width", "height"))
                engine.quads["pattern"].render(moderngl.TRIANGLE_STRIP)
                if cal and cal["surface_id"] == sid and pattern == "grid":
                    engine.draw_label(surface, projectors[surface["projector_id"]])
                texture = target.texture
                flip = True
                opacity = 1
                shape = "rectangle"
            elif layer and frame["transport"] != "READY":
                opacity = layer["opacity"]
                color = layer.get("color") or "#000000"
                if layer["role"] == "media":
                    if not layer["source_id"]:
                        continue
                    if frame.get("deployment"):
                        r = next(
                            (
                                r
                                for r in frame["deployment"]["atlas"]["regions"]
                                if r["clip_id"] == layer["clip_id"]
                            ),
                            None,
                        )
                        if not r or not self.texture:
                            continue
                        texture = self.texture
                        region = r["uv"]
                    elif scenes[layer["source_id"]]["type"] == "color":
                        color = scenes[layer["source_id"]]["color"]
                    else:
                        player = self.sources.get(layer["id"])
                        if not player or not player.texture:
                            continue
                        target = engine.targets[sid]
                        target.framebuffer.use()
                        target.framebuffer.clear(0, 0, 0, 1)
                        self.ctx.disable(moderngl.BLEND)
                        player.draw(tuple(surface["logical"][k] for k in ("width", "height")), 1)
                        texture = target.texture
                        flip = True
            if opacity <= 0:
                continue
            engine.master.framebuffer.use()
            self.ctx.enable(moderngl.BLEND)
            viewport = projectors[surface["projector_id"]]["viewport"]
            self.ctx.scissor = (
                viewport["x"],
                project["canvas"]["height"] - viewport["y"] - viewport["height"],
                viewport["width"],
                viewport["height"],
            )
            p = self.program
            p["transform"].write(engine.transforms[sid].T.astype("f4").tobytes())
            p["viewport"].value = tuple(viewport[k] for k in ("x", "y", "width", "height"))
            p["canvas"].value = (project["canvas"]["width"], project["canvas"]["height"])
            p["region"].value = region
            p["use_image"].value = texture is not None
            p["flip_y"].value = flip
            p["circle"].value = shape == "circle"
            p["logical"].value = tuple(surface["logical"][k] for k in ("width", "height"))
            p["color"].value = color_rgb(color)
            p["opacity"].value = opacity
            if texture:
                texture.use(0)
            p["image"].value = 0
            self.quad.render(moderngl.TRIANGLE_STRIP)
        self.ctx.scissor = None
        self.ctx.disable(moderngl.BLEND)

    def close(self):
        self.close_sources()
        if self.pipeline:
            self.pipeline.close()
        if self.texture:
            self.texture.release()
        self.quad.release()
        self.program.release()

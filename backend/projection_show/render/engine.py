"""One logical FBO per surface, projective warp into one master output FBO."""

import io
import time
import zlib
from dataclasses import dataclass

import glfw
import moderngl
import numpy as np
from PIL import Image

from ..mapping import color_rgb, homography
from ..runtime import RenderBridge
from . import shaders
from .context import create_context, graphics_report
from .labels import calibration_label
from .media import MediaPlayback
from .timeline import TimelineRenderer


@dataclass
class Target:
    texture: object
    framebuffer: object

    def release(self):
        self.framebuffer.release()
        self.texture.release()


class Engine:
    def __init__(self, ctx):
        self.ctx = ctx
        self.revision = -1
        self.geometry_revision = -1
        self.targets: dict[str, Target] = {}
        self.particles: dict[str, tuple] = {}
        self.transforms: dict[str, np.ndarray] = {}
        self.master: Target | None = None
        self.thumbnail: Target | None = None
        self.label_texture = None
        self.label_key = None
        self.programs = {
            "fill": ctx.program(
                vertex_shader=shaders.QUAD_VERTEX, fragment_shader=shaders.FILL_FRAGMENT
            ),
            "pattern": ctx.program(
                vertex_shader=shaders.QUAD_VERTEX, fragment_shader=shaders.PATTERN_FRAGMENT
            ),
            "warp": ctx.program(
                vertex_shader=shaders.WARP_VERTEX, fragment_shader=shaders.TEXTURE_FRAGMENT
            ),
            "blit": ctx.program(
                vertex_shader=shaders.QUAD_VERTEX, fragment_shader=shaders.TEXTURE_FRAGMENT
            ),
            "particles": ctx.program(
                vertex_shader=shaders.PARTICLE_VERTEX, fragment_shader=shaders.PARTICLE_FRAGMENT
            ),
        }
        self.vertices = ctx.buffer(np.array([0, 0, 1, 0, 0, 1, 1, 1], dtype="f4"))
        self.quads = {
            name: ctx.vertex_array(p, [(self.vertices, "2f", "position")])
            for name, p in self.programs.items()
            if name != "particles"
        }
        self.playback = MediaPlayback(ctx, self.vertices)
        self.timeline = TimelineRenderer(ctx, self.vertices)

    def target(self, width: int, height: int) -> Target:
        limit = self.ctx.info["GL_MAX_TEXTURE_SIZE"]
        if width > limit or height > limit:
            raise ValueError(f"Render target {width}×{height} exceeds GPU limit {limit}")
        texture = self.ctx.texture((width, height), 4)
        texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        texture.repeat_x = texture.repeat_y = False
        return Target(texture, self.ctx.framebuffer(color_attachments=[texture]))

    def configure(self, project: dict, revision: int):
        self.release_targets()
        canvas = project["canvas"]
        self.master = self.target(canvas["width"], canvas["height"])
        thumb_w = min(960, canvas["width"])
        self.thumbnail = self.target(
            thumb_w, max(1, round(thumb_w * canvas["height"] / canvas["width"]))
        )
        profiles = {a["id"]: a for a in project["ambient_profiles"]}
        for surface in project["surfaces"]:
            if not surface["enabled"]:
                continue
            sid = surface["id"]
            self.targets[sid] = (
                self.target(64, 64)
                if surface.get("role") == "lighting"
                else self.target(**surface["logical"])
            )
            mapping = surface["mapping"]
            self.transforms[sid] = homography(
                [mapping[k] for k in ("top_left", "top_right", "bottom_right", "bottom_left")]
            )
            profile = (
                profiles.get(surface["ambient_profile"])
                if surface.get("role") != "lighting"
                else None
            )
            if profile and profile["type"] == "particles" and profile["count"]:
                rng = np.random.default_rng((profile["seed"] + zlib.crc32(sid.encode())) % 2**32)
                data = rng.random((profile["count"], 4)).astype("f4")
                data[:, 2:] = data[:, 2:] * 0.75 + 0.5
                buffer = self.ctx.buffer(data)
                vao = self.ctx.vertex_array(
                    self.programs["particles"], [(buffer, "4f", "particle")]
                )
                self.particles[sid] = (buffer, vao)
        self.revision = revision

    def render(self, frame: dict):
        project = frame["project"]
        if self.revision != frame["revision"]:
            self.configure(project, frame["revision"])
            self.geometry_revision = -1
        calibration = frame.get("calibration")
        geometry_revision = frame.get("geometry_revision", 0)
        if self.geometry_revision != geometry_revision:
            for surface in project["surfaces"]:
                mapping = (
                    calibration["mapping"]
                    if calibration and calibration["surface_id"] == surface["id"]
                    else surface["mapping"]
                )
                self.transforms[surface["id"]] = homography(
                    [mapping[k] for k in ("top_left", "top_right", "bottom_right", "bottom_left")]
                )
            self.geometry_revision = geometry_revision
        ctx = self.ctx
        self.master.framebuffer.use()
        ctx.scissor = None
        ctx.disable(moderngl.BLEND)
        self.master.framebuffer.clear(0, 0, 0, 1)
        if frame.get("timeline"):
            self.playback.clear()
            self.timeline.draw(frame, self)
            return
        if self.timeline.pipeline:
            self.timeline.pipeline.close()
            self.timeline.pipeline = None
        self.timeline.close_sources()
        if frame["blackout"]:
            return
        self.playback.update(frame)
        projectors = {p["id"]: p for p in project["projectors"] if p["enabled"]}
        profiles = {p["id"]: p for p in project["ambient_profiles"] if p["enabled"]}
        scenes = {s["id"]: s for s in project["scenes"]}
        cue = frame["scheduler"]["current"]
        opacity = frame["scheduler"]["opacity"] if frame["transport"] != "READY" else 0
        for index, surface in enumerate(project["surfaces"]):
            if not surface["enabled"] or surface["projector_id"] not in projectors:
                continue
            sid = surface["id"]
            if calibration and calibration["black_others"] and calibration["surface_id"] != sid:
                continue
            if (
                surface.get("role") == "lighting"
                and frame["pattern"] == "show"
                and not (
                    calibration
                    and calibration["surface_id"] == sid
                    and calibration["pattern"] != "show"
                )
            ):
                continue  # Lighting brightness is exclusively timeline surface automation.
            target = self.targets[sid]
            target.framebuffer.use()
            ctx.scissor = None
            target.framebuffer.clear(0, 0, 0, 1)
            active = opacity if cue and cue["surface_id"] == sid else 0
            ctx.enable(moderngl.BLEND | moderngl.PROGRAM_POINT_SIZE)
            ctx.blend_func = (
                moderngl.SRC_ALPHA,
                moderngl.ONE_MINUS_SRC_ALPHA,
                moderngl.ONE,
                moderngl.ONE_MINUS_SRC_ALPHA,
            )
            ambient = profiles.get(surface["ambient_profile"])
            if ambient:
                dim = 1 - active * (1 - ambient["foreground_opacity"])
                if ambient["type"] == "solid":
                    self.fill(ambient["color"], ambient["opacity"] * dim)
                elif ambient["type"] == "particles" and sid in self.particles:
                    p = self.programs["particles"]
                    for key in ("speed", "drift", "size"):
                        p[key].value = ambient[key]
                    p["elapsed"].value = frame["ambient_time"]
                    p["color"].value = color_rgb(ambient["color"])
                    p["opacity"].value = ambient["opacity"] * dim
                    self.particles[sid][1].render(moderngl.POINTS)
            if active and cue:
                scene = scenes[cue["scene_id"]]
                if scene.get("type", "color") == "color":
                    self.fill(scene["color"], active)
                else:
                    self.playback.draw(
                        (surface["logical"]["width"], surface["logical"]["height"]), active
                    )
            ctx.disable(moderngl.BLEND)
            pattern = frame["pattern"]
            if calibration and calibration["surface_id"] == sid:
                pattern = calibration["pattern"]
            if pattern != "show":
                p = self.programs["pattern"]
                p["pattern"].value = {"grid": 1, "white": 2, "color": 3, "border": 4}[pattern]
                palette = [(0.25, 0.65, 0.85), (0.75, 0.5, 0.3), (0.45, 0.7, 0.5)]
                p["color"].value = palette[index % len(palette)]
                p["resolution"].value = (surface["logical"]["width"], surface["logical"]["height"])
                self.quads["pattern"].render(moderngl.TRIANGLE_STRIP)
                if calibration and calibration["surface_id"] == sid and pattern == "grid":
                    self.draw_label(surface, projectors[surface["projector_id"]])
            self.master.framebuffer.use()
            viewport = projectors[surface["projector_id"]]["viewport"]
            ctx.scissor = (
                viewport["x"],
                project["canvas"]["height"] - viewport["y"] - viewport["height"],
                viewport["width"],
                viewport["height"],
            )
            p = self.programs["warp"]
            p["transform"].write(self.transforms[sid].T.astype("f4").tobytes())
            p["viewport"].value = tuple(viewport[k] for k in ("x", "y", "width", "height"))
            p["canvas"].value = (project["canvas"]["width"], project["canvas"]["height"])
            target.texture.use(0)
            p["image"].value = 0
            self.quads["warp"].render(moderngl.TRIANGLE_STRIP)
        ctx.scissor = None

    def fill(self, color: str, opacity: float):
        self.programs["fill"]["color"].value = color_rgb(color)
        self.programs["fill"]["opacity"].value = opacity
        self.quads["fill"].render(moderngl.TRIANGLE_STRIP)

    def draw_label(self, surface: dict, projector: dict):
        size = (surface["logical"]["width"], surface["logical"]["height"])
        key = (surface["id"], surface["name"], projector.get("name", projector["id"]), size)
        if key != self.label_key:
            if self.label_texture:
                self.label_texture.release()
            image = calibration_label(surface, {**projector, "name": key[2]})
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            self.label_texture = self.ctx.texture(size, 4, image.tobytes())
            self.label_key = key
        self.ctx.enable(moderngl.BLEND)
        self.label_texture.use(0)
        self.programs["blit"]["image"].value = 0
        self.quads["blit"].render(moderngl.TRIANGLE_STRIP)
        self.ctx.disable(moderngl.BLEND)

    def blit(self, framebuffer, size: tuple[int, int]):
        framebuffer.use()
        self.ctx.scissor = None
        framebuffer.clear(0, 0, 0, 1)
        width, height = size
        ratio = min(width / self.master.texture.width, height / self.master.texture.height)
        w, h = round(self.master.texture.width * ratio), round(self.master.texture.height * ratio)
        self.ctx.viewport = ((width - w) // 2, (height - h) // 2, w, h)
        self.master.texture.use(0)
        self.programs["blit"]["image"].value = 0
        self.quads["blit"].render(moderngl.TRIANGLE_STRIP)

    def image(self) -> Image.Image:
        return Image.frombytes(
            "RGB", self.master.framebuffer.size, self.master.framebuffer.read(components=3)
        ).transpose(Image.Transpose.FLIP_TOP_BOTTOM)

    def jpeg(self) -> bytes:
        self.blit(self.thumbnail.framebuffer, self.thumbnail.framebuffer.size)
        image = Image.frombytes(
            "RGB", self.thumbnail.framebuffer.size, self.thumbnail.framebuffer.read(components=3)
        )
        stream = io.BytesIO()
        image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(stream, "JPEG", quality=80)
        return stream.getvalue()

    def release_targets(self):
        if self.label_texture:
            self.label_texture.release()
            self.label_texture = self.label_key = None
        for target in [*self.targets.values(), self.master, self.thumbnail]:
            if target:
                target.release()
        for buffer, vao in self.particles.values():
            vao.release()
            buffer.release()
        self.targets.clear()
        self.particles.clear()
        self.transforms.clear()
        self.master = self.thumbnail = None

    def close(self):
        self.playback.close()
        self.timeline.close()
        self.release_targets()
        for vao in self.quads.values():
            vao.release()
        self.vertices.release()
        for program in self.programs.values():
            program.release()


def run_renderer(
    bridge: RenderBridge,
    stop,
    *,
    visible=True,
    fullscreen=False,
    monitor=0,
    duration: float | None = None,
    graphics_backend="desktop",
):
    window, ctx = create_context(
        visible=visible, fullscreen=fullscreen, monitor=monitor, backend=graphics_backend
    )
    engine = Engine(ctx)
    start = sample = time.monotonic()
    next_frame = start
    last_preview = 0
    frames = late = 0
    reported_geometry = -1
    try:
        while not stop.is_set() and not glfw.window_should_close(window):
            began = time.monotonic()
            if duration is not None and began - start >= duration:
                break
            if glfw.get_key(window, glfw.KEY_ESCAPE) == glfw.PRESS:
                break
            glfw.poll_events()
            frame = bridge.read()
            if frame:
                engine.render(frame)
                if frame.get("timeline"):
                    bridge.report(timeline_clock=dict(engine.timeline.health))
                if reported_geometry != engine.geometry_revision:
                    bridge.report(geometry_revision=engine.geometry_revision)
                    reported_geometry = engine.geometry_revision
                size = glfw.get_framebuffer_size(window)
                if size[0] and size[1]:
                    engine.blit(ctx.screen, size)
                    glfw.swap_buffers(window)
                if began - last_preview >= 0.5:
                    bridge.preview(engine.jpeg())
                    last_preview = began
                frames += 1
                target = 1 / frame["project"]["canvas"]["refresh_rate"]
                elapsed = time.monotonic() - began
                late += int(elapsed > target * 1.5)
                if began - sample >= 1:
                    canvas = frame["project"]["canvas"]
                    warning = None
                    if fullscreen and size != (canvas["width"], canvas["height"]):
                        warning = (
                            "Display differs from canvas. Output is letterboxed; "
                            "check display settings."
                        )
                    bridge.report(
                        status="LIVE",
                        fps=round(frames / (began - sample), 1),
                        late_frames=late,
                        gpu=ctx.info["GL_RENDERER"],
                        graphics=graphics_report(ctx, size, graphics_backend),
                        output_size=list(size),
                        warning=warning,
                        geometry_revision=engine.geometry_revision,
                        decoder=dict(
                            engine.timeline.health
                            if frame.get("timeline")
                            else engine.playback.health
                        ),
                    )
                    frames, sample = 0, began
                # Accumulate a deadline so timer oversleep doesn't lower the requested frame rate.
                next_frame += target
                now = time.monotonic()
                if now - next_frame > target:
                    next_frame = now
                time.sleep(max(0, next_frame - now))
            else:
                time.sleep(0.01)
    finally:
        engine.close()
        ctx.release()
        glfw.destroy_window(window)
        glfw.terminate()
        bridge.report(status="STOPPED", fps=0)

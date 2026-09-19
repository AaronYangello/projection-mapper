"""Explicit desktop GL or EGL/GLES backend selection; no unsafe version overrides."""

import os

import glfw
import moderngl


def request_visible_window_attention(window, *, visible, fullscreen):
    """Ask the desktop manager to present an operator-facing output window."""
    if not visible:
        return
    if not fullscreen:
        glfw.maximize_window(window)
    glfw.focus_window(window)


def graphics_report(ctx, size, backend):
    info = ctx.info
    renderer = info["GL_RENDERER"]
    report = {
        "backend": backend,
        "renderer": renderer,
        "vendor": info.get("GL_VENDOR"),
        "version": info.get("GL_VERSION"),
        "shader_version": info.get("GL_SHADING_LANGUAGE_VERSION"),
        "max_texture_size": info["GL_MAX_TEXTURE_SIZE"],
        "output_size": list(size),
        "software_rendering": any(
            s in renderer.lower()
            for s in ("llvmpipe", "softpipe", "swiftshader", "software rasterizer")
        ),
        "physical_pi_verified": False,
    }
    if backend == "gles":
        from OpenGL import EGL

        display = EGL.eglGetCurrentDisplay()
        value = EGL.eglQueryString(display, EGL.EGL_VERSION)
        report["egl_version"] = value.decode() if value else None
    monitor = glfw.get_window_monitor(glfw.get_current_context())
    if monitor:
        mode = glfw.get_video_mode(monitor)
        report["fullscreen_mode"] = {
            "width": mode.size.width,
            "height": mode.size.height,
            "refresh_hz": mode.refresh_rate,
        }
    else:
        report["fullscreen_mode"] = None
    return report


def create_context(
    *, width=1280, height=720, visible=True, fullscreen=False, monitor=0, backend="desktop"
):
    if backend not in ("desktop", "gles"):
        raise ValueError("Unknown graphics backend")
    if any(
        os.environ.get(k)
        for k in (
            "MESA_GL_VERSION_OVERRIDE",
            "MESA_GLES_VERSION_OVERRIDE",
            "MESA_GLSL_VERSION_OVERRIDE",
        )
    ):
        raise ValueError("Unsafe Mesa version overrides must be removed before qualification")
    if backend == "gles":
        os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
    if not glfw.init():
        raise RuntimeError("GLFW could not initialize; start a display session or use --api-only")
    glfw.default_window_hints()
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3 if backend == "desktop" else 0)
    if backend == "desktop":
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
    else:
        glfw.window_hint(glfw.CLIENT_API, glfw.OPENGL_ES_API)
        glfw.window_hint(glfw.CONTEXT_CREATION_API, glfw.EGL_CONTEXT_API)
    glfw.window_hint(glfw.VISIBLE, visible)
    if visible and not fullscreen:
        glfw.window_hint(glfw.FOCUSED, True)
        glfw.window_hint(glfw.MAXIMIZED, True)
    glfw.window_hint(glfw.COCOA_RETINA_FRAMEBUFFER, False)
    selected = None
    if fullscreen:
        monitors = glfw.get_monitors()
        if monitor >= len(monitors):
            glfw.terminate()
            raise RuntimeError("Configured monitor is not connected")
        selected = monitors[monitor]
        mode = glfw.get_video_mode(selected)
        width, height = mode.size.width, mode.size.height
    window = glfw.create_window(width, height, "Projection Show · Native Output", selected, None)
    if not window:
        glfw.terminate()
        raise RuntimeError(
            f"{backend} context creation failed; this graphics path is not qualified on this device"
        )
    try:
        glfw.make_context_current(window)
        request_visible_window_attention(window, visible=visible, fullscreen=fullscreen)
        glfw.swap_interval(1 if visible else 0)
        if fullscreen:
            glfw.set_input_mode(window, glfw.CURSOR, glfw.CURSOR_HIDDEN)
        if backend == "desktop":
            ctx = moderngl.create_context(require=330)
        else:
            from .gles import Context

            ctx = Context(glfw.get_framebuffer_size(window))
        if graphics_report(ctx, (width, height), backend)["software_rendering"]:
            raise RuntimeError(
                "Software rasterizer detected; hardware graphics qualification failed"
            )
        return window, ctx
    except Exception:
        glfw.destroy_window(window)
        glfw.terminate()
        raise

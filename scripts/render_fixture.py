"""Capture a deterministic native GPU test pattern without starting a server."""

import argparse
from pathlib import Path

import glfw
from projection_show.config.store import ProjectStore
from projection_show.render.engine import Engine, create_context
from projection_show.runtime import RenderBridge, Runtime

parser = argparse.ArgumentParser()
parser.add_argument("--project", type=Path, default=Path("projects/demo/project.yaml"))
parser.add_argument("--output", type=Path, default=Path("artifacts/native-grid.png"))
args = parser.parse_args()
runtime = Runtime(ProjectStore(args.project), RenderBridge())
runtime.set_pattern("grid")
window, context = create_context(visible=False)
engine = Engine(context)
try:
    engine.render(runtime.bridge.read())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    engine.image().save(args.output)
    print(f"Saved {args.output}: {context.info['GL_RENDERER']}")
finally:
    engine.close()
    context.release()
    glfw.destroy_window(window)
    glfw.terminate()

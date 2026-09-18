"""GLSL 330 core shaders, compatible with the desktop OpenGL path on Mesa and macOS."""

QUAD_VERTEX = """
#version 330
in vec2 position;
out vec2 uv;
void main() {
    uv = position;
    gl_Position = vec4(position.x * 2.0 - 1.0, 1.0 - position.y * 2.0, 0.0, 1.0);
}
"""

FILL_FRAGMENT = """
#version 330
uniform vec3 color;
uniform float opacity;
out vec4 frag;
void main() { frag = vec4(color, opacity); }
"""

PARTICLE_VERTEX = """
#version 330
in vec4 particle;
uniform float elapsed;
uniform float speed;
uniform float drift;
uniform float size;
void main() {
    vec2 p = fract(particle.xy + elapsed * vec2(drift, speed) * particle.z);
    gl_Position = vec4(p.x * 2.0 - 1.0, 1.0 - p.y * 2.0, 0.0, 1.0);
    gl_PointSize = size * particle.w;
}
"""

PARTICLE_FRAGMENT = """
#version 330
uniform vec3 color;
uniform float opacity;
out vec4 frag;
void main() {
    float radius = length(gl_PointCoord - vec2(0.5));
    float alpha = (1.0 - smoothstep(0.15, 0.5, radius)) * opacity;
    frag = vec4(color, alpha);
}
"""

PATTERN_FRAGMENT = """
#version 330
in vec2 uv;
uniform int pattern;
uniform vec3 color;
uniform vec2 resolution;
out vec4 frag;
void main() {
    vec2 edge = min(uv, 1.0 - uv) * resolution;
    bool border = min(edge.x, edge.y) < 5.0;
    vec2 grid = abs(fract(uv * 10.0 + 0.5) - 0.5);
    bool line = min(grid.x, grid.y) < 0.012;
    bool cross = abs(uv.x - 0.5) < 0.004 || abs(uv.y - 0.5) < 0.004;
    vec3 c = color;
    if (pattern == 1) c = (border || cross) ? vec3(1) : line ? color : color * 0.07;
    if (pattern == 2) c = vec3(1);
    if (pattern == 4) c = border ? vec3(1) : vec3(0);
    frag = vec4(c, 1.0);
}
"""

WARP_VERTEX = """
#version 330
in vec2 position;
uniform mat3 transform;
uniform vec4 viewport;
uniform vec2 canvas;
out vec2 uv;
void main() {
    vec3 p = transform * vec3(position, 1.0);
    vec2 pixel = viewport.xy * p.z + p.xy * viewport.zw;
    // Preserve projective w. Affine triangle UV interpolation causes a visible diagonal seam.
    gl_Position = vec4(2.0 * pixel.x / canvas.x - p.z,
                       p.z - 2.0 * pixel.y / canvas.y, 0.0, p.z);
    uv = position;
}
"""

TEXTURE_FRAGMENT = """
#version 330
in vec2 uv;
uniform sampler2D image;
out vec4 frag;
void main() { frag = texture(image, vec2(uv.x, 1.0 - uv.y)); }
"""

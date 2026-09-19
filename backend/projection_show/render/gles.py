"""Small GL resource adapter for GLES 3, isolated from rendering/business logic.

ModernGL is retained on desktop. This adapter uses the common GL/ES subset via PyOpenGL;
its resource contract is desktop pixel-tested, but actual Pi EGL/GLES remains unqualified.
"""

import moderngl
import numpy as np


def shader_source(source, dialect):
    return (
        source.replace(
            "#version 330", "#version 300 es\nprecision highp float;\nprecision highp int;"
        )
        if dialect == "gles"
        else source
    )


class Uniform:
    def __init__(self, program, name):
        self.p = program
        self.location = program.gl.glGetUniformLocation(program.id, name)
        if self.location < 0:
            raise KeyError(name)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        g = self.p.gl
        g.glUseProgram(self.p.id)
        values = value if isinstance(value, (tuple, list)) else [value]
        kind = self.p.types.get(self.location)
        integer = kind in (
            g.GL_INT,
            g.GL_BOOL,
            g.GL_SAMPLER_2D,
            g.GL_INT_VEC2,
            g.GL_INT_VEC3,
            g.GL_INT_VEC4,
        )
        getattr(g, f"glUniform{len(values)}" + ("i" if integer else "f"))(self.location, *values)

    def write(self, data):
        self.p.gl.glUseProgram(self.p.id)
        self.p.gl.glUniformMatrix3fv(self.location, 1, False, np.frombuffer(data, dtype="f4"))


class Program:
    def __init__(self, ctx, vertex_shader, fragment_shader):
        self.gl = ctx.gl
        g = self.gl
        self.id = g.glCreateProgram()
        shaders = []
        try:
            for kind, source in [
                (g.GL_VERTEX_SHADER, vertex_shader),
                (g.GL_FRAGMENT_SHADER, fragment_shader),
            ]:
                shader = g.glCreateShader(kind)
                shaders.append(shader)
                g.glShaderSource(shader, shader_source(source, ctx.dialect))
                g.glCompileShader(shader)
                if not g.glGetShaderiv(shader, g.GL_COMPILE_STATUS):
                    raise ValueError(
                        "Shader compile failed: " + g.glGetShaderInfoLog(shader).decode()
                    )
                g.glAttachShader(self.id, shader)
            g.glLinkProgram(self.id)
            if not g.glGetProgramiv(self.id, g.GL_LINK_STATUS):
                raise ValueError("Shader link failed: " + g.glGetProgramInfoLog(self.id).decode())
        except Exception:
            g.glDeleteProgram(self.id)
            raise
        finally:
            for shader in shaders:
                g.glDeleteShader(shader)
        self.types = {}
        for i in range(g.glGetProgramiv(self.id, g.GL_ACTIVE_UNIFORMS)):
            name, size, kind = g.glGetActiveUniform(self.id, i)
            self.types[g.glGetUniformLocation(self.id, name)] = kind

    def __getitem__(self, name):
        return Uniform(self, name)

    def release(self):
        self.gl.glDeleteProgram(self.id)


class Buffer:
    def __init__(self, ctx, data):
        self.gl = ctx.gl
        g = self.gl
        self.id = int(g.glGenBuffers(1))
        g.glBindBuffer(g.GL_ARRAY_BUFFER, self.id)
        data = data.tobytes() if hasattr(data, "tobytes") else data
        self.size = len(data)
        g.glBufferData(g.GL_ARRAY_BUFFER, len(data), data, g.GL_STATIC_DRAW)

    def release(self):
        self.gl.glDeleteBuffers(1, [self.id])


class VertexArray:
    def __init__(self, ctx, program, content):
        self.gl = ctx.gl
        g = self.gl
        self.program = program
        self.id = int(g.glGenVertexArrays(1))
        g.glBindVertexArray(self.id)
        self.count = 0
        for buffer, fmt, name in content:
            count = int(fmt[:-1])
            self.count = buffer.size // (count * 4)
            g.glBindBuffer(g.GL_ARRAY_BUFFER, buffer.id)
            location = g.glGetAttribLocation(program.id, name)
            if location >= 0:
                g.glEnableVertexAttribArray(location)
                g.glVertexAttribPointer(location, count, g.GL_FLOAT, False, count * 4, None)

    def render(self, mode):
        self.gl.glUseProgram(self.program.id)
        self.gl.glBindVertexArray(self.id)
        self.gl.glDrawArrays(mode, 0, self.count)

    def release(self):
        self.gl.glDeleteVertexArrays(1, [self.id])


class Texture:
    def __init__(self, ctx, size, components, data=None):
        self.gl = ctx.gl
        g = self.gl
        self.id = int(g.glGenTextures(1))
        self.size = size
        self.width, self.height = size
        self.components = components
        self.format = g.GL_RGBA if components == 4 else g.GL_RGB
        self.use()
        g.glPixelStorei(g.GL_UNPACK_ALIGNMENT, 1)
        g.glTexImage2D(
            g.GL_TEXTURE_2D,
            0,
            g.GL_RGBA8 if components == 4 else g.GL_RGB8,
            *size,
            0,
            self.format,
            g.GL_UNSIGNED_BYTE,
            data,
        )
        self.filter = (g.GL_LINEAR, g.GL_LINEAR)
        self.repeat_x = False
        self.repeat_y = False

    def use(self, location=0):
        self.gl.glActiveTexture(self.gl.GL_TEXTURE0 + location)
        self.gl.glBindTexture(self.gl.GL_TEXTURE_2D, self.id)

    def write(self, data, alignment=1):
        self.use()
        self.gl.glPixelStorei(self.gl.GL_UNPACK_ALIGNMENT, alignment)
        self.gl.glTexSubImage2D(
            self.gl.GL_TEXTURE_2D, 0, 0, 0, *self.size, self.format, self.gl.GL_UNSIGNED_BYTE, data
        )

    def parameter(self, name, value):
        self.use()
        self.gl.glTexParameteri(self.gl.GL_TEXTURE_2D, name, value)

    @property
    def filter(self):
        return self._filter

    @filter.setter
    def filter(self, value):
        self._filter = value
        self.parameter(self.gl.GL_TEXTURE_MIN_FILTER, value[0])
        self.parameter(self.gl.GL_TEXTURE_MAG_FILTER, value[1])

    @property
    def repeat_x(self):
        return False

    @repeat_x.setter
    def repeat_x(self, value):
        self.parameter(
            self.gl.GL_TEXTURE_WRAP_S, self.gl.GL_REPEAT if value else self.gl.GL_CLAMP_TO_EDGE
        )

    @property
    def repeat_y(self):
        return False

    @repeat_y.setter
    def repeat_y(self, value):
        self.parameter(
            self.gl.GL_TEXTURE_WRAP_T, self.gl.GL_REPEAT if value else self.gl.GL_CLAMP_TO_EDGE
        )

    def release(self):
        self.gl.glDeleteTextures([self.id])


class Framebuffer:
    def __init__(self, ctx, texture=None, size=None):
        self.ctx = ctx
        self.gl = ctx.gl
        g = self.gl
        self.size = texture.size if texture else size
        self.id = int(g.glGenFramebuffers(1)) if texture else 0
        if texture:
            self.use()
            g.glFramebufferTexture2D(
                g.GL_FRAMEBUFFER, g.GL_COLOR_ATTACHMENT0, g.GL_TEXTURE_2D, texture.id, 0
            )
            if g.glCheckFramebufferStatus(g.GL_FRAMEBUFFER) != g.GL_FRAMEBUFFER_COMPLETE:
                raise ValueError("Incomplete framebuffer")

    def use(self):
        self.gl.glBindFramebuffer(self.gl.GL_FRAMEBUFFER, self.id)
        self.ctx.viewport = (0, 0, *self.size)

    def clear(self, *rgba):
        self.gl.glClearColor(*rgba)
        self.gl.glClear(self.gl.GL_COLOR_BUFFER_BIT)

    def read(self, components=3):
        self.use()
        g = self.gl
        g.glPixelStorei(g.GL_PACK_ALIGNMENT, 1)
        # GLES guarantees RGBA/UNSIGNED_BYTE; remove alpha after readback if RGB requested.
        raw = g.glReadPixels(0, 0, *self.size, g.GL_RGBA, g.GL_UNSIGNED_BYTE)
        data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 4)
        return data[:, :components].tobytes()

    def release(self):
        if self.id:
            self.gl.glDeleteFramebuffers(1, [self.id])


class Context:
    def __init__(self, size, dialect="gles"):
        from OpenGL import GL

        self.gl = GL
        self.dialect = dialect
        self.info = {
            key: GL.glGetString(getattr(GL, key)).decode()
            for key in ["GL_RENDERER", "GL_VENDOR", "GL_VERSION", "GL_SHADING_LANGUAGE_VERSION"]
        }
        self.info["GL_MAX_TEXTURE_SIZE"] = int(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_SIZE))
        self.screen = Framebuffer(self, size=size)

    def program(self, **kwargs):
        return Program(self, **kwargs)

    def buffer(self, data):
        return Buffer(self, data)

    def vertex_array(self, program, content):
        return VertexArray(self, program, content)

    def texture(self, size, components, data=None):
        return Texture(self, size, components, data)

    def framebuffer(self, color_attachments):
        return Framebuffer(self, color_attachments[0])

    def enable(self, flags):
        if flags & moderngl.BLEND:
            self.gl.glEnable(self.gl.GL_BLEND)
        if flags & moderngl.PROGRAM_POINT_SIZE and self.dialect != "gles":
            self.gl.glEnable(self.gl.GL_PROGRAM_POINT_SIZE)

    def disable(self, flags):
        if flags & moderngl.BLEND:
            self.gl.glDisable(self.gl.GL_BLEND)
        if flags & moderngl.PROGRAM_POINT_SIZE and self.dialect != "gles":
            self.gl.glDisable(self.gl.GL_PROGRAM_POINT_SIZE)

    @property
    def viewport(self):
        return self._viewport

    @viewport.setter
    def viewport(self, value):
        self._viewport = value
        self.gl.glViewport(*value)

    @property
    def scissor(self):
        return None

    @scissor.setter
    def scissor(self, value):
        if value is None:
            self.gl.glDisable(self.gl.GL_SCISSOR_TEST)
        else:
            self.gl.glEnable(self.gl.GL_SCISSOR_TEST)
            self.gl.glScissor(*value)

    @property
    def blend_func(self):
        return self._blend

    @blend_func.setter
    def blend_func(self, value):
        self._blend = value
        self.gl.glBlendFuncSeparate(*value)

    def release(self):
        pass

/* Legacy VideoCore IV projector output. Control and project parsing live in appliance.py. */
#define _POSIX_C_SOURCE 200809L
#include <bcm_host.h>
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <zlib.h>

/* ALSA PCM ABI. Stretch ships libasound.so.2 but its development headers are optional. */
typedef struct _snd_pcm snd_pcm_t;
extern int snd_pcm_open(snd_pcm_t **, const char *, int, int);
extern int snd_pcm_close(snd_pcm_t *);
extern int snd_pcm_set_params(snd_pcm_t *, int, int, unsigned, unsigned, int, unsigned);
extern long snd_pcm_writei(snd_pcm_t *, const void *, unsigned long);
extern int snd_pcm_delay(snd_pcm_t *, long *);
extern int snd_pcm_recover(snd_pcm_t *, int, int);
extern int snd_pcm_drop(snd_pcm_t *);
extern const char *snd_strerror(int);
enum { ALSA_PLAYBACK = 0, ALSA_NONBLOCK = 1, ALSA_S16_LE = 2, ALSA_INTERLEAVED = 3 };

#define MAX_SURFACES 20
#define MAX_KEYS 1024
#define AUDIO_RATE 48000
#define FPS 30
#define KEY_INTERVAL 30
#define MAX_ATLAS_SIZE 1024

typedef struct { double time, value; int hold; } Key;
typedef struct {
    int media, circle, multiply, nkeys;
    float logical[2], rgb[3], uv[4], corners[8];
    double opacity;
    Key keys[MAX_KEYS];
} Surface;
static Surface surfaces[MAX_SURFACES];
static int count, looping, has_audio, offscreen;
static double duration;
static int viewport_w, viewport_h, viewport_x, viewport_y;
static int logical_w, logical_h;
static EGLDisplay display = EGL_NO_DISPLAY;
static EGLContext context = EGL_NO_CONTEXT;
static EGLSurface window = EGL_NO_SURFACE;
static EGL_DISPMANX_WINDOW_T native;
static DISPMANX_DISPLAY_HANDLE_T dispman;
static GLuint program, texture;
static GLint position, uv, geometry, region, color, shape, size, style, atlas_on, blend;
static long audio_offset, audio_end, audio_written;
static double audio_drain_deadline;
static const char *audio_device;
static FILE *audio_file;
static snd_pcm_t *pcm;
static int16_t pcm_buffer[2048 * 2];
static FILE *atlas_file;
static unsigned frame_total, atlas_w, atlas_h;
static uint32_t *offsets;
static unsigned char *pixels, *delta, *compressed;
static unsigned pixels_len, compressed_max;
static int last_frame = -1, has_frame;
static volatile sig_atomic_t quitting;
static int playing, stopped = 1, black, resume_after_blackout, pattern, isolate = -1, dirty = 1;
static double current, base_time, base_position, max_time;

static double clock_sec(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return value.tv_sec + value.tv_nsec / 1e9;
}
static void on_signal(int sig) { (void)sig; quitting = 1; }
static void fail(const char *message) {
    fprintf(stderr, "%s\n", message);
    exit(EXIT_FAILURE);
}
static uint32_t word(FILE *file) {
    unsigned char b[4];
    if (fread(b, 1, 4, file) != 4) fail("Truncated atlas index");
    return (uint32_t)b[0] | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16 | (uint32_t)b[3] << 24;
}
static void open_atlas(const char *path) {
    atlas_file = fopen(path, "rb");
    if (!atlas_file || word(atlas_file) != 0x31505350) fail("Invalid Pi atlas");
    atlas_w = word(atlas_file);
    atlas_h = word(atlas_file);
    frame_total = word(atlas_file);
    GLint gpu_limit = 0;
    glGetIntegerv(GL_MAX_TEXTURE_SIZE, &gpu_limit);
    if (!atlas_w || !atlas_h || atlas_w > MAX_ATLAS_SIZE || atlas_h > MAX_ATLAS_SIZE ||
        gpu_limit <= 0 || atlas_w > (unsigned)gpu_limit || atlas_h > (unsigned)gpu_limit ||
        !frame_total || frame_total > 108000) fail("Pi atlas exceeds limits");
    pixels_len = atlas_w * atlas_h * 2;
    offsets = calloc(frame_total + 1, sizeof(*offsets));
    pixels = malloc(pixels_len);
    delta = malloc(pixels_len);
    compressed_max = compressBound(pixels_len);
    compressed = malloc(compressed_max);
    if (!offsets || !pixels || !delta || !compressed) fail("Insufficient atlas memory");
    for (unsigned i = 0; i <= frame_total; i++) offsets[i] = word(atlas_file);
    for (unsigned i = 0; i < frame_total; i++) {
        if (offsets[i] < 20 + frame_total * 4 || offsets[i + 1] < offsets[i] ||
            offsets[i + 1] - offsets[i] > compressed_max ||
            (i % KEY_INTERVAL == 0 && offsets[i + 1] == offsets[i]))
            fail("Invalid Pi atlas offsets");
    }
    if (fseek(atlas_file, 0, SEEK_END) || ftell(atlas_file) != (long)offsets[frame_total])
        fail("Pi atlas is incomplete");
}
static void frame_at(int frame) {
    if (frame == last_frame) return;
    int start = frame - frame % KEY_INTERVAL;
    if (last_frame >= start && last_frame < frame) start = last_frame + 1;
    for (int i = start; i <= frame; i++) {
        unsigned amount = offsets[i + 1] - offsets[i];
        if (!amount) continue;
        if (fseek(atlas_file, offsets[i], SEEK_SET) ||
            fread(compressed, 1, amount, atlas_file) != amount) fail("Cannot read Pi atlas");
        uLongf length = pixels_len;
        unsigned char *out = i % KEY_INTERVAL == 0 ? pixels : delta;
        if (uncompress(out, &length, compressed, amount) != Z_OK || length != pixels_len)
            fail("Corrupt Pi atlas frame");
        if (out == delta) {
            for (unsigned j = 0; j < pixels_len; j++) pixels[j] ^= delta[j];
        }
    }
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, atlas_w, atlas_h, GL_RGB,
                    GL_UNSIGNED_SHORT_5_6_5, pixels);
    last_frame = frame;
    has_frame = 1;
    dirty = 1;
}
static GLuint shader(GLenum type, const char *code) {
    GLuint id = glCreateShader(type);
    glShaderSource(id, 1, &code, NULL);
    glCompileShader(id);
    GLint ok;
    glGetShaderiv(id, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char error[1024];
        glGetShaderInfoLog(id, sizeof(error), NULL, error);
        fail(error);
    }
    return id;
}
static void open_display(int hidden) {
    offscreen = hidden;
    bcm_host_init();
    uint32_t width = logical_w, height = logical_h;
    if (!hidden && graphics_get_display_size(0, &width, &height) < 0)
        fail("HDMI display is unavailable");
    display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (display == EGL_NO_DISPLAY || !eglInitialize(display, NULL, NULL) ||
        !eglBindAPI(EGL_OPENGL_ES_API)) fail("Broadcom EGL is unavailable");
    EGLint attributes[] = {EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT, EGL_SURFACE_TYPE,
        hidden ? EGL_PBUFFER_BIT : EGL_WINDOW_BIT, EGL_NONE};
    EGLint available;
    EGLConfig config;
    if (!eglChooseConfig(display, attributes, &config, 1, &available) || !available)
        fail("No OpenGL ES 2 display configuration");
    EGLint version[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    context = eglCreateContext(display, config, EGL_NO_CONTEXT, version);
    if (hidden) {
        EGLint dims[] = {EGL_WIDTH, width, EGL_HEIGHT, height, EGL_NONE};
        window = eglCreatePbufferSurface(display, config, dims);
    } else {
        VC_RECT_T dest, src;
        vc_dispmanx_rect_set(&dest, 0, 0, width, height);
        vc_dispmanx_rect_set(&src, 0, 0, width << 16, height << 16);
        dispman = vc_dispmanx_display_open(0);
        DISPMANX_UPDATE_HANDLE_T update = vc_dispmanx_update_start(0);
        native.element = vc_dispmanx_element_add(update, dispman, 100, &dest, 0, &src,
                          DISPMANX_PROTECTION_NONE, NULL, NULL, DISPMANX_NO_ROTATE);
        native.width = width;
        native.height = height;
        if (!native.element || vc_dispmanx_update_submit_sync(update))
            fail("Could not open the projector layer");
        window = eglCreateWindowSurface(display, config, &native, NULL);
    }
    if (context == EGL_NO_CONTEXT || window == EGL_NO_SURFACE ||
        !eglMakeCurrent(display, window, window, context)) fail("Cannot activate Broadcom EGL");
    const char *gpu = (const char *)glGetString(GL_RENDERER);
    if (!gpu || !strstr(gpu, "VideoCore")) fail("Broadcom hardware renderer is unavailable");
    printf("GPU %s (%ux%u)\n", gpu, width, height);
    eglSwapInterval(display, hidden ? 0 : 1);
    float scale = fminf(width / (float)logical_w, height / (float)logical_h);
    viewport_w = (int)lroundf(logical_w * scale);
    viewport_h = (int)lroundf(logical_h * scale);
    viewport_x = ((int)width - viewport_w) / 2;
    viewport_y = ((int)height - viewport_h) / 2;
}
static void setup_shader(void) {
    const char *vertex =
        "attribute vec2 vertex; varying vec2 p; uniform mat3 quad;"
        "void main(){p=vertex; vec3 q=quad*vec3(vertex,1.);"
        "gl_Position=vec4(2.*q.x-q.z,q.z-2.*q.y,0.,q.z);}";
    const char *fragment =
        "precision mediump float; varying vec2 p; uniform sampler2D image;"
        "uniform vec4 region,color; uniform vec2 logical; uniform int shape,style,atlas,blending;"
        "void main(){if(shape==1 && length((p-0.5)*(logical/min(logical.x,logical.y)))>0.5)discard;"
        "vec3 c=color.rgb;"
        "if(atlas==1)c=texture2D(image, region.xy+p*region.zw).rgb;"
        "if(style==1){vec2 edge=abs(fract(p*8.+.5)-.5);"
        "c=(min(edge.x,edge.y)<.045?vec3(.68,.88,1.):vec3(.06,.13,.18));}"
        "if(style==3){if(min(min(p.x,p.y),min(1.-p.x,1.-p.y))>.025)discard;c=vec3(1.);}"
        "if(blending==1)c=mix(vec3(1.),c,color.a);gl_FragColor=vec4(c,color.a);}";
    GLuint vs = shader(GL_VERTEX_SHADER, vertex);
    GLuint fs = shader(GL_FRAGMENT_SHADER, fragment);
    program = glCreateProgram();
    glAttachShader(program, vs);
    glAttachShader(program, fs);
    glLinkProgram(program);
    GLint linked;
    glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (!linked) {
        char error[1024];
        glGetProgramInfoLog(program, sizeof error, NULL, error);
        fail(error);
    }
    glUseProgram(program);
    position = glGetAttribLocation(program, "vertex");
    geometry = glGetUniformLocation(program, "quad");
    region = glGetUniformLocation(program, "region");
    color = glGetUniformLocation(program, "color");
    shape = glGetUniformLocation(program, "shape");
    size = glGetUniformLocation(program, "logical");
    style = glGetUniformLocation(program, "style");
    atlas_on = glGetUniformLocation(program, "atlas");
    blend = glGetUniformLocation(program, "blending");
    uv = glGetUniformLocation(program, "image");
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, atlas_w, atlas_h, 0, GL_RGB,
                 GL_UNSIGNED_SHORT_5_6_5, NULL);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glUniform1i(uv, 0);
    glDeleteShader(vs);
    glDeleteShader(fs);
}
static void warp(const float *p, float *m) {
    float dx = p[0] - p[2] + p[4] - p[6], dy = p[1] - p[3] + p[5] - p[7];
    float ax = p[2] - p[4], ay = p[3] - p[5], bx = p[6] - p[4], by = p[7] - p[5];
    float det = ax * by - bx * ay;
    float g = (dx * by - bx * dy) / det, h = (ax * dy - dx * ay) / det;
    m[0] = (1+g)*p[2]-p[0]; m[1] = (1+g)*p[3]-p[1]; m[2] = g;
    m[3] = (1+h)*p[6]-p[0]; m[4] = (1+h)*p[7]-p[1]; m[5] = h;
    m[6] = p[0]; m[7] = p[1]; m[8] = 1;
}
static double opacity_at(const Surface *s) {
    if (!s->nkeys || current < s->keys[0].time) return s->opacity;
    for (int i = 1; i < s->nkeys; i++) {
        Key a = s->keys[i-1], b = s->keys[i];
        if (current < b.time)
            return a.value + (a.hold ? 0 : (b.value-a.value)*(current-a.time)/(b.time-a.time));
    }
    return s->keys[s->nkeys-1].value;
}
static void draw(void) {
    static const GLfloat vertices[] = {0,0,1,0,0,1,1,1};
    glViewport(viewport_x, viewport_y, viewport_w, viewport_h);
    glClearColor(0, 0, 0, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    glEnable(GL_BLEND);
    glEnableVertexAttribArray(position);
    glVertexAttribPointer(position, 2, GL_FLOAT, GL_FALSE, 0, vertices);
    for (int i = 0; i < count && !black; i++) {
        const Surface *s = &surfaces[i];
        if (isolate >= 0 && isolate != i) continue;
        if (stopped && !pattern) continue;
        if (!pattern && s->media && !has_frame) continue;
        float opacity = pattern ? 1.0 : opacity_at(s);
        if (opacity <= 0) continue;
        float m[9];
        warp(s->corners, m);
        glUniformMatrix3fv(geometry, 1, GL_FALSE, m);
        glUniform4fv(region, 1, s->uv);
        glUniform2fv(size, 1, s->logical);
        glUniform1i(shape, pattern == 3 ? 0 : s->circle);
        glUniform1i(style, pattern);
        glUniform1i(atlas_on, !pattern && s->media);
        glUniform4f(color, pattern ? 1 : s->rgb[0], pattern ? 1 : s->rgb[1],
                    pattern ? 1 : s->rgb[2], opacity);
        int multiply = !pattern && s->multiply;
        glUniform1i(blend, multiply);
        if (multiply) glBlendFuncSeparate(GL_DST_COLOR, GL_ZERO, GL_ZERO, GL_ONE);
        else glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ZERO, GL_ONE);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    }
    if (glGetError() != GL_NO_ERROR || !eglSwapBuffers(display, window))
        fail("Projector frame could not be presented");
    dirty = 0;
}
static void measure_atlas(void) {
    unsigned first = 0, last = frame_total < KEY_INTERVAL ? frame_total : KEY_INTERVAL;
    uint32_t largest = 0;
    // A busy keyframe interval exercises SD reads, decompression, GPU upload and drawing.
    for (unsigned start = 0; start < frame_total; start += KEY_INTERVAL) {
        unsigned end = start + KEY_INTERVAL;
        if (end > frame_total) break;
        uint32_t length = offsets[end] - offsets[start];
        if (length > largest) {
            largest = length;
            first = start;
            last = end;
        }
    }
    stopped = 0;
    double start = clock_sec();
    for (unsigned frame = first; frame < last; frame++) {
        current = frame / (double)FPS;
        frame_at((int)frame);
        draw();
        glFinish();
    }
    printf("BENCH %.2f\n", (last - first) / (clock_sec() - start));
}
static void load(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f || fscanf(f, "%d%d%d%lf%d%d%ld%ld", &count, &logical_w, &logical_h, &duration,
                     &looping, &has_audio, &audio_offset, &audio_end) != 8 ||
        count < 1 || count > MAX_SURFACES || logical_w < 1 || logical_h < 1)
        fail("Invalid Pi show geometry");
    for (int i = 0; i < count; i++) {
        Surface *s = &surfaces[i];
        if (fscanf(f, "%d%d%d%f%f%f%f%f%lf%d", &s->media, &s->circle, &s->multiply,
                   &s->logical[0], &s->logical[1], &s->rgb[0], &s->rgb[1], &s->rgb[2],
                   &s->opacity, &s->nkeys) != 10 || s->nkeys < 0 || s->nkeys > MAX_KEYS)
            fail("Invalid surface definition");
        for (int j = 0; j < 4; j++)
            if (fscanf(f, "%f", &s->uv[j]) != 1) fail("Invalid atlas region");
        for (int j = 0; j < 8; j++)
            if (fscanf(f, "%f", &s->corners[j]) != 1) fail("Invalid surface coordinates");
        for (int j = 0; j < s->nkeys; j++)
            if (fscanf(f, "%lf%lf%d", &s->keys[j].time, &s->keys[j].value, &s->keys[j].hold) != 3)
                fail("Invalid lighting curve");
    }
    fclose(f);
}
static void close_audio(void) {
    audio_drain_deadline = 0;
    if (pcm) { snd_pcm_drop(pcm); snd_pcm_close(pcm); pcm = NULL; }
}
static void pause_show(void) {
    playing = 0;
    close_audio();
}
static void start_show(void) {
    if (current >= duration) current = 0;
    /* Upload and render the first frame before starting the playback clock. */
    if (!pattern) frame_at((int)fmin(frame_total - 1, floor(current * FPS)));
    stopped = 0;
    draw();
    if (has_audio) {
        int err = snd_pcm_open(&pcm, audio_device, ALSA_PLAYBACK, ALSA_NONBLOCK);
        if (err >= 0) err = snd_pcm_set_params(pcm, ALSA_S16_LE, ALSA_INTERLEAVED,
                                                2, AUDIO_RATE, 1, 100000);
        if (err < 0) {
            printf("ERROR Audio %s: %s\n", audio_device, snd_strerror(err));
            close_audio();
            return;
        }
        audio_written = lround(current * AUDIO_RATE);
    }
    playing = 1;
    stopped = 0;
    base_position = current;
    base_time = clock_sec();
    dirty = 1;
}
static void update_clock(void) {
    if (!playing) return;
    int audio_finished = 0;
    if (pcm) {
        long available = audio_end - audio_written;
        if (available > 0) {
            long wanted = available < 1024 ? available : 1024;
            if (fseek(audio_file, audio_offset + audio_written * 4, SEEK_SET) ||
                fread(pcm_buffer, 4, wanted, audio_file) != (size_t)wanted) fail("Cannot read audio");
            long wrote = snd_pcm_writei(pcm, pcm_buffer, wanted);
            if (wrote > 0) audio_written += wrote;
            else if (wrote != -EAGAIN && wrote < 0 && snd_pcm_recover(pcm, wrote, 1) < 0)
                fail("Audio device stopped responding");
        }
        long delay = 0;
        int have_delay = snd_pcm_delay(pcm, &delay) >= 0;
        if (have_delay) {
            double reported = (audio_written - (delay > 0 ? delay : 0)) / (double)AUDIO_RATE;
            if (reported > current) current = reported;
        }
        if (audio_written >= audio_end) {
            double now = clock_sec();
            // Some HDMI drivers keep reporting a small delay after the final sample.
            if (!audio_drain_deadline) {
                double pending = have_delay ? fmax(0, delay) / AUDIO_RATE : 0.1;
                audio_drain_deadline = now + pending + 0.025;
            }
            audio_finished = current >= audio_end / (double)AUDIO_RATE - 0.0005 ||
                             now >= audio_drain_deadline;
        }
        /* ALSA's null sink is for bounded hardware tests and consumes samples immediately. */
        if (!strcmp(audio_device, "null")) current = clock_sec() - base_time + base_position;
    } else current = clock_sec() - base_time + base_position;
    if (current >= duration - 0.0005 || audio_finished) {
        pause_show();
        if (looping) { current = 0; start_show(); }
        else current = duration;
    }
}
static void command(const char *line) {
    int p, index;
    if (offscreen && sscanf(line, "pixel %d %d", &p, &index) == 2 &&
            p >= 0 && p < viewport_w && index >= 0 && index < viewport_h) {
        unsigned char rgb[4] = {0};
        glReadPixels(p + viewport_x, viewport_h - 1 - index + viewport_y, 1, 1,
                     GL_RGBA, GL_UNSIGNED_BYTE, rgb);
        printf("PIXEL %d %d %u %u %u\n", p, index, rgb[0], rgb[1], rgb[2]);
        return;
    }
    float v[8];
    double seconds;
    if (!strcmp(line, "play") && !playing && !black) start_show();
    else if (!strcmp(line, "pause")) pause_show();
    else if (!strcmp(line, "stop")) {
        pause_show(); stopped = 1; current = 0; resume_after_blackout = 0;
    } else if (!strcmp(line, "blackout") && !black) {
        resume_after_blackout = playing;
        pause_show();
        black = 1;
    } else if (!strcmp(line, "restore") && black) {
        black = 0;
        if (resume_after_blackout) start_show();
        resume_after_blackout = 0;
    }
    else if (!strcmp(line, "quit")) quitting = 1;
    else if (sscanf(line, "seek %lf", &seconds) == 1 && isfinite(seconds)) {
        int resume = playing;
        pause_show();
        current = fmin(duration, fmax(0, seconds));
        stopped = 0;
        if (resume) start_show();
    } else if (sscanf(line, "pattern %d %d", &p, &index) == 2 &&
               p >= 0 && p <= 3 && index >= -1 && index < count) {
        pattern = p;
        isolate = index;
    } else if (sscanf(line, "map %d %f %f %f %f %f %f %f %f", &index,
                      &v[0], &v[1], &v[2], &v[3], &v[4], &v[5], &v[6], &v[7]) == 9 &&
               index >= 0 && index < count) memcpy(surfaces[index].corners, v, sizeof(v));
    dirty = 1;
}
static void commands(void) {
    static char line[512];
    static size_t used;
    char bytes[256];
    ssize_t size_read;
    while ((size_read = read(STDIN_FILENO, bytes, sizeof bytes)) > 0) {
        for (ssize_t i = 0; i < size_read; i++) {
            if (bytes[i] == '\n') {
                line[used] = 0;
                command(line);
                used = 0;
            } else if (used + 1 < sizeof line) line[used++] = bytes[i];
        }
    }
    if (size_read == 0) quitting = 1;
}
int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    signal(SIGTERM, on_signal);
    signal(SIGINT, on_signal);
    int probe = argc == 2 && !strcmp(argv[1], "--probe");
    int measure = argc == 4 && !strcmp(argv[3], "--measure");
    int hidden = argc == 6 && !strcmp(argv[5], "--hidden");
    int bench = argc == 6 && !hidden;
    if (!probe && !measure && argc != 5 && !bench && !hidden)
        fail("Usage: renderer geometry.txt atlas.psp master.wav ALSA_DEVICE [benchmark_seconds]");
    if (probe) logical_w = logical_h = 64;
    else load(argv[1]);
    open_display(probe || bench || hidden || measure);
    if (probe) return 0;
    open_atlas(argv[2]);
    setup_shader();
    if (measure) {
        measure_atlas();
        eglTerminate(display);
        return 0;
    }
    if (bench) max_time = strtod(argv[5], NULL);
    audio_device = argv[4];
    if (has_audio && !(audio_file = fopen(argv[3], "rb"))) fail("Cannot open master audio");
    if (fcntl(STDIN_FILENO, F_SETFL, O_NONBLOCK) < 0) fail("Cannot configure player controls");
    double started = clock_sec(), window_start = started;
    unsigned frames = 0, dropped = 0, total = 0;
    printf("READY\n");
    if (bench) {
        start_show();
        started = window_start = clock_sec();
    }
    while (!quitting && (!bench || clock_sec() - started < max_time)) {
        if (!bench) commands();
        update_clock();
        int frame = (int)fmin(frame_total - 1, floor(current * FPS + 0.0001));
        if (!black && !stopped && !pattern && frame != last_frame) {
            if (playing && last_frame >= 0 && frame > last_frame + 1)
                dropped += frame - last_frame - 1;
            frame_at(frame);
        }
        if (dirty) { draw(); frames++; total++; }
        double now = clock_sec();
        if (now - window_start >= 0.5) {
            printf("STATE %.3f %s %.2f %u\n", current,
                   playing ? "playing" : stopped ? "stopped" : "paused",
                   frames / (now - window_start), dropped);
            frames = 0;
            window_start = now;
        }
        struct timespec tick = {0, 2500000};
        nanosleep(&tick, NULL);
    }
    printf("END %u %u\n", total, dropped);
    close_audio();
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroySurface(display, window);
    eglDestroyContext(display, context);
    eglTerminate(display);
    if (native.element) {
        DISPMANX_UPDATE_HANDLE_T update = vc_dispmanx_update_start(0);
        vc_dispmanx_element_remove(update, native.element);
        vc_dispmanx_update_submit_sync(update);
        vc_dispmanx_display_close(dispman);
    }
    return 0;
}

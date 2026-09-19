export type Named = { id: string; name: string; enabled: boolean };
export type Viewport = { x: number; y: number; width: number; height: number };
export type Surface = Named & {
  role: "media" | "lighting";
  shape: "rectangle" | "circle";
  light: { color: string };
  projector_id: string;
  logical: { width: number; height: number };
  mapping: Record<
    "top_left" | "top_right" | "bottom_right" | "bottom_left",
    [number, number]
  >;
  tags: string[];
  ambient_profile: string | null;
  foreground_enabled: boolean;
};
export type Project = {
  schema_version: number;
  id: string;
  name: string;
  description: string;
  canvas: {
    width: number;
    height: number;
    refresh_rate: number;
    fullscreen: boolean;
    monitor: number;
  };
  projectors: (Named & { viewport: Viewport })[];
  surfaces: Surface[];
  scenes: (Named & {
    type: "color" | "image" | "video" | "audio";
    color?: string;
    tags: string[];
    path?: string;
    fit?: string;
    focal_point?: [number, number];
    playback?: string;
    end_behavior?: string;
    start_seconds?: number;
    end_seconds?: number | null;
  })[];
  ambient_profiles: (Named & {
    type: string;
    color: string;
    opacity: number;
    count: number;
  })[];
  show: {
    mode: string;
    timeline: Timeline;
    max_simultaneous: number;
    auto_start: boolean;
    fade_in_seconds: number;
    hold_seconds: { min: number; max: number };
    fade_out_seconds: number;
    gap_seconds: { min: number; max: number };
    queue_length: number;
    seed: number | null;
    surfaces: { include_tags: string[]; exclude_tags: string[] };
    scenes: { include_tags: string[]; exclude_tags: string[] };
  };
};
export type Cue = {
  manual?: boolean;
  id: number;
  surface_id: string;
  scene_id: string;
  fade_in: number;
  hold: number;
  fade_out: number;
  gap: number;
};
export type Status = {
  deployment_kind?: "preview" | "installed" | null;
  system?: {
    cpu_percent: number;
    memory_bytes: number;
    memory_measurement: string;
    free_disk_bytes: number;
    temperature_c: number | null;
    throttling: string | null;
  };
  mode: string;
  deployment?: {
    id: string;
    source_project: { name: string };
    encoder_backend: string;
  } | null;
  timeline: null | {
    position: number;
    duration: number;
    loop: boolean;
    cycle: number;
    ended: boolean;
    layers: {
      id: string;
      surface_id: string;
      source_id: string | null;
      opacity: number;
      role: string;
    }[];
    upcoming: { time: number; surface_id: string; kind: string }[];
  };
  state: string;
  transport: string;
  blackout: boolean;
  pattern: string;
  phase: string;
  opacity: number;
  remaining: number;
  elapsed: number;
  show_time: number;
  current: Cue | null;
  queue: Cue[];
  eligible_surfaces: number;
  eligible_scenes: number;
  renderer: {
    status: string;
    fps: number;
    late_frames: number;
    gpu?: string;
    output_size?: number[];
    warning?: string;
    timeline_clock?: Record<string, any>;
    graphics?: Record<string, any>;
    decoder?: {
      state: string;
      backend: string;
      error: string | null;
      pts?: number;
      decoded_frames?: number;
    };
  };
  calibration: { surface_id: string; dirty: boolean } | null;
  revision: number;
  clients: number;
  uptime: number;
  warnings: string[];
  events: { time: number; title: string; detail: string }[];
};

export type MediaAsset = {
  id: string;
  name: string;
  path: string;
  type: "video" | "image" | "audio";
  error: string | null;
  thumbnail: boolean;
  bytes?: number;
  width?: number;
  height?: number;
  duration_seconds?: number;
  fps?: number;
  codec?: string;
};

export type OpacityKey = {
  time_seconds: number;
  value: number;
  interpolation: "linear" | "hold";
};
export type Clip = {
  id: string;
  scene_id: string;
  start_seconds: number;
  source_in_seconds: number;
  duration_seconds: number;
};
export type Track = {
  id: string;
  surface_id: string;
  clips: Clip[];
  opacity: { default: number; keyframes: OpacityKey[] };
};
export type Timeline = {
  duration_seconds: number;
  loop: boolean;
  track_order: string[];
  tracks: Track[];
  audio: null | {
    scene_id: string;
    start_seconds: number;
    source_in_seconds: number;
    duration_seconds: number;
    volume: number;
    muted: boolean;
    sync_offset_ms: number;
  };
};
export type Capabilities = {
  deployment_write: boolean;
  deployment_reason: string | null;
  role: string;
  timeline_edit: boolean;
  compiler: boolean;
  compiler_reason: string | null;
  media_upload: boolean;
  deploy: boolean;
  physical_pi_verified: boolean;
};
export type Job = {
  id: string;
  kind: string;
  state: string;
  progress: number;
  message: string;
  error?: string;
  result?: Record<string, any>;
};

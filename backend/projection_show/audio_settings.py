"""Installation-local audio routing and explicit runtime overrides, outside bundles."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AudioSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    audio_sink: Literal["auto", "alsa", "fake"] = "auto"
    audio_device: str = Field(default="", max_length=200, pattern=r"^[^\x00-\x1f]*$")
    volume: float | None = Field(default=None, ge=0, le=1)
    muted: bool | None = None
    sync_offset_ms: int | None = Field(default=None, ge=-1000, le=1000)

    def apply(self, runtime):
        runtime.playback_options = self.model_dump(include={"audio_sink", "audio_device"})
        runtime.audio_overrides = self.model_dump(
            exclude={"audio_sink", "audio_device"}, exclude_none=True
        )

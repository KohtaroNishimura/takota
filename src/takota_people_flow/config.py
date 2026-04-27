from __future__ import annotations

from argparse import Namespace
from pathlib import Path
from typing import Any

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    stream_url: str | HttpUrl = Field(default="http://192.168.1.50:81/stream")
    model: str = Field(default="models/yolo11n.pt")
    device: str = Field(default="cpu")
    imgsz: int = Field(default=416, ge=160)
    conf: float = Field(default=0.35, ge=0.0, le=1.0)
    iou: float = Field(default=0.5, ge=0.0, le=1.0)
    camera_width: int | None = Field(default=None, ge=1)
    camera_height: int | None = Field(default=None, ge=1)
    camera_fps: float | None = Field(default=None, gt=0.0)
    camera_fourcc: str | None = Field(default="MJPG", min_length=4, max_length=4)
    frame_skip: int = Field(default=2, ge=1)
    max_frames: int = Field(default=30, ge=1)
    line_x_ratio: float = Field(default=0.5, gt=0.0, lt=1.0)
    stop_speed_px_per_sec: float = Field(default=12.0, ge=0.0)
    stop_duration_sec: float = Field(default=3.0, ge=0.0)
    output: Path = Field(default=Path("data/people_flow.csv"))
    badge_output: Path = Field(default=Path("data/badge_counts.csv"))
    aggregate_output: Path = Field(default=Path("data/people_flow_summary.csv"))
    badge_daily_output: Path = Field(default=Path("data/badge_daily_summary.csv"))
    badge_weekly_output: Path = Field(default=Path("data/badge_weekly_summary.csv"))
    preview_host: str = Field(default="0.0.0.0")
    preview_port: int = Field(default=8080, ge=1, le=65535)
    preview_jpeg_quality: int = Field(default=80, ge=1, le=100)
    preview_shutdown_enabled: bool = Field(default=False)
    preview_shutdown_command: str = Field(default="")

    @field_validator("stream_url", mode="before")
    @classmethod
    def allow_rtsp_urls(cls, value: Any) -> Any:
        if isinstance(value, str) and value.startswith("rtsp://"):
            return value
        return value

    @classmethod
    def from_args(cls, args: Namespace) -> "AppConfig":
        values = {
            key: value
            for key, value in vars(args).items()
            if value is not None
        }
        return cls(**values)

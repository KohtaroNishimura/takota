"""Frame capture from ATOMS3RM12 streams."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from time import monotonic

import cv2
import numpy as np


@dataclass(frozen=True)
class CapturedFrame:
    index: int
    timestamp_monotonic: float
    image: np.ndarray

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])


class StreamCaptureError(RuntimeError):
    """Raised when a stream cannot be opened or decoded."""


@dataclass(frozen=True)
class CaptureOptions:
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    fourcc: str | None = None


class StreamCapture:
    def __init__(
        self,
        stream_url: str,
        *,
        api_preference: int = cv2.CAP_ANY,
        options: CaptureOptions | None = None,
    ) -> None:
        self.stream_url = stream_url
        self.api_preference = api_preference
        self.options = options or CaptureOptions()
        self._capture: cv2.VideoCapture | None = None
        self._frame_index = 0

    def __enter__(self) -> "StreamCapture":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @property
    def is_open(self) -> bool:
        return self._capture is not None and self._capture.isOpened()

    def open(self) -> None:
        if self.is_open:
            return

        capture = cv2.VideoCapture(_video_capture_source(self.stream_url), self.api_preference)
        if not capture.isOpened():
            capture.release()
            raise StreamCaptureError(f"Could not open stream: {self.stream_url}")

        self._apply_options(capture)
        self._capture = capture
        self._frame_index = 0

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def _apply_options(self, capture: cv2.VideoCapture) -> None:
        if self.options.fourcc is not None:
            capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.options.fourcc))
        if self.options.width is not None:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.options.width)
        if self.options.height is not None:
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.options.height)
        if self.options.fps is not None:
            capture.set(cv2.CAP_PROP_FPS, self.options.fps)

    def read(self) -> CapturedFrame:
        if self._capture is None:
            raise StreamCaptureError("Stream is not open.")

        ok, image = self._capture.read()
        if not ok or image is None:
            raise StreamCaptureError(f"Could not read frame from stream: {self.stream_url}")

        self._frame_index += 1
        return CapturedFrame(
            index=self._frame_index,
            timestamp_monotonic=monotonic(),
            image=image,
        )

    def frames(self, *, max_frames: int | None = None, frame_skip: int = 1) -> Iterator[CapturedFrame]:
        if frame_skip < 1:
            raise ValueError("frame_skip must be >= 1.")

        emitted = 0
        while max_frames is None or emitted < max_frames:
            frame = self.read()
            if (frame.index - 1) % frame_skip != 0:
                continue
            emitted += 1
            yield frame


@dataclass(frozen=True)
class StreamCheckResult:
    frames: int
    width: int
    height: int
    elapsed_sec: float

    @property
    def fps(self) -> float:
        if self.elapsed_sec <= 0:
            return 0.0
        return self.frames / self.elapsed_sec


def check_stream(
    stream_url: str,
    *,
    max_frames: int = 30,
    frame_skip: int = 1,
    options: CaptureOptions | None = None,
) -> StreamCheckResult:
    started_at = monotonic()
    width = 0
    height = 0
    frames = 0

    with StreamCapture(stream_url, options=options) as capture:
        for frame in capture.frames(max_frames=max_frames, frame_skip=frame_skip):
            frames += 1
            width = frame.width
            height = frame.height

    return StreamCheckResult(
        frames=frames,
        width=width,
        height=height,
        elapsed_sec=monotonic() - started_at,
    )


def _video_capture_source(stream_url: str) -> str | int:
    if stream_url.isdigit():
        return int(stream_url)
    return stream_url

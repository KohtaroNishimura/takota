"""Person flow event detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import hypot

from .capture import CapturedFrame
from .tracker import TrackedPerson


@dataclass(frozen=True)
class FlowEvent:
    timestamp: str
    frame_index: int
    track_id: int
    event: str
    direction: str
    center_x: float
    center_y: float
    dwell_time_sec: float
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
    confidence: float
    active_tracks: int


@dataclass
class _TrackState:
    last_center_x: float
    last_center_y: float
    last_seen_monotonic: float
    last_side: int
    stopped_since_monotonic: float | None = None
    stopped_emitted: bool = False


class PeopleFlowAnalyzer:
    def __init__(
        self,
        *,
        line_x_ratio: float,
        stop_speed_px_per_sec: float,
        stop_duration_sec: float,
    ) -> None:
        self.line_x_ratio = line_x_ratio
        self.stop_speed_px_per_sec = stop_speed_px_per_sec
        self.stop_duration_sec = stop_duration_sec
        self._states: dict[int, _TrackState] = {}

    def update(self, frame: CapturedFrame, people: list[TrackedPerson]) -> list[FlowEvent]:
        active_track_ids = {person.track_id for person in people if person.track_id is not None}
        active_tracks = len(active_track_ids)
        line_x = frame.width * self.line_x_ratio
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")

        events: list[FlowEvent] = []
        for person in people:
            if person.track_id is None:
                continue

            side = self._side(person.center_x, line_x)
            state = self._states.get(person.track_id)
            if state is None:
                self._states[person.track_id] = _TrackState(
                    last_center_x=person.center_x,
                    last_center_y=person.center_y,
                    last_seen_monotonic=frame.timestamp_monotonic,
                    last_side=side,
                )
                continue

            crossing_event = self._crossing_event(timestamp, frame, person, state, side, active_tracks)
            if crossing_event is not None:
                events.append(crossing_event)

            stopped_event = self._stopped_event(timestamp, frame, person, state, active_tracks)
            if stopped_event is not None:
                events.append(stopped_event)

            state.last_center_x = person.center_x
            state.last_center_y = person.center_y
            state.last_seen_monotonic = frame.timestamp_monotonic
            if side != 0:
                state.last_side = side

        return events

    @staticmethod
    def _side(center_x: float, line_x: float) -> int:
        if center_x < line_x:
            return -1
        if center_x > line_x:
            return 1
        return 0

    def _crossing_event(
        self,
        timestamp: str,
        frame: CapturedFrame,
        person: TrackedPerson,
        state: _TrackState,
        side: int,
        active_tracks: int,
    ) -> FlowEvent | None:
        if side == 0 or state.last_side == 0 or side == state.last_side:
            return None

        direction = "left_to_right" if state.last_side < side else "right_to_left"
        return self._event(
            timestamp,
            frame,
            person,
            event="cross",
            direction=direction,
            dwell_time_sec=frame.timestamp_monotonic - state.last_seen_monotonic,
            active_tracks=active_tracks,
        )

    def _stopped_event(
        self,
        timestamp: str,
        frame: CapturedFrame,
        person: TrackedPerson,
        state: _TrackState,
        active_tracks: int,
    ) -> FlowEvent | None:
        elapsed = max(frame.timestamp_monotonic - state.last_seen_monotonic, 0.001)
        distance = hypot(person.center_x - state.last_center_x, person.center_y - state.last_center_y)
        speed = distance / elapsed

        if speed > self.stop_speed_px_per_sec:
            state.stopped_since_monotonic = None
            state.stopped_emitted = False
            return None

        if state.stopped_since_monotonic is None:
            state.stopped_since_monotonic = state.last_seen_monotonic

        dwell_time = frame.timestamp_monotonic - state.stopped_since_monotonic
        if state.stopped_emitted or dwell_time < self.stop_duration_sec:
            return None

        state.stopped_emitted = True
        return self._event(
            timestamp,
            frame,
            person,
            event="stopped",
            direction="stopped",
            dwell_time_sec=dwell_time,
            active_tracks=active_tracks,
        )

    @staticmethod
    def _event(
        timestamp: str,
        frame: CapturedFrame,
        person: TrackedPerson,
        *,
        event: str,
        direction: str,
        dwell_time_sec: float,
        active_tracks: int,
    ) -> FlowEvent:
        return FlowEvent(
            timestamp=timestamp,
            frame_index=frame.index,
            track_id=person.track_id if person.track_id is not None else -1,
            event=event,
            direction=direction,
            center_x=person.center_x,
            center_y=person.center_y,
            dwell_time_sec=dwell_time_sec,
            bbox_x1=person.bbox.x1,
            bbox_y1=person.bbox.y1,
            bbox_x2=person.bbox.x2,
            bbox_y2=person.bbox.y2,
            confidence=person.confidence,
            active_tracks=active_tracks,
        )

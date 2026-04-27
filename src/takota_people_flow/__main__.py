from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from time import monotonic

from rich.console import Console
from rich.table import Table

from .capture import CaptureOptions, StreamCapture, StreamCaptureError, check_stream
from .config import AppConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="takota-people-flow",
        description="Collect person-flow events from an ATOMS3RM12 stream using YOLO11.",
    )
    parser.add_argument("--stream-url", help="ATOMS3RM12 stream URL.")
    parser.add_argument("--model", help="YOLO model path or name, e.g. models/yolo11n.pt.")
    parser.add_argument("--device", help="Inference device, e.g. cpu, cuda, mps.")
    parser.add_argument("--imgsz", type=int, help="Inference image size.")
    parser.add_argument("--conf", type=float, help="Detection confidence threshold.")
    parser.add_argument("--iou", type=float, help="NMS/tracking IOU threshold.")
    parser.add_argument("--camera-width", type=int, help="Requested capture width for UVC cameras.")
    parser.add_argument("--camera-height", type=int, help="Requested capture height for UVC cameras.")
    parser.add_argument("--camera-fps", type=float, help="Requested capture FPS for UVC cameras.")
    parser.add_argument("--camera-fourcc", help="Requested capture FOURCC, e.g. MJPG.")
    parser.add_argument("--frame-skip", type=int, help="Run inference every N frames.")
    parser.add_argument("--max-frames", type=int, help="Number of frames to read for stream checks.")
    parser.add_argument("--line-x-ratio", type=float, help="Vertical crossing line position, 0.0 to 1.0.")
    parser.add_argument("--stop-speed-px-per-sec", type=float, help="Movement threshold for stopped detection.")
    parser.add_argument("--stop-duration-sec", type=float, help="Seconds before a track is considered stopped.")
    parser.add_argument("--output", help="CSV output path.")
    parser.add_argument("--badge-output", help="CSV output path for manual badge consumption counts.")
    parser.add_argument("--aggregate-output", help="CSV output path for people-flow summaries.")
    parser.add_argument("--badge-daily-output", help="CSV output path for daily badge summaries.")
    parser.add_argument("--badge-weekly-output", help="CSV output path for weekly badge summaries.")
    parser.add_argument("--preview-host", help="Preview HTTP server bind host.")
    parser.add_argument("--preview-port", type=int, help="Preview HTTP server port.")
    parser.add_argument("--preview-jpeg-quality", type=int, help="Preview JPEG quality, 1 to 100.")
    parser.add_argument(
        "--preview-shutdown-enabled",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Allow the preview page to request a system shutdown.",
    )
    parser.add_argument("--preview-shutdown-command", help="Fixed command used for preview shutdown requests.")
    parser.add_argument("--check-stream", action="store_true", help="Open STREAM_URL and read frames without YOLO.")
    parser.add_argument("--track", action="store_true", help="Run YOLO11 person detection and tracking.")
    parser.add_argument("--aggregate", action="store_true", help="Summarize saved CSV events into table rows.")
    parser.add_argument("--aggregate-interval-minutes", type=int, default=30, help="Aggregation interval in minutes.")
    parser.add_argument("--aggregate-badges", action="store_true", help="Summarize manual badge completion counts.")
    parser.add_argument("--preview-server", action="store_true", help="Serve live MJPEG preview in a browser.")
    parser.add_argument("--no-table", action="store_true", help="Hide per-frame tracking rows and print only summary.")
    parser.add_argument("--run-forever", action="store_true", help="Ignore --max-frames and keep processing until stopped.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = AppConfig.from_args(args)

    console = Console()
    console.print("[bold]takota-people-flow[/bold]")
    capture_options = CaptureOptions(
        width=config.camera_width,
        height=config.camera_height,
        fps=config.camera_fps,
        fourcc=config.camera_fourcc,
    )

    if args.aggregate:
        from .analysis import summarize_csv

        summaries = summarize_csv(config.output, interval_minutes=args.aggregate_interval_minutes)
        _write_people_flow_summary(config.aggregate_output, summaries)
        table = Table(title=f"People flow summary ({args.aggregate_interval_minutes} min)", padding=(0, 0))
        table.add_column("start", no_wrap=True)
        table.add_column("end", no_wrap=True)
        table.add_column("L->R", justify="right")
        table.add_column("R->L", justify="right")
        table.add_column("stopped", justify="right")
        table.add_column("events", justify="right")
        table.add_column("tracks", justify="right")
        table.add_column("peak", justify="right")
        for summary in summaries:
            table.add_row(
                f"{summary.start:%Y-%m-%d %H:%M}",
                f"{summary.end:%Y-%m-%d %H:%M}",
                str(summary.left_to_right),
                str(summary.right_to_left),
                str(summary.stopped),
                str(summary.total_events),
                str(summary.unique_tracks),
                str(summary.peak_active_tracks),
            )
        console.print(table)
        console.print({"input": str(config.output), "output": str(config.aggregate_output), "rows": len(summaries)})
        return

    if args.aggregate_badges:
        from .badges import summarize_badges

        daily_summaries, weekly_summaries = summarize_badges(config.badge_output)
        _write_daily_badge_summary(config.badge_daily_output, daily_summaries)
        _write_weekly_badge_summary(config.badge_weekly_output, weekly_summaries)

        daily_table = Table(title="Daily badge completions", padding=(0, 0))
        daily_table.add_column("date", no_wrap=True)
        daily_table.add_column("start", no_wrap=True)
        daily_table.add_column("end", no_wrap=True)
        daily_table.add_column("partial", justify="right")
        daily_table.add_column("badges", justify="right")
        daily_table.add_column("first_done", no_wrap=True)
        daily_table.add_column("last_done", no_wrap=True)
        daily_table.add_column("avg_hours", justify="right")
        for summary in daily_summaries:
            daily_table.add_row(
                summary.day.isoformat(),
                _format_time(summary.started_at),
                _format_time(summary.ended_at),
                f"{summary.partial_progress:.2f}",
                _format_badges(summary.badges),
                _format_time(summary.first_finished_at),
                _format_time(summary.last_finished_at),
                "-" if summary.average_hours_per_badge is None else f"{summary.average_hours_per_badge:.2f}",
            )

        weekly_table = Table(title="Weekly badge completions", padding=(0, 0))
        weekly_table.add_column("week", no_wrap=True)
        weekly_table.add_column("badges", justify="right")
        weekly_table.add_column("first_done", no_wrap=True)
        weekly_table.add_column("last_done", no_wrap=True)
        weekly_table.add_column("avg_hours", justify="right")
        for summary in weekly_summaries:
            weekly_table.add_row(
                f"{summary.week_start.isoformat()}..{summary.week_end.isoformat()}",
                _format_badges(summary.badges),
                _format_datetime(summary.first_finished_at),
                _format_datetime(summary.last_finished_at),
                "-" if summary.average_hours_per_badge is None else f"{summary.average_hours_per_badge:.2f}",
            )

        console.print(daily_table)
        console.print(weekly_table)
        console.print(
            {
                "input": str(config.badge_output),
                "daily_output": str(config.badge_daily_output),
                "weekly_output": str(config.badge_weekly_output),
                "daily_rows": len(daily_summaries),
                "weekly_rows": len(weekly_summaries),
            }
        )
        return

    if args.check_stream:
        try:
            result = check_stream(
                str(config.stream_url),
                max_frames=config.max_frames,
                frame_skip=config.frame_skip,
                options=capture_options,
            )
        except StreamCaptureError as exc:
            console.print(f"[red]Stream check failed:[/red] {exc}")
            raise SystemExit(1) from exc

        console.print("[green]Stream check succeeded.[/green]")
        console.print(
            {
                "stream_url": str(config.stream_url),
                "frames": result.frames,
                "width": result.width,
                "height": result.height,
                "elapsed_sec": round(result.elapsed_sec, 3),
                "fps": round(result.fps, 2),
                "requested_camera_width": config.camera_width,
                "requested_camera_height": config.camera_height,
                "requested_camera_fps": config.camera_fps,
                "requested_camera_fourcc": config.camera_fourcc,
            }
        )
        return

    if args.track:
        from .detector import PersonTracker
        from .events import PeopleFlowAnalyzer
        from .output import CsvEventWriter
        from .badges import BadgeCounter
        from .preview import FpsMeter, PreviewServer, PreviewState, ShutdownController, annotate_frame

        preview_server: PreviewServer | None = None
        try:
            tracker = PersonTracker(
                config.model,
                imgsz=config.imgsz,
                conf=config.conf,
                iou=config.iou,
                device=config.device,
            )
            table = Table(title="Tracked people")
            table.add_column("frame", justify="right")
            table.add_column("track_id", justify="right")
            table.add_column("conf", justify="right")
            table.add_column("center", justify="right")
            table.add_column("bbox", justify="right")
            table.add_column("events")

            total_people = 0
            total_events = 0
            processed_frames = 0
            first_width = 0
            first_height = 0
            started_at = monotonic()
            fps_meter = FpsMeter()
            preview_state = PreviewState()
            if args.preview_server:
                badge_counter = BadgeCounter(config.badge_output)
                preview_server = PreviewServer(
                    host=config.preview_host,
                    port=config.preview_port,
                    state=preview_state,
                    badge_counter=badge_counter,
                    shutdown_controller=ShutdownController(
                        enabled=config.preview_shutdown_enabled,
                        command=config.preview_shutdown_command,
                    ),
                )
                preview_server.start()
                console.print(
                    {
                        "preview_url": f"http://{config.preview_host}:{config.preview_port}",
                        "stream_url": f"http://{config.preview_host}:{config.preview_port}/stream.mjpg",
                    }
                )
            analyzer = PeopleFlowAnalyzer(
                line_x_ratio=config.line_x_ratio,
                stop_speed_px_per_sec=config.stop_speed_px_per_sec,
                stop_duration_sec=config.stop_duration_sec,
            )
            with StreamCapture(str(config.stream_url), options=capture_options) as capture, CsvEventWriter(
                config.output
            ) as writer:
                max_frames = None if args.run_forever else config.max_frames
                for frame in capture.frames(max_frames=max_frames, frame_skip=config.frame_skip):
                    processed_frames += 1
                    if first_width == 0:
                        first_width = frame.width
                        first_height = frame.height
                    people = tracker.track_frame(frame)
                    events = analyzer.update(frame, people)
                    writer.write_events(events)
                    fps = fps_meter.tick()
                    if args.preview_server:
                        preview_state.update(
                            annotate_frame(
                                frame.image,
                                people,
                                events,
                                line_x_ratio=config.line_x_ratio,
                                fps=fps,
                                jpeg_quality=config.preview_jpeg_quality,
                            )
                        )
                    total_events += len(events)
                    event_labels = ", ".join(f"{event.track_id}:{event.direction}" for event in events)
                    total_people += len(people)
                    if args.no_table:
                        continue
                    if not people:
                        table.add_row(str(frame.index), "-", "-", "-", "-", event_labels or "-")
                        continue

                    for person in people:
                        table.add_row(
                            str(person.frame_index),
                            "-" if person.track_id is None else str(person.track_id),
                            f"{person.confidence:.2f}",
                            f"({person.center_x:.0f}, {person.center_y:.0f})",
                            (
                                f"({person.bbox.x1:.0f}, {person.bbox.y1:.0f}, "
                                f"{person.bbox.x2:.0f}, {person.bbox.y2:.0f})"
                            ),
                            event_labels or "-",
                        )
        except KeyboardInterrupt:
            console.print("[yellow]Stopped by user.[/yellow]")
        except StreamCaptureError as exc:
            console.print(f"[red]Tracking failed:[/red] {exc}")
            raise SystemExit(1) from exc
        finally:
            if preview_server is not None:
                preview_server.stop()

        elapsed_sec = monotonic() - started_at
        if not args.no_table:
            console.print(table)
        console.print(
            {
                "stream_url": str(config.stream_url),
                "model": config.model,
                "device": config.device,
                "processed_frames": processed_frames,
                "source_frame_span": max((processed_frames - 1) * config.frame_skip + 1, 0),
                "width": first_width,
                "height": first_height,
                "elapsed_sec": round(elapsed_sec, 3),
                "processing_fps": round(processed_frames / elapsed_sec, 2) if elapsed_sec > 0 else 0.0,
                "total_person_detections": total_people,
                "total_events": total_events,
                "imgsz": config.imgsz,
                "conf": config.conf,
                "iou": config.iou,
                "frame_skip": config.frame_skip,
                "requested_camera_width": config.camera_width,
                "requested_camera_height": config.camera_height,
                "requested_camera_fps": config.camera_fps,
                "requested_camera_fourcc": config.camera_fourcc,
                "preview_server": args.preview_server,
                "preview_host": config.preview_host,
                "preview_port": config.preview_port,
                "preview_shutdown_enabled": config.preview_shutdown_enabled,
                "output": str(config.output),
                "badge_output": str(config.badge_output),
            }
        )
        return

    console.print("Frame capture and YOLO tracking are ready. Run with --check-stream or --track.")
    console.print(config.model_dump())


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return f"{value:%Y-%m-%d %H:%M}"


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "-"
    return f"{value:%H:%M}"


def _format_badges(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _write_people_flow_summary(path: Path, summaries: object) -> None:
    fieldnames = [
        "start",
        "end",
        "left_to_right",
        "right_to_left",
        "stopped",
        "total_events",
        "unique_tracks",
        "peak_active_tracks",
    ]
    rows = [
        {
            "start": f"{summary.start:%Y-%m-%d %H:%M}",
            "end": f"{summary.end:%Y-%m-%d %H:%M}",
            "left_to_right": summary.left_to_right,
            "right_to_left": summary.right_to_left,
            "stopped": summary.stopped,
            "total_events": summary.total_events,
            "unique_tracks": summary.unique_tracks,
            "peak_active_tracks": summary.peak_active_tracks,
        }
        for summary in summaries
    ]
    _write_csv(path, fieldnames, rows)


def _write_daily_badge_summary(path: Path, summaries: object) -> None:
    fieldnames = [
        "date",
        "start",
        "end",
        "partial",
        "badges",
        "first_done",
        "last_done",
        "avg_hours",
    ]
    rows = [
        {
            "date": summary.day.isoformat(),
            "start": _format_time(summary.started_at),
            "end": _format_time(summary.ended_at),
            "partial": f"{summary.partial_progress:.2f}",
            "badges": _format_badges(summary.badges),
            "first_done": _format_time(summary.first_finished_at),
            "last_done": _format_time(summary.last_finished_at),
            "avg_hours": "" if summary.average_hours_per_badge is None else f"{summary.average_hours_per_badge:.2f}",
        }
        for summary in summaries
    ]
    _write_csv(path, fieldnames, rows)


def _write_weekly_badge_summary(path: Path, summaries: object) -> None:
    fieldnames = [
        "week",
        "badges",
        "first_done",
        "last_done",
        "avg_hours",
    ]
    rows = [
        {
            "week": f"{summary.week_start.isoformat()}..{summary.week_end.isoformat()}",
            "badges": _format_badges(summary.badges),
            "first_done": _format_datetime(summary.first_finished_at),
            "last_done": _format_datetime(summary.last_finished_at),
            "avg_hours": "" if summary.average_hours_per_badge is None else f"{summary.average_hours_per_badge:.2f}",
        }
        for summary in summaries
    ]
    _write_csv(path, fieldnames, rows)


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()

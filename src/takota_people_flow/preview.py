"""Browser MJPEG preview for tracked people."""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from threading import Condition, Thread
from time import monotonic
from urllib.parse import urlsplit

import cv2
import numpy as np

from .badges import BadgeCounter
from .events import FlowEvent
from .tracker import TrackedPerson


class PreviewState:
    def __init__(self) -> None:
        self._condition = Condition()
        self._jpeg: bytes | None = None
        self._sequence = 0

    def update(self, jpeg: bytes) -> None:
        with self._condition:
            self._jpeg = jpeg
            self._sequence += 1
            self._condition.notify_all()

    def wait_for_frame(self, last_sequence: int, *, timeout: float = 5.0) -> tuple[int, bytes | None]:
        with self._condition:
            if self._sequence == last_sequence:
                self._condition.wait(timeout=timeout)
            return self._sequence, self._jpeg


class PreviewServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        state: PreviewState | None = None,
        badge_counter: BadgeCounter | None = None,
        shutdown_controller: ShutdownController | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.state = state or PreviewState()
        self.badge_counter = badge_counter
        self.shutdown_controller = shutdown_controller
        self._server = ThreadingHTTPServer((host, port), self._handler_class())
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        state = self.state
        badge_counter = self.badge_counter
        shutdown_controller = self.shutdown_controller

        class PreviewHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                path = urlsplit(self.path).path
                if path in ("/", "/index.html"):
                    self._send_index()
                    return
                if path == "/stream.mjpg":
                    self._send_stream()
                    return
                if path == "/badges/status":
                    self._send_badge_status()
                    return
                if path == "/system/shutdown/status":
                    self._send_shutdown_status()
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                path = urlsplit(self.path).path
                content_length = int(self.headers.get("Content-Length", "0"))
                body = b""
                if content_length > 0:
                    body = self.rfile.read(content_length)
                if path == "/badges/consume":
                    self._consume_badge()
                    return
                if path == "/badges/start":
                    self._start_badge_day()
                    return
                if path == "/badges/end":
                    self._end_badge_day(body)
                    return
                if path == "/badges/undo":
                    self._undo_badge()
                    return
                if path == "/system/shutdown":
                    self._shutdown_system(body)
                    return
                self.send_error(HTTPStatus.NOT_FOUND)

            def log_message(self, format: str, *args: object) -> None:
                return

            def _send_index(self) -> None:
                body = """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>takota people flow preview</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: system-ui, sans-serif; }
    button, input { touch-action: manipulation; }
    dialog::backdrop { background: rgba(0, 0, 0, 0.65); }
    .safe-area-bottom { padding-bottom: max(1rem, env(safe-area-inset-bottom)); }
  </style>
</head>
<body class="min-h-screen bg-neutral-950 text-neutral-100">
  <header class="sticky top-0 z-10 border-b border-neutral-800 bg-neutral-950/95 px-3 py-3 shadow-lg backdrop-blur safe-area-bottom sm:px-4">
    <div class="mb-3 flex items-center justify-between gap-3">
      <div>
        <div class="text-sm font-semibold tracking-wide text-neutral-100">takota preview</div>
        <div class="text-xs text-neutral-400">people flow monitor</div>
      </div>
      <button id="openShutdown" class="hidden min-h-11 rounded-md border border-red-700 bg-red-800 px-4 text-sm font-bold text-white shadow-sm active:bg-red-900 disabled:opacity-50" type="button">電源</button>
    </div>

    <div class="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
      <div class="rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2">
        <div class="text-xs text-neutral-400">今日</div>
        <div><strong id="todayBadges" class="text-xl font-bold tabular-nums text-white">0</strong> <span class="text-neutral-300">バッジ</span></div>
      </div>
      <div class="rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2">
        <div class="text-xs text-neutral-400">累計</div>
        <div><strong id="totalBadges" class="text-xl font-bold tabular-nums text-white">0</strong> <span class="text-neutral-300">バッジ</span></div>
      </div>
      <div class="rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2">
        <div class="text-xs text-neutral-400">開始</div>
        <strong id="startedAt" class="text-lg font-bold tabular-nums text-white">未記録</strong>
      </div>
      <div class="rounded-md border border-neutral-800 bg-neutral-900 px-3 py-2">
        <div class="text-xs text-neutral-400">終了</div>
        <strong id="endedAt" class="text-lg font-bold tabular-nums text-white">未記録</strong>
      </div>
    </div>

    <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
      <label class="col-span-2 flex min-h-12 items-center justify-between gap-3 rounded-md border border-neutral-700 bg-neutral-900 px-3 text-sm font-semibold text-neutral-200 sm:col-span-1">
        <span>途中</span>
        <input id="partialProgress" class="h-9 w-20 rounded-md border border-neutral-600 bg-neutral-950 px-2 text-right text-base font-bold tabular-nums text-white" type="number" min="0" max="0.99" step="0.1" value="0">
      </label>
      <button id="startDay" class="min-h-12 rounded-md border border-neutral-600 bg-neutral-800 px-3 text-base font-bold text-white active:bg-neutral-700 disabled:opacity-50" type="button">営業開始</button>
      <button id="endDay" class="min-h-12 rounded-md border border-neutral-600 bg-neutral-800 px-3 text-base font-bold text-white active:bg-neutral-700 disabled:opacity-50" type="button">営業終了</button>
      <button id="consumeBadge" class="min-h-12 rounded-md border border-emerald-500 bg-emerald-600 px-3 text-base font-bold text-white active:bg-emerald-700 disabled:opacity-50" type="button">1バッジ</button>
      <button id="undoBadge" class="min-h-12 rounded-md border border-neutral-600 bg-neutral-800 px-3 text-base font-bold text-white active:bg-neutral-700 disabled:opacity-50" type="button">戻す</button>
    </div>
  </header>
  <dialog id="shutdownDialog" class="w-[calc(100vw-2rem)] max-w-sm rounded-lg border border-neutral-700 bg-neutral-900 p-0 text-neutral-100 shadow-2xl">
    <form method="dialog" class="p-4">
      <h2 class="text-lg font-bold">電源を切る</h2>
      <p class="mt-2 text-sm leading-6 text-neutral-300">入力欄に「電源を切る」と入力すると、この端末のシステムを終了します。</p>
      <input id="shutdownConfirm" class="mt-4 h-12 w-full rounded-md border border-neutral-600 bg-neutral-950 px-3 text-base font-semibold text-white" type="text" autocomplete="off" inputmode="text">
      <div class="mt-4 grid grid-cols-2 gap-2">
        <button id="cancelShutdown" class="min-h-12 rounded-md border border-neutral-600 bg-neutral-800 px-3 font-bold text-white active:bg-neutral-700" value="cancel" type="submit">キャンセル</button>
        <button id="confirmShutdown" class="min-h-12 rounded-md border border-red-700 bg-red-800 px-3 font-bold text-white active:bg-red-900 disabled:opacity-50" value="shutdown" type="button" disabled>電源を切る</button>
      </div>
    </form>
  </dialog>
  <main class="bg-black">
    <img class="block h-auto w-screen" src="/stream.mjpg" alt="Live preview">
  </main>
  <script>
    const shutdownPhrase = "電源を切る";
    const ids = {
      todayBadges: document.getElementById("todayBadges"),
      totalBadges: document.getElementById("totalBadges"),
      startedAt: document.getElementById("startedAt"),
      endedAt: document.getElementById("endedAt"),
      partialProgress: document.getElementById("partialProgress"),
      startDay: document.getElementById("startDay"),
      endDay: document.getElementById("endDay"),
      consumeBadge: document.getElementById("consumeBadge"),
      undoBadge: document.getElementById("undoBadge"),
      openShutdown: document.getElementById("openShutdown"),
      shutdownDialog: document.getElementById("shutdownDialog"),
      shutdownConfirm: document.getElementById("shutdownConfirm"),
      confirmShutdown: document.getElementById("confirmShutdown"),
    };

    function updateStatus(status) {
      ids.todayBadges.textContent = status.today_badges;
      ids.totalBadges.textContent = status.total_badges;
      ids.startedAt.textContent = status.today_started_at ? status.today_started_at.slice(11, 16) : "未記録";
      ids.endedAt.textContent = status.today_ended_at ? status.today_ended_at.slice(11, 16) : "未記録";
      ids.partialProgress.value = status.carryover_progress ?? 0;
      ids.consumeBadge.textContent = "1バッジ";
      ids.undoBadge.disabled = status.total_badges <= 0;
    }

    async function fetchStatus() {
      const response = await fetch("/badges/status", { cache: "no-store" });
      if (response.ok) updateStatus(await response.json());
    }

    async function fetchShutdownStatus() {
      const response = await fetch("/system/shutdown/status", { cache: "no-store" });
      if (!response.ok) return;
      const status = await response.json();
      ids.openShutdown.classList.toggle("hidden", !status.enabled);
    }

    async function postBadge(path) {
      ids.consumeBadge.disabled = true;
      ids.startDay.disabled = true;
      ids.endDay.disabled = true;
      ids.undoBadge.disabled = true;
      try {
        const options = { method: "POST" };
        if (path === "/badges/end") {
          const partial = Math.min(Math.max(Number(ids.partialProgress.value || 0), 0), 0.99);
          options.headers = { "Content-Type": "application/json" };
          options.body = JSON.stringify({ partial_progress: partial });
        }
        const response = await fetch(path, options);
        if (response.ok) updateStatus(await response.json());
      } finally {
        ids.consumeBadge.disabled = false;
        ids.startDay.disabled = false;
        ids.endDay.disabled = false;
      }
    }

    ids.startDay.addEventListener("click", () => postBadge("/badges/start"));
    ids.endDay.addEventListener("click", () => postBadge("/badges/end"));
    ids.consumeBadge.addEventListener("click", () => postBadge("/badges/consume"));
    ids.undoBadge.addEventListener("click", () => postBadge("/badges/undo"));
    ids.openShutdown.addEventListener("click", () => {
      ids.shutdownConfirm.value = "";
      ids.confirmShutdown.disabled = true;
      ids.shutdownDialog.showModal();
      ids.shutdownConfirm.focus();
    });
    ids.shutdownConfirm.addEventListener("input", () => {
      ids.confirmShutdown.disabled = ids.shutdownConfirm.value !== shutdownPhrase;
    });
    ids.confirmShutdown.addEventListener("click", async () => {
      ids.confirmShutdown.disabled = true;
      const response = await fetch("/system/shutdown", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: shutdownPhrase }),
      });
      if (response.ok) {
        ids.shutdownDialog.close();
        ids.openShutdown.disabled = true;
        ids.openShutdown.textContent = "終了中";
      } else {
        ids.confirmShutdown.disabled = false;
      }
    });
    fetchStatus();
    fetchShutdownStatus();
    setInterval(fetchStatus, 30000);
  </script>
</body>
</html>
""".encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_stream(self) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Age", "0")
                self.send_header("Cache-Control", "no-cache, private")
                self.send_header("Pragma", "no-cache")
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.end_headers()

                sequence = 0
                while True:
                    sequence, jpeg = state.wait_for_frame(sequence)
                    if jpeg is None:
                        continue
                    try:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                    except (BrokenPipeError, ConnectionResetError):
                        break

            def _send_badge_status(self) -> None:
                if badge_counter is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json(asdict(badge_counter.status()))

            def _send_shutdown_status(self) -> None:
                self._send_json({"enabled": shutdown_controller is not None and shutdown_controller.enabled})

            def _consume_badge(self) -> None:
                if badge_counter is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json(asdict(badge_counter.consume()))

            def _start_badge_day(self) -> None:
                if badge_counter is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json(asdict(badge_counter.start_day()))

            def _end_badge_day(self, body: bytes) -> None:
                if badge_counter is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                partial_progress = 0.0
                if body:
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        partial_progress = float(payload.get("partial_progress", 0.0))
                    except (ValueError, TypeError, json.JSONDecodeError):
                        partial_progress = 0.0
                self._send_json(asdict(badge_counter.end_day(partial_progress=partial_progress)))

            def _undo_badge(self) -> None:
                if badge_counter is None:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_json(asdict(badge_counter.undo()))

            def _shutdown_system(self, body: bytes) -> None:
                if shutdown_controller is None or not shutdown_controller.enabled:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if not _is_private_client(self.client_address[0]):
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                confirm = ""
                if body:
                    try:
                        payload = json.loads(body.decode("utf-8"))
                        confirm = str(payload.get("confirm", ""))
                    except (TypeError, json.JSONDecodeError):
                        confirm = ""
                if confirm != shutdown_controller.confirm_phrase:
                    self.send_error(HTTPStatus.BAD_REQUEST)
                    return
                shutdown_controller.request_shutdown()
                self._send_json({"status": "shutdown_requested"})

            def _send_json(self, payload: dict[str, object]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return PreviewHandler


class ShutdownController:
    confirm_phrase = "電源を切る"

    def __init__(self, *, enabled: bool = False, command: str = "") -> None:
        self._enabled = enabled
        self.command = shlex.split(command) if command else []

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self.command)

    def request_shutdown(self) -> None:
        if not self.enabled:
            raise RuntimeError("Shutdown command is not configured.")
        Thread(target=self._run_shutdown, daemon=True).start()

    def _run_shutdown(self) -> None:
        subprocess.Popen(self.command, start_new_session=True)


def _is_private_client(host: str) -> bool:
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


class FpsMeter:
    def __init__(self, *, smoothing: float = 0.9) -> None:
        self.smoothing = smoothing
        self._last_time: float | None = None
        self.value = 0.0

    def tick(self) -> float:
        now = monotonic()
        if self._last_time is None:
            self._last_time = now
            return self.value
        elapsed = max(now - self._last_time, 0.001)
        current = 1.0 / elapsed
        self.value = current if self.value == 0 else self.value * self.smoothing + current * (1 - self.smoothing)
        self._last_time = now
        return self.value


def annotate_frame(
    image: np.ndarray,
    people: list[TrackedPerson],
    events: list[FlowEvent],
    *,
    line_x_ratio: float,
    fps: float,
    jpeg_quality: int = 80,
) -> bytes:
    annotated = image.copy()
    height, width = annotated.shape[:2]
    line_x = int(width * line_x_ratio)

    cv2.line(annotated, (line_x, 0), (line_x, height), (0, 220, 255), 2)
    cv2.putText(
        annotated,
        f"FPS {fps:.1f}  active {len([p for p in people if p.track_id is not None])}",
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    for person in people:
        x1, y1, x2, y2 = [int(value) for value in (person.bbox.x1, person.bbox.y1, person.bbox.x2, person.bbox.y2)]
        label = f"id {person.track_id}" if person.track_id is not None else "person"
        label = f"{label} {person.confidence:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (50, 220, 80), 2)
        cv2.circle(annotated, (int(person.center_x), int(person.center_y)), 4, (50, 220, 80), -1)
        cv2.putText(
            annotated,
            label,
            (x1, max(y1 - 8, 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (50, 220, 80),
            2,
            cv2.LINE_AA,
        )

    y = 58
    for event in events[-3:]:
        cv2.putText(
            annotated,
            f"{event.track_id}: {event.direction}",
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 220, 255),
            2,
            cv2.LINE_AA,
        )
        y += 26

    ok, encoded = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise RuntimeError("Could not encode preview frame as JPEG.")
    return encoded.tobytes()

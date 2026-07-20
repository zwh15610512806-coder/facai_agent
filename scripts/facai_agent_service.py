from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
PID_FILE = LOG_DIR / "facai-agent-server.pid"
WORKER_PID_FILE = LOG_DIR / "facai-agent-integration-worker.pid"
WORKER_ENABLED_ENV = "FACAI_INTEGRATION_WORKER_ENABLED"
MAX_WORKER_RESTART_BACKOFF_SECONDS = 60.0
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.runtime_environment import load_project_environment  # noqa: E402

load_project_environment(ROOT)

from scripts.verify_runtime import assert_verified_runtime  # noqa: E402
from services.runtime_logging import configure_runtime_logging  # noqa: E402

configure_runtime_logging(LOG_DIR / "facai-agent-watchdog.log")
LOGGER = logging.getLogger("facai.watchdog")


def log(message: str) -> None:
    LOGGER.info(message)


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=8) as response:
            return response.status == 200
    except Exception:
        return False


def port_available(port: int) -> bool:
    """Check availability without terminating the current port owner."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _record_managed_pid(pid: int) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    temp_path = PID_FILE.with_suffix(".pid.tmp")
    temp_path.write_text(str(pid), encoding="ascii")
    temp_path.replace(PID_FILE)


def _recorded_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="ascii").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _clear_managed_pid(pid: int) -> None:
    if _recorded_pid() != pid:
        return
    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _record_worker_pid(pid: int) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    temp_path = WORKER_PID_FILE.with_suffix(".pid.tmp")
    temp_path.write_text(str(pid), encoding="ascii")
    temp_path.replace(WORKER_PID_FILE)


def _recorded_worker_pid() -> int | None:
    try:
        return int(WORKER_PID_FILE.read_text(encoding="ascii").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _clear_worker_pid(pid: int) -> None:
    if _recorded_worker_pid() != pid:
        return
    try:
        WORKER_PID_FILE.unlink()
    except FileNotFoundError:
        pass


def start_server(port: int) -> subprocess.Popen:
    LOG_DIR.mkdir(exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "facai_server.py"),
        "--port",
        str(port),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    _record_managed_pid(process.pid)
    log(f"Started server process {process.pid} on port {port}")
    return process


def stop_managed_process(process: subprocess.Popen | None) -> None:
    """Stop only the exact child PID created and recorded by this monitor."""
    if process is None or process.poll() is not None:
        return
    if _recorded_pid() != process.pid:
        log(f"Refusing to stop unrecorded process {process.pid}")
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    finally:
        _clear_managed_pid(process.pid)


def integration_worker_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Fail closed unless the optional worker is explicitly enabled with ``1``."""

    values = os.environ if environ is None else environ
    raw = values.get(WORKER_ENABLED_ENV)
    if raw is None or raw == "0":
        return False
    if raw == "1":
        return True
    raise ValueError(f"{WORKER_ENABLED_ENV} must be exactly 0 or 1")


def start_integration_worker() -> subprocess.Popen:
    LOG_DIR.mkdir(exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "scripts" / "integration_worker.py"),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    try:
        _record_worker_pid(process.pid)
    except OSError:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        raise
    log(f"Started integration worker process {process.pid}")
    return process


def stop_integration_worker(process: subprocess.Popen | None) -> None:
    """Stop only the worker child recorded by this supervisor."""

    if process is None or process.poll() is not None:
        return
    if _recorded_worker_pid() != process.pid:
        log(f"Refusing to stop unrecorded integration worker {process.pid}")
        return
    process.terminate()
    try:
        process.wait(timeout=35)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    finally:
        _clear_worker_pid(process.pid)


class WorkerSupervisorState:
    __slots__ = ("process", "restart_attempts", "next_restart_at")

    def __init__(
        self,
        process: subprocess.Popen | None = None,
        restart_attempts: int = 0,
        next_restart_at: float = 0.0,
    ) -> None:
        self.process = process
        self.restart_attempts = restart_attempts
        self.next_restart_at = next_restart_at


def supervise_worker_once(
    state: WorkerSupervisorState,
    *,
    enabled: bool,
    now: float | None = None,
) -> tuple[WorkerSupervisorState, str]:
    """Supervise the optional worker independently from Uvicorn health."""

    if not isinstance(state, WorkerSupervisorState):
        raise TypeError("state must be WorkerSupervisorState")
    selected_now = time.monotonic() if now is None else float(now)
    if not enabled:
        stop_integration_worker(state.process)
        return WorkerSupervisorState(), "disabled"
    if state.process is not None and state.process.poll() is None:
        return WorkerSupervisorState(process=state.process), "running"
    if state.process is not None:
        _clear_worker_pid(state.process.pid)
        attempts = min(state.restart_attempts + 1, 64)
        delay = min(
            MAX_WORKER_RESTART_BACKOFF_SECONDS,
            float(2 ** min(attempts - 1, 6)),
        )
        log(
            "Integration worker exited; scheduling a bounded restart "
            f"in {int(delay)} seconds"
        )
        return (
            WorkerSupervisorState(
                process=None,
                restart_attempts=attempts,
                next_restart_at=selected_now + delay,
            ),
            "backoff",
        )
    if selected_now < state.next_restart_at:
        return state, "backoff"
    try:
        process = start_integration_worker()
    except OSError:
        attempts = min(state.restart_attempts + 1, 64)
        delay = min(
            MAX_WORKER_RESTART_BACKOFF_SECONDS,
            float(2 ** min(attempts - 1, 6)),
        )
        LOGGER.error(
            "Integration worker start failed; scheduling a bounded restart"
        )
        return (
            WorkerSupervisorState(
                process=None,
                restart_attempts=attempts,
                next_restart_at=selected_now + delay,
            ),
            "backoff",
        )
    return (
        WorkerSupervisorState(
            process=process,
            restart_attempts=state.restart_attempts,
        ),
        "started",
    )


def supervise_once(process: subprocess.Popen | None, port: int) -> tuple[subprocess.Popen | None, str]:
    process_running = process is not None and process.poll() is None
    if process_running:
        if healthy(port):
            return process, "managed-healthy"
        log(f"Managed process {process.pid} failed health check; restarting it")
        stop_managed_process(process)
        process = None
        time.sleep(1)

    if healthy(port):
        return None, "external-healthy"
    if not port_available(port):
        return None, "port-occupied"
    return start_server(port), "started"


def main() -> int:
    assert_verified_runtime()
    log(f"Verified isolated runtime: {sys.executable}")
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()

    log(f"Service monitor started for {ROOT} on port {args.port}")

    process: subprocess.Popen | None = None
    worker_state = WorkerSupervisorState()
    previous_state = ""
    previous_worker_state = ""
    try:
        while True:
            process, state = supervise_once(process, args.port)
            if state != previous_state:
                if state == "port-occupied":
                    log(f"Port {args.port} is occupied by an unmanaged process; waiting without terminating it")
                elif state == "external-healthy":
                    log(f"Port {args.port} already serves a healthy unmanaged process; monitoring without taking ownership")
                previous_state = state
            try:
                worker_is_enabled = integration_worker_enabled()
            except ValueError:
                worker_is_enabled = False
                worker_state, _ = supervise_worker_once(
                    worker_state,
                    enabled=False,
                )
                worker_status = "invalid-config"
            else:
                worker_state, worker_status = supervise_worker_once(
                    worker_state,
                    enabled=worker_is_enabled,
                )
            if worker_status != previous_worker_state:
                if worker_status == "invalid-config":
                    log(
                        f"{WORKER_ENABLED_ENV} is invalid; integration worker remains disabled"
                    )
                previous_worker_state = worker_status
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log("Service monitor stopping")
    finally:
        stop_managed_process(process)
        stop_integration_worker(worker_state.process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import logging
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
PID_FILE = LOG_DIR / "facai-agent-server.pid"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.security import assert_startup_security
from services.runtime_logging import configure_runtime_logging


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


def start_server(port: int) -> subprocess.Popen:
    bind_host = "0.0.0.0"
    assert_startup_security(bind_host)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()

    log(f"Service monitor started for {ROOT} on port {args.port}")

    process: subprocess.Popen | None = None
    previous_state = ""
    try:
        while True:
            process, state = supervise_once(process, args.port)
            if state != previous_state:
                if state == "port-occupied":
                    log(f"Port {args.port} is occupied by an unmanaged process; waiting without terminating it")
                elif state == "external-healthy":
                    log(f"Port {args.port} already serves a healthy unmanaged process; monitoring without taking ownership")
                previous_state = state
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log("Service monitor stopping")
    finally:
        stop_managed_process(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

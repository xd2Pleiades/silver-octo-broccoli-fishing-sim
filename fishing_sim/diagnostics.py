"""Persistent runtime diagnostics for the Fishing Simulator.

The game writes Python errors and crash context to ``<project>/cache/errors``.
The directory is created automatically on launch. Logs rotate so a long session
cannot consume unbounded disk space. ``faulthandler`` also records native faults
such as segmentation faults when Python can still write the diagnostic file.
"""
from __future__ import annotations

import datetime as _dt
import faulthandler
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
import traceback
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ERROR_DIR = PROJECT_ROOT / "cache" / "errors"

_LOGGER = logging.getLogger("fishing_sim.diagnostics")
_INSTALLED = False
_INSTALLED_DIR: Path | None = None
_FAULT_STREAM = None
_ACTIVE_CONTEXT: dict[str, Any] = {}
_CONTEXT_LOCK = threading.Lock()


def _jsonable(value: Any, limit: int = 240) -> Any:
    """Convert state into compact, safe-to-serialize diagnostic values."""
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > limit:
            return value[:limit] + "…"
        return value
    if hasattr(value, "x") and hasattr(value, "y"):
        try:
            return {"x": round(float(value.x), 3), "y": round(float(value.y), 3)}
        except (TypeError, ValueError, OverflowError):
            pass
    if isinstance(value, dict):
        return {str(k): _jsonable(v, limit) for k, v in list(value.items())[:80]}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(v, limit) for v in list(value)[:80]]
    return repr(value)[:limit]


def _ensure_directory() -> Path:
    """Create the project cache, falling back to a user-writable cache if needed."""
    global ERROR_DIR
    try:
        ERROR_DIR.mkdir(parents=True, exist_ok=True)
        return ERROR_DIR
    except OSError:
        local_app_data = os.environ.get("LOCALAPPDATA")
        fallback_root = Path(local_app_data) if local_app_data else Path.home() / ".cache"
        fallback = fallback_root / "FishingSimulator" / "errors"
        fallback.mkdir(parents=True, exist_ok=True)
        ERROR_DIR = fallback
        return ERROR_DIR


def install_diagnostics(error_dir: str | os.PathLike[str] | None = None) -> Path:
    """Configure logs, exception hooks, and faulthandler. Safe to call repeatedly."""
    global _INSTALLED, _INSTALLED_DIR, _FAULT_STREAM, ERROR_DIR
    if error_dir is not None:
        requested_dir = Path(error_dir).expanduser().resolve()
    else:
        requested_dir = ERROR_DIR.resolve()

    if _INSTALLED and _INSTALLED_DIR == requested_dir:
        requested_dir.mkdir(parents=True, exist_ok=True)
        return requested_dir

    ERROR_DIR = requested_dir
    ERROR_DIR = _ensure_directory()
    requested_dir = ERROR_DIR.resolve()
    _LOGGER.setLevel(logging.DEBUG)
    _LOGGER.propagate = False

    # Remove only handlers installed by this module, closing stale handles when
    # tests or launchers explicitly choose a different diagnostic directory.
    for handler in list(_LOGGER.handlers):
        if getattr(handler, "_fishing_sim_diagnostic_handler", False):
            _LOGGER.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(levelname)s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    runtime_handler = RotatingFileHandler(
        ERROR_DIR / "runtime.log", maxBytes=2_000_000, backupCount=4, encoding="utf-8"
    )
    runtime_handler.setLevel(logging.INFO)
    runtime_handler.setFormatter(formatter)
    runtime_handler._fishing_sim_diagnostic_handler = True  # type: ignore[attr-defined]
    _LOGGER.addHandler(runtime_handler)

    errors_handler = RotatingFileHandler(
        ERROR_DIR / "errors.log", maxBytes=2_000_000, backupCount=6, encoding="utf-8"
    )
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(formatter)
    errors_handler._fishing_sim_diagnostic_handler = True  # type: ignore[attr-defined]
    _LOGGER.addHandler(errors_handler)

    # A raw file is retained for faulthandler; its API writes directly to a file
    # descriptor and may operate when ordinary Python exception handling cannot.
    if _FAULT_STREAM is not None:
        try:
            _FAULT_STREAM.close()
        except Exception:
            pass
        _FAULT_STREAM = None
    _FAULT_STREAM = open(ERROR_DIR / "faults.log", "a", encoding="utf-8", buffering=1)
    try:
        faulthandler.enable(file=_FAULT_STREAM, all_threads=True)
    except (RuntimeError, OSError, ValueError) as exc:
        _LOGGER.warning("Could not enable faulthandler: %s", exc)

    if not getattr(sys.excepthook, "_fishing_sim_hook", False):
        previous_hook = sys.excepthook

        def _top_level_hook(exc_type, exc_value, exc_tb):
            path = write_exception_report(
                "Uncaught top-level exception",
                exc_info=(exc_type, exc_value, exc_tb),
                context=active_context(),
            )
            try:
                previous_hook(exc_type, exc_value, exc_tb)
            finally:
                if path:
                    try:
                        sys.__stderr__.write("\nFishing Simulator diagnostic report: %s\n" % path)
                        sys.__stderr__.flush()
                    except Exception:
                        pass

        _top_level_hook._fishing_sim_hook = True  # type: ignore[attr-defined]
        sys.excepthook = _top_level_hook

    if hasattr(threading, "excepthook") and not getattr(threading.excepthook, "_fishing_sim_hook", False):
        previous_thread_hook = threading.excepthook

        def _thread_hook(args):
            write_exception_report(
                "Uncaught exception in worker thread %s" % getattr(args.thread, "name", "unknown"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                context=active_context(),
            )
            previous_thread_hook(args)

        _thread_hook._fishing_sim_hook = True  # type: ignore[attr-defined]
        threading.excepthook = _thread_hook

    if not getattr(sys, "unraisablehook", None) is None and not getattr(sys.unraisablehook, "_fishing_sim_hook", False):
        previous_unraisable_hook = sys.unraisablehook

        def _unraisable_hook(args):
            write_exception_report(
                "Unraisable exception in %s" % (getattr(args, "object", "unknown object"),),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
                context=active_context(),
            )
            previous_unraisable_hook(args)

        _unraisable_hook._fishing_sim_hook = True  # type: ignore[attr-defined]
        sys.unraisablehook = _unraisable_hook

    _INSTALLED = True
    _INSTALLED_DIR = requested_dir
    _LOGGER.info("Diagnostics started; error directory=%s; pid=%s", ERROR_DIR, os.getpid())
    return ERROR_DIR


def get_logger() -> logging.Logger:
    return _LOGGER


def set_active_context(context: dict[str, Any] | None = None) -> None:
    """Record the last input/frame phase so a later crash has useful context."""
    with _CONTEXT_LOCK:
        if context:
            _ACTIVE_CONTEXT.update(_jsonable(context))


def active_context() -> dict[str, Any]:
    with _CONTEXT_LOCK:
        return dict(_ACTIVE_CONTEXT)


def log_event(event: str, context: dict[str, Any] | None = None, level: int = logging.INFO) -> None:
    """Write a small structured event into runtime.log (and context into crash snapshots)."""
    details = _jsonable(context or {})
    set_active_context({"last_game_event": event, "last_game_event_details": details})
    _LOGGER.log(level, "EVENT %s %s", event, json.dumps(details, sort_keys=True, ensure_ascii=False))


def game_context_snapshot(game: Any, frame_no: int | None = None, last_event: str | None = None) -> dict[str, Any]:
    """Collect a compact snapshot without allowing diagnostics to throw its own error."""
    ctx: dict[str, Any] = active_context()
    if frame_no is not None:
        ctx["frame"] = frame_no
    if last_event is not None:
        ctx["last_input_event"] = last_event
    try:
        world = getattr(game, "world", None)
        line = getattr(game, "line", None)
        ship = getattr(game, "ship", None)
        if world is not None:
            pos = getattr(world, "ship_pos", None)
            ctx["world"] = {
                "time": round(float(getattr(world, "time", 0.0)), 3),
                "ship_pos": _jsonable(pos),
                "speed": round(float(getattr(world, "speed", 0.0)), 3),
                "heading": round(float(getattr(world, "heading", 0.0)), 5),
                "distance_from_harbour": round(float(world.dist()), 3) if callable(getattr(world, "dist", None)) else None,
                "destination": _jsonable(getattr(world, "destination", None)),
                "route_waypoints": len(getattr(world, "route_waypoints", []) or []),
            }
        if line is not None:
            ctx["longline"] = {
                "phase": getattr(line, "phase", None),
                "stage": getattr(line, "stage", None),
                "auto": getattr(line, "auto", None),
                "point_count": len(getattr(line, "pts", []) or []),
                "max_points": getattr(line, "max_points", None),
                "spacing": getattr(line, "spacing", None),
                "slack": getattr(line, "slack", None),
                "stern_power": line.power("stern") if callable(getattr(line, "power", None)) else None,
            }
        if ship is not None:
            ctx["ship_state"] = {
                "engine_ok": getattr(ship, "engine_ok", None),
                "engine_power": getattr(ship, "engine_power", None),
                "engine_flood": getattr(ship, "engine_flood", None),
                "hold_flood": getattr(ship, "hold_flood", None),
                "hatch_states": _jsonable(getattr(ship, "hatch_states", {})),
            }
    except Exception as context_exc:
        ctx["context_snapshot_error"] = repr(context_exc)
    return _jsonable(ctx)


def write_exception_report(
    title: str,
    *,
    exc_info=None,
    context: dict[str, Any] | None = None,
) -> str | None:
    """Save a unique crash report and write the traceback to errors.log/runtime.log."""
    if exc_info is None:
        exc_info = sys.exc_info()
    exc_type, exc_value, exc_tb = exc_info
    stamp = _dt.datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%f")
    report_path: Path | None = None
    try:
        directory = _ensure_directory()
        report_path = directory / ("crash_%s_pid%s.txt" % (stamp, os.getpid()))
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        snapshot = _jsonable(context if context is not None else active_context())
        with report_path.open("w", encoding="utf-8") as file:
            file.write("Fishing Simulator crash report\n")
            file.write("Generated: %s\n" % _dt.datetime.now().astimezone().isoformat())
            file.write("Title: %s\n" % title)
            file.write("Process ID: %s\n" % os.getpid())
            file.write("\n--- Context ---\n")
            file.write(json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False, default=repr))
            file.write("\n\n--- Traceback ---\n")
            file.write(tb_text or "No Python traceback was available (possible native/process-level fault).\n")
        _LOGGER.error("%s; report=%s; context=%s", title, report_path, json.dumps(snapshot, sort_keys=True, ensure_ascii=False),
                      exc_info=exc_info if exc_type is not None else None)
        return str(report_path)
    except Exception as logging_exc:
        # Never let a failure in the diagnostic writer hide the original exception.
        try:
            sys.__stderr__.write("Could not save Fishing Simulator crash report: %r\n" % (logging_exc,))
            if exc_type is not None:
                traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.__stderr__)
            sys.__stderr__.flush()
        except Exception:
            pass
        return str(report_path) if report_path else None

import json
import os
import sys
import tempfile
import time
from pathlib import Path


def _load_startup_settings(profile_name=None):
    """Load the selected profile before Qt WebEngine initializes."""
    from ui.settings import Settings

    settings = Settings()
    settings.load_profile_settings()
    if profile_name not in settings.profiles_list:
        profile_name = "Guest"
    if settings.profiles_list and profile_name not in settings.profiles_list:
        profile_name = settings.profiles_list[0]
    settings.load(profile_name)
    Settings.configure_hardware_acceleration(settings.hardware_acceleration)
    Settings.configure_webgpu(settings.webgpu_enabled)
    return settings



def _normalize_application_font(app):
    """Ensure Qt's application font has a usable point size on every platform."""
    from PySide6.QtGui import QFont

    app_font = QFont(app.font())
    if app_font.pointSize() <= 0:
        app_font.setPointSize(10)
        app.setFont(app_font)
    return app_font


def _wait_for_parent_exit(pid: int, timeout: float = 60.0) -> bool:
    """Wait before opening a profile directory still owned by the old process."""
    if pid <= 0:
        return False
    deadline = time.monotonic() + timeout
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        wait_for_single_object.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL

        handle = open_process(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: process exited
        try:
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            return wait_for_single_object(handle, remaining_ms) == 0
        finally:
            close_handle(handle)

    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass
        time.sleep(0.1)
    return False


def _consume_session(path):
    if not path:
        return None
    candidate = Path(path).resolve()
    temp_directory = Path(tempfile.gettempdir()).resolve()
    if candidate.parent != temp_directory or not candidate.name.startswith("arma-network-switch-") or candidate.suffix != ".json":
        return None
    try:
        with candidate.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    finally:
        try:
            candidate.unlink()
        except OSError:
            pass


def _runtime_arguments(arguments):
    """Remove internal handoff flags before passing arguments to Qt."""
    tor_mode = "--tor-mode" in arguments
    resume_path = None
    parent_pid = None
    qt_arguments = []
    for argument in arguments:
        if argument == "--tor-mode":
            continue
        if argument.startswith("--resume-session="):
            resume_path = argument.split("=", 1)[1]
            continue
        if argument.startswith("--wait-for-parent="):
            try:
                parent_pid = int(argument.split("=", 1)[1])
            except ValueError:
                parent_pid = -1
            continue
        qt_arguments.append(argument)
    return qt_arguments, tor_mode, resume_path, parent_pid


if __name__ == "__main__":
    # A one-file executable extracts bundled resources to a temporary directory.
    # Mutable settings, profiles, browser storage, and proxy state must instead live
    # in a stable, writable per-user folder.
    if getattr(sys, "frozen", False):
        from app_paths import app_data_dir

        os.chdir(app_data_dir())

    qt_arguments, tor_mode, resume_path, parent_pid = _runtime_arguments(sys.argv[1:])
    if parent_pid is not None and not _wait_for_parent_exit(parent_pid):
        raise SystemExit("ARMA Browser could not safely reopen its profile after switching network mode.")
    restored_session = _consume_session(resume_path)
    selected_profile = restored_session.get("profile") if restored_session else None
    _load_startup_settings(selected_profile)

    # Register the internal origin before importing BrowserWindow or creating profiles.
    from ui.dashboard.internal_page import register_dashboard_scheme
    register_dashboard_scheme()

    # No Tor proxy is configured for an ordinary browser session.
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ui.browser_window import BrowserWindow

    app = QApplication([sys.argv[0], *qt_arguments])
    _normalize_application_font(app)
    app.setApplicationName("ARMA Browser")
    app.setApplicationDisplayName("ARMA Browser")
    try:
        window = BrowserWindow(tor_mode=tor_mode, restored_session=restored_session)
    except Exception as exc:
        QMessageBox.critical(None, "ARMA Browser", f"Could not initialize the requested network mode: {exc}")
        sys.exit(1)
    app.aboutToQuit.connect(window.prepare_shutdown)
    window.showMaximized()
    sys.exit(app.exec())

import os
import socket
import sys


def _reserve_proxy_port() -> int:
    """Choose the loopback port before Qt WebEngine reads Chromium flags."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _configure_chromium_proxy(port: int) -> None:
    """Set Chromium's proxy before QApplication/QtWebEngine initialization."""
    existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    flags = []
    skip_next = False
    for flag in existing:
        if skip_next:
            skip_next = False
            continue
        if flag == "--proxy-server":
            skip_next = True
            continue
        if flag.startswith("--proxy-server="):
            continue
        # Hardware acceleration must not be disabled by disabling Chromium's
        # sandbox or its software renderer. These were emitted by old settings.
        if flag in ("--no-sandbox", "--disable-software-rasterizer"):
            continue
        flags.append(flag)
    flags.append(f"--proxy-server=http://127.0.0.1:{port}")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)
    os.environ.pop("QTWEBENGINE_DISABLE_SANDBOX", None)


if __name__ == "__main__":
    proxy_port = _reserve_proxy_port()
    _configure_chromium_proxy(proxy_port)

    # Import Qt WebEngine only after its Chromium startup flags are ready.
    from PySide6.QtWidgets import QApplication
    from ui.browser_window import BrowserWindow

    app = QApplication(sys.argv)
    window = BrowserWindow(proxy_port=proxy_port)
    window.showMaximized()
    sys.exit(app.exec())

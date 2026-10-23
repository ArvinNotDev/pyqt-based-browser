"""Qt WebEngine plumbing for the reloadable, app-owned dashboard origin."""

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtWebEngineCore import (
    QWebEngineUrlRequestJob,
    QWebEngineUrlScheme,
    QWebEngineUrlSchemeHandler,
)


DASHBOARD_SCHEME = b"arma"
DASHBOARD_URL = "arma://dashboard/"
DASHBOARD_DEFAULT_PORT = 443
INTERNAL_PAGE_HOSTS = frozenset({"dashboard", "settings", "history", "downloads"})
_scheme_registered = False


def register_dashboard_scheme() -> None:
    """Register ARMA's secure local origin once, before any WebEngine profile exists."""
    global _scheme_registered
    if _scheme_registered:
        return

    scheme = QWebEngineUrlScheme(DASHBOARD_SCHEME)
    scheme.setSyntax(QWebEngineUrlScheme.Syntax.HostAndPort)
    # HostAndPort schemes require a concrete default port in Chromium. A negative
    # value causes registration to be rejected and handler-installation warnings.
    scheme.setDefaultPort(DASHBOARD_DEFAULT_PORT)
    scheme.setFlags(
        QWebEngineUrlScheme.Flag.SecureScheme
        | QWebEngineUrlScheme.Flag.LocalScheme
    )
    QWebEngineUrlScheme.registerScheme(scheme)
    _scheme_registered = True


class DashboardSchemeHandler(QWebEngineUrlSchemeHandler):
    """Serve the dashboard document and validated managed wallpaper assets."""

    def __init__(self, browser, parent=None):
        super().__init__(parent)
        self.browser = browser
        self._buffers: set[QBuffer] = set()

    def _reply(self, job: QWebEngineUrlRequestJob, mime: bytes, content: bytes) -> None:
        buffer = QBuffer(job)
        buffer.setData(QByteArray(content))
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._buffers.add(buffer)
        buffer.destroyed.connect(lambda _obj=None, item=buffer: self._buffers.discard(item))
        job.reply(mime, buffer)

    def requestStarted(self, job: QWebEngineUrlRequestJob) -> None:
        request = job.requestUrl()
        host = request.host().lower()
        if host not in INTERNAL_PAGE_HOSTS:
            job.fail(QWebEngineUrlRequestJob.Error.RequestDenied)
            return
        path = request.path()
        if path in {"", "/", "/index.html"}:
            try:
                if host == "dashboard":
                    document = self.browser._dashboard_document()
                else:
                    document = self.browser._internal_page_document(host)
                self._reply(job, b"text/html; charset=utf-8", document)
            except (OSError, RuntimeError, ValueError):
                job.fail(QWebEngineUrlRequestJob.Error.RequestFailed)
            return
        if host == "dashboard" and path.startswith("/wallpaper/"):
            filename = path.rsplit("/", 1)[-1]
            manager = getattr(self.browser, "dashboard_manager", None)
            content = manager.read_wallpaper(filename) if manager is not None else None
            if content:
                self._reply(job, b"image/jpeg", content)
            else:
                job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)
            return
        job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)


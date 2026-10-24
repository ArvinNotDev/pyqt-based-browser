"""High-value browser features layered onto ARMA Browser's existing Qt WebEngine UI.

This module deliberately keeps the main BrowserWindow implementation small by
installing focused hooks at startup. It uses the existing profile/settings and
tab lifecycle rather than creating a second browsing stack.
"""

from __future__ import annotations

import json
import logging
import os
import re
import weakref
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView

logger = logging.getLogger(__name__)

# Domain rules are intentionally conservative and easy to inspect. The user can
# disable the interceptor per profile if a site relies on a blocked resource.
BLOCKED_HOSTS = frozenset({
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "adservice.google.com",
    "adnxs.com",
    "adsrvr.org",
    "taboola.com",
    "outbrain.com",
    "criteo.com",
    "scorecardresearch.com",
    "hotjar.com",
    "google-analytics.com",
    "analytics.google.com",
    "segment.io",
    "segment.com",
    "mixpanel.com",
    "quantserve.com",
    "adform.net",
    "yieldmo.com",
    "casalemedia.com",
    "pubmatic.com",
    "rubiconproject.com",
    "openx.net",
    "amazon-adsystem.com",
    "adsafeprotected.com",
    "smartadserver.com",
    "lijit.com",
})


def is_blocked_host(host: str) -> bool:
    """Return whether a hostname matches a built-in ad/tracker domain."""
    if not isinstance(host, str):
        return False
    normalized = host.strip().rstrip(".").casefold()
    if not normalized:
        return False
    return any(
        normalized == domain or normalized.endswith("." + domain)
        for domain in BLOCKED_HOSTS
    )


def sanitize_session_data(value):
    """Validate stored session data before it can be used to open tabs."""
    if not isinstance(value, dict):
        return None
    raw_tabs = value.get("tabs")
    if not isinstance(raw_tabs, list):
        return None

    tabs = []
    for raw_url in raw_tabs[:50]:
        if not isinstance(raw_url, str) or len(raw_url) > 8192:
            continue
        candidate = raw_url.strip()
        try:
            parsed = urlsplit(candidate)
        except ValueError:
            continue
        if (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.username is None
            and parsed.password is None
        ):
            tabs.append(candidate)
        elif parsed.scheme == "arma" and parsed.netloc.casefold() == "dashboard":
            tabs.append("arma://dashboard/")
    if not tabs:
        return None

    active_index = value.get("active_index", 0)
    if not isinstance(active_index, int) or isinstance(active_index, bool):
        active_index = 0
    active_index = max(0, min(active_index, len(tabs) - 1))
    profile = value.get("profile", "Guest")
    if not isinstance(profile, str) or not profile.strip() or len(profile) > 80:
        profile = "Guest"
    return {"profile": profile, "tabs": tabs, "active_index": active_index}


class AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    """Small built-in host-based ad/tracker request blocker."""

    def __init__(self, enabled=True):
        super().__init__()
        self.enabled = bool(enabled)
        self.blocked_count = 0

    def interceptRequest(self, info):
        if not self.enabled:
            return
        try:
            host = info.requestUrl().host()
            if is_blocked_host(host):
                info.block(True)
                self.blocked_count += 1
        except (AttributeError, RuntimeError, TypeError):
            logger.debug("Skipped an unsupported WebEngine request", exc_info=True)


class FindInPageDialog(QDialog):
    """A compact, non-modal find bar that follows the active browser tab."""

    def __init__(self, browser, parent=None):
        super().__init__(parent)
        self.browser_ref = weakref.ref(browser)
        self.setWindowTitle("Find in page")
        self.setObjectName("findInPageDialog")
        self.setWindowFlag(Qt.Tool, True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.query = QLineEdit(self)
        self.query.setPlaceholderText("Find on this page")
        self.query.setClearButtonEnabled(True)
        self.query.setAccessibleName("Find in page")
        self.previous_button = QPushButton("Previous", self)
        self.next_button = QPushButton("Next", self)
        self.close_button = QPushButton("Close", self)
        row.addWidget(self.query, 1)
        row.addWidget(self.previous_button)
        row.addWidget(self.next_button)
        row.addWidget(self.close_button)
        layout.addLayout(row)
        self.status = QLabel("", self)
        layout.addWidget(self.status)

        self.query.textChanged.connect(self._find_next)
        self.query.returnPressed.connect(self._find_next)
        self.previous_button.clicked.connect(self._find_previous)
        self.next_button.clicked.connect(self._find_next)
        self.close_button.clicked.connect(self.close)

    def _find(self, backwards=False):
        browser = self.browser_ref()
        if browser is None:
            return
        view = browser.current_view()
        term = self.query.text()
        if view is None or not term:
            self.status.setText("")
            if view is not None:
                try:
                    view.findText("")
                except (RuntimeError, TypeError):
                    pass
            return
        flags = (
            QWebEnginePage.FindFlag.FindBackward
            if backwards
            else QWebEnginePage.FindFlag(0)
        )

        def result_found(found):
            self.status.setText("Match found" if found else "No match")

        try:
            view.findText(term, flags, result_found)
        except (RuntimeError, TypeError):
            self.status.setText("Search is unavailable on this page")

    def _find_next(self, *_args):
        self._find(False)

    def _find_previous(self, *_args):
        self._find(True)

    def showEvent(self, event):
        super().showEvent(event)
        self.query.setFocus(Qt.ShortcutFocusReason)
        self.query.selectAll()


def _origin_key(origin) -> str:
    try:
        value = origin.toString()
    except AttributeError:
        value = str(origin)
    return value.rstrip("/")


def _feature_name(feature) -> str:
    name = getattr(feature, "name", None)
    if isinstance(name, str) and name:
        return name
    text = str(feature)
    return text.rsplit(".", 1)[-1]


def _permission_title(feature_name: str) -> str:
    readable = {
        "Geolocation": "your location",
        "MediaAudioCapture": "your microphone",
        "MediaVideoCapture": "your camera",
        "MediaAudioVideoCapture": "your camera and microphone",
        "DesktopVideoCapture": "screen sharing",
        "DesktopAudioVideoCapture": "screen and audio sharing",
        "DesktopAudioCapture": "system audio capture",
        "Notifications": "notifications",
        "ClipboardReadWrite": "clipboard access",
        "LocalFontsAccess": "local fonts",
        "MouseLock": "mouse lock",
        "FileSystemAccess": "file system access",
        "LocalNetworkAccess": "local network access",
    }
    return readable.get(feature_name, feature_name.replace("_", " ").lower())


def _session_path(browser, profile_name=None) -> str:
    profile = profile_name or getattr(browser, "selected_profile", "Guest")
    # The browser changes to app_data_dir() for frozen builds and uses this same
    # profile_data location for WebEngine storage.
    return os.path.join(os.getcwd(), "profile_data", profile, "session.json")


def _last_session_path() -> str:
    return os.path.join(os.getcwd(), "profile_data", "last_session.json")


def _permission_path(browser, profile_name=None) -> str:
    profile = profile_name or getattr(browser, "selected_profile", "Guest")
    return os.path.join(os.getcwd(), "profile_data", profile, "site_permissions.json")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write_json(path, value):
    from managers.storage import atomic_write_json

    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_json(path, value)


def _stored_session_for_startup():
    """Load the last valid non-private session without initializing WebEngine."""
    from ui.settings import Settings

    settings = Settings()
    settings.load_profile_settings()
    profiles = settings.profiles_list or ["Guest"]
    default_profile = "Guest" if "Guest" in profiles else profiles[0]

    session = sanitize_session_data(_read_json(_last_session_path()))
    if session is not None and session.get("profile") in profiles:
        profile = session["profile"]
    else:
        profile = default_profile
        session = sanitize_session_data(_read_json(_session_path(None, profile)))

    settings.load(profile)
    if not settings.restore_session or settings.private_mode:
        return None
    if session is None:
        session = sanitize_session_data(_read_json(_session_path(None, profile)))
    if session is None:
        return None
    session["profile"] = profile
    return session


def install_essential_features(browser_window_class):
    """Patch the existing browser window with five requested core features."""
    if getattr(browser_window_class, "_essential_features_installed", False):
        return
    browser_window_class._essential_features_installed = True

    original_init = browser_window_class.__init__
    original_get_profile = browser_window_class._get_profile
    original_apply_profile_settings = browser_window_class._apply_profile_settings
    original_new_tab = browser_window_class.new_tab
    original_connect_page = browser_window_class._connect_page
    original_set_tab_visibility = browser_window_class._set_tab_visibility
    original_close_event = browser_window_class.closeEvent

    def _ensure_interceptor(self, profile):
        collection = getattr(self, "_essential_interceptors", None)
        if collection is None:
            collection = {}
            self._essential_interceptors = collection
        key = id(profile)
        interceptor = collection.get(key)
        if interceptor is None:
            enabled = bool(getattr(getattr(self, "settings", None), "ad_blocking_enabled", True))
            interceptor = AdBlockInterceptor(enabled)
            profile.setUrlRequestInterceptor(interceptor)
            collection[key] = interceptor
        return interceptor

    def _wrapped_get_profile(self, profile_name):
        profile = original_get_profile(self, profile_name)
        self._ensure_interceptor(profile)
        return profile

    def _wrapped_apply_profile_settings(self, profile):
        result = original_apply_profile_settings(self, profile)
        interceptor = self._ensure_interceptor(profile)
        interceptor.enabled = bool(getattr(self.settings, "ad_blocking_enabled", True))
        return result

    def _ensure_session_timer(self):
        if getattr(self, "_essential_session_timer", None) is not None:
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(450)
        timer.timeout.connect(self._essential_save_session_now)
        self._essential_session_timer = timer

    def _schedule_session_save(self):
        if not getattr(self, "_essential_features_ready", False):
            return
        self._ensure_session_timer()
        if getattr(self, "_closing", False):
            return
        if not getattr(getattr(self, "settings", None), "restore_session", True):
            return
        if getattr(getattr(self, "settings", None), "private_mode", False):
            return
        self._essential_session_timer.start()

    def _save_session_now(self):
        settings = getattr(self, "settings", None)
        if settings is None:
            return
        profile_name = getattr(self, "selected_profile", "Guest")
        path = _session_path(self)
        last_path = _last_session_path()
        if not getattr(settings, "restore_session", True) or getattr(settings, "private_mode", False):
            for candidate in (path, last_path):
                try:
                    if candidate == last_path:
                        stored = _read_json(last_path)
                        if stored.get("profile") != profile_name:
                            continue
                    if os.path.exists(candidate):
                        os.remove(candidate)
                except OSError:
                    logger.debug("Could not remove disabled session store", exc_info=True)
            return
        tabs = []
        active_url = ""
        views = list(getattr(self, "views", []))
        current_index = getattr(self, "current_index", 0)
        if isinstance(current_index, int) and 0 <= current_index < len(views):
            try:
                active_url = views[current_index].url().toString()
            except (AttributeError, RuntimeError):
                active_url = ""
        for view in views[:50]:
            try:
                raw_url = view.url().toString()
            except (AttributeError, RuntimeError):
                continue
            if not raw_url or raw_url == "about:blank":
                continue
            try:
                parsed = urlsplit(raw_url)
            except ValueError:
                continue
            if (
                parsed.scheme in {"http", "https"}
                and parsed.hostname
                and parsed.username is None
                and parsed.password is None
            ):
                tabs.append(raw_url)
            elif parsed.scheme == "arma" and parsed.netloc.casefold() == "dashboard":
                tabs.append("arma://dashboard/")
        if not tabs:
            return
        active_index = tabs.index(active_url) if active_url in tabs else 0
        document = {
            "profile": profile_name,
            "tabs": tabs,
            "active_index": active_index,
        }
        try:
            _write_json(path, document)
            _write_json(last_path, document)
        except (OSError, TypeError, ValueError):
            logger.warning("Could not save browser session", exc_info=True)

    def _attach_page_features(self, page, view=None):
        if page is None:
            return
        try:
            if view is not None and not getattr(view, "_essential_session_signal_connected", False):
                browser_ref = weakref.ref(self)
                view.urlChanged.connect(
                    lambda _url, ref=browser_ref: (
                        ref()._essential_schedule_session_save() if ref() is not None else None
                    )
                )
                view._essential_session_signal_connected = True
            if not getattr(page, "_essential_pdf_signal_connected", False) and hasattr(page, "pdfPrintingFinished"):
                browser_ref = weakref.ref(self)
                page.pdfPrintingFinished.connect(
                    lambda path, success, ref=browser_ref: (
                        ref()._essential_pdf_finished(path, success) if ref() is not None else None
                    )
                )
                page._essential_pdf_signal_connected = True
            if getattr(page, "_essential_permission_connected", False):
                return
            browser_ref = weakref.ref(self)
            modern_signal = getattr(page, "permissionRequested", None)
            if modern_signal is not None and hasattr(modern_signal, "connect"):
                modern_signal.connect(
                    lambda permission, ref=browser_ref: (
                        ref()._essential_handle_modern_permission(permission) if ref() is not None else None
                    )
                )
            else:
                legacy_signal = getattr(page, "featurePermissionRequested", None)
                if legacy_signal is not None:
                    legacy_signal.connect(
                        lambda origin, feature, p=page, ref=browser_ref: (
                            ref()._essential_handle_legacy_permission(p, origin, feature)
                            if ref() is not None else None
                        )
                    )
            page._essential_permission_connected = True
        except (AttributeError, RuntimeError, TypeError):
            logger.debug("Could not attach all page features", exc_info=True)

    def _wrapped_connect_page(self, view, page):
        result = original_connect_page(self, view, page)
        self._attach_page_features(page, view)
        return result

    def _wrapped_new_tab(self, *args, **kwargs):
        result = original_new_tab(self, *args, **kwargs)
        try:
            index = result if isinstance(result, int) else len(self.views) - 1
            if 0 <= index < len(self.views):
                view = self.views[index]
                self._attach_page_features(view.page(), view)
        except (AttributeError, IndexError, RuntimeError):
            pass
        self._schedule_session_save()
        if getattr(getattr(self, "_essential_devtools_dock", None), "isVisible", lambda: False)():
            self._essential_attach_devtools()
        return result

    def _wrapped_tab_visibility(self, *args, **kwargs):
        result = original_set_tab_visibility(self, *args, **kwargs)
        self._schedule_session_save()
        if getattr(getattr(self, "_essential_devtools_dock", None), "isVisible", lambda: False)():
            self._essential_attach_devtools()
        return result

    def _wrapped_init(self, *args, **kwargs):
        supplied_session = kwargs.get("restored_session")
        if supplied_session is None and len(args) > 1:
            supplied_session = args[1]
        if supplied_session is None:
            # Preserve an explicit network-mode handoff when present; otherwise
            # make ordinary launches resume their prior session by default.
            stored_session = _stored_session_for_startup()
            if stored_session is not None:
                if len(args) > 1:
                    args = list(args)
                    args[1] = stored_session
                    args = tuple(args)
                else:
                    kwargs["restored_session"] = stored_session
        original_init(self, *args, **kwargs)
        self._essential_features_ready = True
        self._essential_permission_memory = {}
        self._essential_devtools_dock = None
        self._essential_devtools_view = None
        self._essential_find_dialog = None
        self._essential_interceptors = getattr(self, "_essential_interceptors", {})
        self._ensure_session_timer()
        self._essential_install_menu_actions()
        for view in tuple(getattr(self, "views", [])):
            self._attach_page_features(view.page(), view)
        self._schedule_session_save()

    def _wrapped_close_event(self, event):
        original_close_event(self, event)
        try:
            if event.isAccepted():
                self._essential_save_session_now()
        except (AttributeError, RuntimeError):
            logger.debug("Could not save session during close", exc_info=True)

    def _settings_changed(self):
        enabled = bool(getattr(self.settings, "ad_blocking_enabled", True))
        for interceptor in getattr(self, "_essential_interceptors", {}).values():
            interceptor.enabled = enabled
        action = getattr(self, "_essential_adblock_action", None)
        if action is not None:
            action.blockSignals(True)
            action.setChecked(enabled)
            action.blockSignals(False)
        self._schedule_session_save()

    def _toggle_ad_blocking(self, enabled):
        self.settings.ad_blocking_enabled = bool(enabled)
        try:
            self.settings.save(self.selected_profile)
        except (OSError, ValueError, TypeError):
            logger.warning("Could not save ad-blocking preference", exc_info=True)
        self._essential_settings_changed()
        message = "Ad and tracker blocking enabled" if enabled else "Ad and tracker blocking disabled"
        self.statusBar().showMessage(message, 2500)

    def _install_menu_actions(self):
        menu = getattr(getattr(self, "navbar", None), "browser_menu", None)
        if menu is None or getattr(self, "_essential_menu_installed", False):
            return
        self._essential_menu_installed = True

        menu.addSeparator()
        self._essential_adblock_action = QAction("Block ads and trackers", self)
        self._essential_adblock_action.setCheckable(True)
        self._essential_adblock_action.setChecked(bool(getattr(self.settings, "ad_blocking_enabled", True)))
        self._essential_adblock_action.setToolTip(
            "Block requests to a built-in list of common advertising and tracking domains."
        )
        self._essential_adblock_action.toggled.connect(self._essential_toggle_ad_blocking)
        menu.addAction(self._essential_adblock_action)

        permissions_action = QAction("Site permissions…", self)
        permissions_action.triggered.connect(self._essential_show_site_permissions)
        menu.addAction(permissions_action)

        self._essential_devtools_action = QAction("Developer tools", self)
        self._essential_devtools_action.setShortcuts([
            QKeySequence("F12"), QKeySequence("Ctrl+Shift+I")
        ])
        self._essential_devtools_action.triggered.connect(self._essential_toggle_devtools)
        self.addAction(self._essential_devtools_action)
        menu.addAction(self._essential_devtools_action)

        menu.addSeparator()
        self._essential_find_action = QAction("Find in page…", self)
        self._essential_find_action.setShortcut(QKeySequence("Ctrl+F"))
        self._essential_find_action.triggered.connect(self._essential_show_find)
        self.addAction(self._essential_find_action)
        menu.addAction(self._essential_find_action)

        self._essential_zoom_in_action = QAction("Zoom in", self)
        self._essential_zoom_in_action.setShortcut(QKeySequence("Ctrl+="))
        self._essential_zoom_in_action.triggered.connect(lambda: self._essential_change_zoom(0.1))
        self.addAction(self._essential_zoom_in_action)
        menu.addAction(self._essential_zoom_in_action)

        self._essential_zoom_out_action = QAction("Zoom out", self)
        self._essential_zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        self._essential_zoom_out_action.triggered.connect(lambda: self._essential_change_zoom(-0.1))
        self.addAction(self._essential_zoom_out_action)
        menu.addAction(self._essential_zoom_out_action)

        self._essential_zoom_reset_action = QAction("Reset zoom", self)
        self._essential_zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
        self._essential_zoom_reset_action.triggered.connect(lambda: self._essential_set_zoom(1.0))
        self.addAction(self._essential_zoom_reset_action)
        menu.addAction(self._essential_zoom_reset_action)

        self._essential_pdf_action = QAction("Save page as PDF…", self)
        self._essential_pdf_action.triggered.connect(self._essential_save_pdf)
        menu.addAction(self._essential_pdf_action)

        self._essential_screenshot_action = QAction("Save visible page screenshot…", self)
        self._essential_screenshot_action.triggered.connect(self._essential_save_screenshot)
        menu.addAction(self._essential_screenshot_action)

        self._essential_print_action = QAction("Print page…", self)
        self._essential_print_action.triggered.connect(self._essential_print_page)
        menu.addAction(self._essential_print_action)

    def _essential_show_find(self):
        if self.current_view() is None:
            return
        dialog = getattr(self, "_essential_find_dialog", None)
        if dialog is None:
            dialog = FindInPageDialog(self, self)
            self._essential_find_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.query.setFocus(Qt.ShortcutFocusReason)
        dialog.query.selectAll()

    def _essential_change_zoom(self, amount):
        view = self.current_view()
        if view is not None:
            self._essential_set_zoom(max(0.25, min(5.0, view.zoomFactor() + amount)))

    def _essential_set_zoom(self, factor):
        view = self.current_view()
        if view is None:
            return
        view.setZoomFactor(max(0.25, min(5.0, float(factor))))
        self.statusBar().showMessage(f"Page zoom: {round(view.zoomFactor() * 100)}%", 2000)

    def _essential_save_pdf(self):
        view = self.current_view()
        if view is None:
            return
        title = re.sub(r"[^A-Za-z0-9._ -]+", "_", view.title()).strip(" .")[:80] or "webpage"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save page as PDF", title + ".pdf", "PDF files (*.pdf)"
        )
        if not path:
            return
        if not path.casefold().endswith(".pdf"):
            path += ".pdf"
        try:
            view.page().printToPdf(path)
            self.statusBar().showMessage("Creating PDF…", 2500)
        except (AttributeError, RuntimeError, TypeError):
            logger.exception("Could not start PDF export")
            QMessageBox.warning(self, "PDF export failed", "This page could not be exported to PDF.")

    def _essential_pdf_finished(self, path, success):
        self.statusBar().showMessage(
            f"PDF saved: {os.path.basename(path)}" if success else "PDF export failed.",
            4000,
        )

    def _essential_save_screenshot(self):
        view = self.current_view()
        if view is None:
            return
        title = re.sub(r"[^A-Za-z0-9._ -]+", "_", view.title()).strip(" .")[:80] or "webpage"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save page screenshot", title + ".png", "PNG image (*.png)"
        )
        if not path:
            return
        if not path.casefold().endswith(".png"):
            path += ".png"
        try:
            image = view.grab()
            if image.isNull() or not image.save(path, "PNG"):
                raise OSError("Could not write screenshot")
            self.statusBar().showMessage(f"Screenshot saved: {os.path.basename(path)}", 3500)
        except (OSError, RuntimeError):
            logger.exception("Could not save page screenshot")
            QMessageBox.warning(self, "Screenshot failed", "The current page could not be captured.")

    def _essential_print_page(self):
        view = self.current_view()
        if view is None:
            return
        try:
            from PySide6.QtPrintSupport import QPrintDialog, QPrinter

            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() != QPrintDialog.DialogCode.Accepted:
                return
            view.page().print(printer, lambda ok: self.statusBar().showMessage(
                "Page sent to printer." if ok else "Printing failed.", 3500
            ))
        except (ImportError, AttributeError, RuntimeError, TypeError):
            logger.exception("Could not print page")
            QMessageBox.warning(self, "Print failed", "Printing is unavailable for this page.")

    def _essential_toggle_devtools(self):
        dock = getattr(self, "_essential_devtools_dock", None)
        if dock is not None and dock.isVisible():
            self._essential_detach_devtools()
            dock.hide()
            return
        if self.current_view() is None:
            return
        if dock is None:
            dock = QDockWidget("Developer tools", self)
            dock.setObjectName("developerToolsDock")
            dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
            dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
            tools_view = QWebEngineView(dock)
            dock.setWidget(tools_view)
            self.addDockWidget(Qt.BottomDockWidgetArea, dock)
            self._essential_devtools_dock = dock
            self._essential_devtools_view = tools_view
            dock.visibilityChanged.connect(
                lambda visible, ref=weakref.ref(self): (
                    ref()._essential_attach_devtools() if visible and ref() is not None else None
                )
            )
        self._essential_attach_devtools()
        dock.show()
        dock.raise_()

    def _essential_attach_devtools(self):
        dock = getattr(self, "_essential_devtools_dock", None)
        tools_view = getattr(self, "_essential_devtools_view", None)
        target = self.current_view()
        if dock is None or tools_view is None or target is None:
            return
        try:
            profile = target.page().profile()
            if tools_view.page().profile() is not profile:
                old_page = tools_view.page()
                tools_view.setPage(QWebEnginePage(profile, tools_view))
                old_page.deleteLater()
            target.page().setDevToolsPage(tools_view.page())
        except (AttributeError, RuntimeError, TypeError):
            logger.exception("Could not attach developer tools")
            self.statusBar().showMessage("Developer tools are unavailable for this page.", 3000)

    def _essential_detach_devtools(self):
        tools_view = getattr(self, "_essential_devtools_view", None)
        if tools_view is None:
            return
        devtools_page = tools_view.page()
        for view in tuple(getattr(self, "views", [])):
            try:
                if view.page().devToolsPage() is devtools_page:
                    view.page().setDevToolsPage(None)
            except (AttributeError, RuntimeError):
                pass

    def _essential_permission_document(self):
        if getattr(getattr(self, "settings", None), "private_mode", False):
            return self._essential_permission_memory
        return _read_json(_permission_path(self))

    def _essential_save_permission_document(self, document):
        if getattr(getattr(self, "settings", None), "private_mode", False):
            self._essential_permission_memory = document
            return
        _write_json(_permission_path(self), document)

    def _essential_apply_saved_permission(self, origin, feature_name):
        key = _origin_key(origin)
        document = self._essential_permission_document()
        site = document.get(key)
        if not isinstance(site, dict):
            return None
        action = site.get(feature_name)
        return action if action in {"allow", "block"} else None

    def _essential_remember_permission(self, origin, feature_name, action):
        key = _origin_key(origin)
        document = self._essential_permission_document()
        site = document.get(key)
        if not isinstance(site, dict):
            site = {}
        site[feature_name] = action
        document[key] = site
        self._essential_save_permission_document(document)

    def _essential_permission_choice(self, origin, feature_name):
        title = _permission_title(feature_name)
        host = origin.host() if hasattr(origin, "host") else _origin_key(origin)
        private = bool(getattr(self.settings, "private_mode", False))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Website permission")
        box.setText(f"{host or 'This website'} wants to access {title}.")
        box.setInformativeText(
            "Choose whether this website may use the requested feature. "
            "Saved choices apply to this site and permission only."
        )
        allow_once = box.addButton(
            "Allow for this session" if private else "Allow once",
            QMessageBox.ButtonRole.AcceptRole,
        )
        block_once = box.addButton(
            "Block for this session" if private else "Block once",
            QMessageBox.ButtonRole.DestructiveRole,
        )
        allow_always = None
        block_always = None
        if not private:
            allow_always = box.addButton("Always allow", QMessageBox.ButtonRole.YesRole)
            block_always = box.addButton("Always block", QMessageBox.ButtonRole.NoRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is allow_once:
            return "allow"
        if clicked is block_once:
            return "block"
        if clicked is allow_always:
            return "allow-always"
        if clicked is block_always:
            return "block-always"
        return "block"

    def _essential_handle_modern_permission(self, permission):
        try:
            origin = permission.origin()
            feature_name = _feature_name(permission.permissionType())
            saved = self._essential_apply_saved_permission(origin, feature_name)
            if saved is None:
                choice = self._essential_permission_choice(origin, feature_name)
                if choice.endswith("-always"):
                    saved = choice.removesuffix("-always")
                    self._essential_remember_permission(origin, feature_name, saved)
                else:
                    saved = choice
            if saved == "allow":
                permission.grant()
            else:
                permission.deny()
        except (AttributeError, RuntimeError, TypeError, OSError, ValueError):
            logger.exception("Could not resolve a website permission request")
            try:
                permission.deny()
            except Exception:
                pass

    def _essential_handle_legacy_permission(self, page, origin, feature):
        try:
            feature_name = _feature_name(feature)
            saved = self._essential_apply_saved_permission(origin, feature_name)
            if saved is None:
                choice = self._essential_permission_choice(origin, feature_name)
                if choice.endswith("-always"):
                    saved = choice.removesuffix("-always")
                    self._essential_remember_permission(origin, feature_name, saved)
                else:
                    saved = choice
            policy = (
                QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
                if saved == "allow"
                else QWebEnginePage.PermissionPolicy.PermissionDeniedByUser
            )
            page.setFeaturePermission(origin, feature, policy)
        except (AttributeError, RuntimeError, TypeError, OSError, ValueError):
            logger.exception("Could not resolve a website permission request")
            try:
                page.setFeaturePermission(
                    origin, feature,
                    QWebEnginePage.PermissionPolicy.PermissionDeniedByUser,
                )
            except Exception:
                pass

    def _essential_show_site_permissions(self):
        view = self.current_view()
        if view is None:
            return
        url = view.url()
        if url.scheme().lower() not in {"http", "https"} or not url.host():
            QMessageBox.information(self, "Site permissions", "Open a website to manage its permissions.")
            return
        port = url.port()
        origin = f"{url.scheme().lower()}://{url.host().lower()}" + (f":{port}" if port > 0 else "")
        document = self._essential_permission_document()
        existing = document.get(origin, {})
        lines = [
            f"{name}: {'Allowed' if decision == 'allow' else 'Blocked'}"
            for name, decision in sorted(existing.items())
            if decision in {"allow", "block"}
        ]
        message = "\n".join(lines) if lines else "No saved permission decisions for this site."
        box = QMessageBox(self)
        box.setWindowTitle("Site permissions")
        box.setText(f"Permissions for {url.host()}")
        box.setInformativeText(message)
        clear_button = box.addButton("Clear saved decisions", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is clear_button and origin in document:
            document.pop(origin, None)
            try:
                self._essential_save_permission_document(document)
            except (OSError, ValueError, TypeError):
                logger.exception("Could not clear website permissions")
                QMessageBox.warning(self, "Site permissions", "Could not clear saved decisions.")
                return
            QMessageBox.information(
                self, "Site permissions",
                "Saved decisions were cleared. Reload the site for new permission prompts.",
            )

    def _essential_show_permission_help(self):
        QMessageBox.information(
            self, "Site permissions",
            "Website permissions are requested when a site first needs a protected feature. "
            "Use Site permissions from the browser menu to review or clear saved choices.",
        )

    browser_window_class._ensure_interceptor = _ensure_interceptor
    browser_window_class._ensure_session_timer = _ensure_session_timer
    browser_window_class._attach_page_features = _attach_page_features
    browser_window_class._schedule_session_save = _schedule_session_save
    browser_window_class._save_session_now = _save_session_now
    browser_window_class._essential_schedule_session_save = _schedule_session_save
    browser_window_class._essential_save_session_now = _save_session_now
    browser_window_class._essential_settings_changed = _settings_changed
    browser_window_class._essential_toggle_ad_blocking = _toggle_ad_blocking
    browser_window_class._essential_install_menu_actions = _install_menu_actions
    browser_window_class._essential_show_find = _essential_show_find
    browser_window_class._essential_change_zoom = _essential_change_zoom
    browser_window_class._essential_set_zoom = _essential_set_zoom
    browser_window_class._essential_save_pdf = _essential_save_pdf
    browser_window_class._essential_pdf_finished = _essential_pdf_finished
    browser_window_class._essential_save_screenshot = _essential_save_screenshot
    browser_window_class._essential_print_page = _essential_print_page
    browser_window_class._essential_toggle_devtools = _essential_toggle_devtools
    browser_window_class._essential_attach_devtools = _essential_attach_devtools
    browser_window_class._essential_detach_devtools = _essential_detach_devtools
    browser_window_class._essential_permission_document = _essential_permission_document
    browser_window_class._essential_save_permission_document = _essential_save_permission_document
    browser_window_class._essential_apply_saved_permission = _essential_apply_saved_permission
    browser_window_class._essential_remember_permission = _essential_remember_permission
    browser_window_class._essential_permission_choice = _essential_permission_choice
    browser_window_class._essential_handle_modern_permission = _essential_handle_modern_permission
    browser_window_class._essential_handle_legacy_permission = _essential_handle_legacy_permission
    browser_window_class._essential_show_site_permissions = _essential_show_site_permissions

    browser_window_class._get_profile = _wrapped_get_profile
    browser_window_class._apply_profile_settings = _wrapped_apply_profile_settings
    browser_window_class._connect_page = _wrapped_connect_page
    browser_window_class.new_tab = _wrapped_new_tab
    browser_window_class._set_tab_visibility = _wrapped_tab_visibility
    browser_window_class.__init__ = _wrapped_init
    browser_window_class.closeEvent = _wrapped_close_event

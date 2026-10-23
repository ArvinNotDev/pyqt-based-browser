"""Small JavaScript bridge that is active only on ARMA's internal page."""

from __future__ import annotations

import json

from PySide6.QtCore import QObject, QUrl, QUrlQuery, Slot


class DashboardBridge(QObject):
    """Forward dashboard intents after checking the calling page origin."""

    def __init__(self, browser, page):
        super().__init__(page)
        self.browser = browser
        self.page = page

    @Slot(str, str)
    def dispatch(self, action: str, payload_json: str) -> None:
        if not getattr(self.page, "_dashboard_active", False):
            return
        try:
            page_url = self.page.url()
        except RuntimeError:
            return
        if page_url.scheme().lower() != "arma" or page_url.host().lower() not in {
            "dashboard", "settings", "history", "downloads"
        }:
            return
        if not isinstance(action, str) or len(action) > 40 or len(payload_json) > 80_000:
            return
        try:
            payload = json.loads(payload_json) if payload_json else {}
        except (json.JSONDecodeError, TypeError):
            return
        if not isinstance(payload, dict):
            return
        url = QUrl("arma-action://dispatch/")
        query = QUrlQuery()
        query.addQueryItem("action", action)
        query.addQueryItem("payload", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        url.setQuery(query)
        self.browser._handle_dashboard_action(self.page, url)

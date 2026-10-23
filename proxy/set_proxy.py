"""Apply and restore the optional Qt WebEngine network proxy."""

import platform
import threading

from PySide6.QtNetwork import QNetworkProxy, QNetworkProxyFactory


class Os:
    Windows = "Windows"
    Linux = "Linux"


def get_os_name():
    return platform.system()


action_list = ["set", "clear"]
_proxy_lock = threading.RLock()
_previous_proxy = None
_application_proxy_active = False
_uses_system_configuration = False


def set_proxy(profile, host: str, port: int):
    """Route Qt WebEngine through the local Tor bridge, preserving the old route."""
    del profile  # Qt WebEngine takes its proxy from Qt Network's application setting.
    global _previous_proxy, _application_proxy_active, _uses_system_configuration
    with _proxy_lock:
        if not _application_proxy_active:
            _previous_proxy = QNetworkProxy.applicationProxy()
            _uses_system_configuration = QNetworkProxyFactory.usesSystemConfiguration()
        proxy = QNetworkProxy(QNetworkProxy.HttpProxy, host, int(port))
        QNetworkProxy.setApplicationProxy(proxy)
        _application_proxy_active = True


def clear_proxy(profile):
    """Restore the route that was active before the user enabled Tor."""
    del profile
    global _previous_proxy, _application_proxy_active, _uses_system_configuration
    with _proxy_lock:
        if not _application_proxy_active:
            return
        if _uses_system_configuration:
            QNetworkProxyFactory.setUseSystemConfiguration(True)
        else:
            previous_proxy = _previous_proxy or QNetworkProxy(QNetworkProxy.NoProxy)
            QNetworkProxy.setApplicationProxy(previous_proxy)
        _previous_proxy = None
        _application_proxy_active = False
        _uses_system_configuration = False


def manage_proxy(profile, host, port, action="set"):
    if action == action_list[0]:
        return set_proxy(profile, host, port)
    if action == action_list[1]:
        return clear_proxy(profile)
    raise ValueError(f"Unknown proxy action: {action}")

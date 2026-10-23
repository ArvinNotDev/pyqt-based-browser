"""Responsive ARMA internal pages rendered only on the app-owned arma:// origin."""

from __future__ import annotations

import html
import json
from typing import Any

from ._manager_ui import normalize_download


def _e(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _payload(value: dict) -> str:
    return _e(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _action(label: str, action: str, payload: dict | None = None, cls: str = "") -> str:
    klass = f' class="{_e(cls)}"' if cls else ""
    return (
        f'<button type="button"{klass} data-action="{_e(action)}" '
        f'data-payload="{_payload(payload or {})}">{_e(label)}</button>'
    )


def _shell(browser, title: str, subtitle: str, body: str, active: str) -> str:
    dark = bool(getattr(browser.settings, "dark_mode", False))
    mode_class = "dark" if dark else "light"
    nav = [
        ("Home", "dashboard"),
        ("Settings", "settings"),
        ("History", "history"),
        ("Downloads", "downloads"),
    ]
    nav_html = "".join(
        f'<a class="nav-link{" active" if host == active else ""}" href="arma://{host}/">{label}</a>'
        for label, host in nav
    )
    css = r"""
:root { color-scheme: light dark; --bg:#f5f8fc; --surface:rgba(255,255,255,.88); --surface-2:#fff;
 --text:#233047; --muted:#66768c; --line:#dbe3ee; --accent:#176fc1; --accent-soft:#e2efff;
 --danger:#bb4048; --shadow:0 10px 30px rgba(25,50,80,.07); }
html.dark { color-scheme:dark; --bg:#171c23; --surface:rgba(32,38,48,.96); --surface-2:#1b222b; --text:#e8edf3;
 --muted:#9aaabd; --line:#3b4655; --accent:#75b4ff; --accent-soft:#263a53; --danger:#ff777e;
 --shadow:0 12px 34px rgba(0,0,0,.2); }
html.light { color-scheme:light; }
* { box-sizing:border-box; scrollbar-color:var(--line) var(--bg); scrollbar-width:thin; }
*::-webkit-scrollbar { width:10px; height:10px; }
*::-webkit-scrollbar-track { background:var(--bg); }
*::-webkit-scrollbar-thumb { background:var(--line); border:2px solid var(--bg); border-radius:6px; }
*::-webkit-scrollbar-thumb:hover { background:var(--muted); }
html, body { min-height:100%; margin:0; background:var(--bg); color:var(--text);
 font:14px/1.5 "Segoe UI",system-ui,-apple-system,sans-serif; }
body { padding:20px clamp(12px,3.4vw,36px) 36px; }
a { color:inherit; text-decoration:none; }
button, input, select { font:inherit; }
button, .button { min-height:34px; display:inline-flex; align-items:center; justify-content:center;
 gap:7px; padding:7px 12px; border:1px solid var(--line); border-radius:9px; color:var(--text);
 background:var(--surface-2); cursor:pointer; transition:background .14s,border-color .14s,transform .14s; }
button:hover, .button:hover { background:var(--accent-soft); border-color:var(--accent); }
button:active, .button:active { transform:translateY(1px); }
button.primary { background:var(--accent); color:#fff; border-color:var(--accent); font-weight:700; }
button.primary:hover { filter:brightness(1.06); }
button.danger { color:var(--danger); }
button.ghost { background:transparent; }
button:disabled { opacity:.45; cursor:not-allowed; }
.app { max-width:1100px; margin:0 auto; }
header { display:flex; align-items:center; justify-content:space-between; gap:16px; margin:0 0 22px; }
.brand { display:flex; align-items:center; gap:12px; min-width:0; }
.brand-mark { display:grid; place-items:center; flex:0 0 42px; width:42px; height:42px; border-radius:14px;
 color:#fff; background:linear-gradient(145deg,#3788e4,#1959a5); box-shadow:0 7px 18px rgba(28,101,188,.23);
 font-size:21px; font-weight:800; }
h1 { margin:0; font-size:clamp(22px,3vw,30px); line-height:1.15; letter-spacing:-.6px; }
.subtitle { margin:5px 0 0; color:var(--muted); font-size:13px; }
.nav { display:flex; gap:4px; align-items:center; flex-wrap:wrap; padding:4px; border:1px solid var(--line);
 border-radius:12px; background:var(--surface); box-shadow:var(--shadow); }
.nav-link { display:inline-flex; align-items:center; justify-content:center; padding:8px 11px; border-radius:8px;
 color:var(--muted); font-weight:650; white-space:nowrap; }
.nav-link:hover { color:var(--text); background:var(--accent-soft); }
.nav-link.active { color:var(--accent); background:var(--accent-soft); }
.layout { display:grid; grid-template-columns:minmax(0,1fr) 260px; align-items:start; gap:16px; }
main { min-width:0; }
aside { padding:16px; background:var(--surface); border:1px solid var(--line); border-radius:16px; box-shadow:var(--shadow); }
aside h2 { margin:0 0 8px; font-size:13px; }
aside p { margin:0 0 11px; color:var(--muted); font-size:12px; }
.page-head { display:flex; align-items:end; justify-content:space-between; gap:12px; margin-bottom:16px; }
.page-head h2 { margin:0; font-size:18px; }
.panel { background:var(--surface); border:1px solid var(--line); border-radius:16px; box-shadow:var(--shadow); overflow:hidden; }
.panel + .panel { margin-top:14px; }
.panel-head { padding:15px 17px; border-bottom:1px solid var(--line); }
.panel-head h3 { margin:0; font-size:14px; }
.panel-head p { margin:4px 0 0; font-size:12px; color:var(--muted); }
.panel-body { padding:17px; }
.form-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:15px 18px; }
.field { min-width:0; display:flex; flex-direction:column; gap:6px; }
.field.full { grid-column:1/-1; }
.field label, .field-label { font-size:12px; font-weight:700; color:var(--muted); }
input[type=text], input[type=url], input[type=search], select {
 width:100%; min-width:0; min-height:38px; padding:9px 11px; background:var(--surface-2); color:var(--text);
 border:1px solid var(--line); border-radius:9px; outline:none;
}
input:focus, select:focus { border-color:var(--accent); box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 18%,transparent); }
.field-hint { font-size:11px; color:var(--muted); }
.check-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:9px; }
.check-row { min-height:42px; display:flex; align-items:center; gap:10px; padding:10px 12px;
 background:var(--surface-2); border:1px solid var(--line); border-radius:10px; }
.check-row input { accent-color:var(--accent); width:16px; height:16px; flex:0 0 auto; }
.check-copy { display:flex; flex-direction:column; gap:1px; }
.check-copy strong { font-size:12px; }
.check-copy small { font-size:11px; color:var(--muted); }
.form-actions { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px; padding-top:16px; margin-top:16px; border-top:1px solid var(--line); }
.banner { padding:12px 14px; background:var(--accent-soft); color:var(--text); border-radius:11px; font-size:12px; }
.empty { display:grid; justify-items:center; gap:7px; padding:35px 16px; text-align:center; color:var(--muted); }
.empty .glyph { font-size:27px; color:var(--accent); }
.empty strong { color:var(--text); font-size:14px; }
.list { display:flex; flex-direction:column; gap:10px; }
.history-item, .download-item { min-width:0; padding:14px; border:1px solid var(--line); background:var(--surface); border-radius:13px; }
.item-top { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.item-title { min-width:0; font-weight:750; overflow-wrap:anywhere; }
.item-sub { color:var(--muted); font-size:11px; margin-top:4px; overflow-wrap:anywhere; }
.actions { display:flex; flex-wrap:wrap; gap:6px; margin-top:11px; }
.actions button { min-height:30px; padding:5px 9px; font-size:12px; }
.visit { display:flex; align-items:center; justify-content:space-between; gap:8px; padding:8px 0 0; margin-top:8px;
 border-top:1px solid var(--line); }
.visit time { color:var(--muted); font-size:12px; }
.visit button { min-height:27px; font-size:11px; padding:3px 7px; }
progress { width:100%; height:6px; border:0; border-radius:4px; overflow:hidden; accent-color:var(--accent); }
.progress-track { height:6px; overflow:hidden; background:var(--line); border-radius:5px; margin-top:11px; }
.progress-value { height:100%; background:var(--accent); border-radius:5px; }
.status-pill { display:inline-flex; align-items:center; gap:6px; padding:4px 8px; border-radius:7px; background:var(--accent-soft);
 color:var(--accent); font-size:11px; font-weight:750; }
.footer-note { margin-top:16px; color:var(--muted); font-size:11px; }
.toast { position:fixed; bottom:18px; left:50%; transform:translate(-50%,20px); opacity:0; pointer-events:none;
 max-width:min(600px,calc(100vw - 28px)); padding:11px 15px; border:1px solid var(--line); border-radius:11px;
 background:var(--surface-2); box-shadow:var(--shadow); transition:all .18s; z-index:20; }
.toast.show { transform:translate(-50%,0); opacity:1; }
@media (max-width:800px) {
 body { padding:14px 12px 28px; }
 header { align-items:flex-start; flex-direction:column; gap:14px; }
 .nav { width:100%; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); }
 .nav-link { padding:8px 4px; font-size:12px; }
 .layout { grid-template-columns:minmax(0,1fr); }
 aside { order:2; }
 .form-grid { grid-template-columns:minmax(0,1fr); }
 .check-grid { grid-template-columns:minmax(0,1fr); }
 .page-head { align-items:flex-start; flex-direction:column; }
}
"""
    base = f"""<!doctype html>
<html class="{mode_class}" lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{_e(title)} · ARMA Browser</title>
<style>{css}</style>
</head>
<body>
<div class="app">
<header>
  <div class="brand"><div class="brand-mark" aria-hidden="true">A</div>
    <div><h1>{_e(title)}</h1><p class="subtitle">{_e(subtitle)}</p></div>
  </div>
  <nav class="nav" aria-label="Browser pages">{nav_html}</nav>
</header>
{body}
</div>
<div id="toast" class="toast" role="status" aria-live="polite"></div>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
(() => {{
  let bridge = null;
  let toastTimer = null;
  window.armaAction = (action, payload = {{}}) => {{
    if (bridge) bridge.dispatch(action, JSON.stringify(payload));
    else window.armaToast('The browser bridge is not ready yet.', 'warning');
  }};
  window.armaSetTheme = (mode) => {{
    const normalized = mode === 'dark' ? 'dark' : 'light';
    document.documentElement.classList.toggle('dark', normalized === 'dark');
    document.documentElement.classList.toggle('light', normalized === 'light');
    document.documentElement.style.colorScheme = normalized;
  }};
  window.armaToast = (message) => {{
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = String(message || '');
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
  }};
  document.addEventListener('click', (event) => {{
    const button = event.target.closest('[data-action]');
    if (!button || button.disabled) return;
    event.preventDefault();
    let payload = {{}};
    try {{ payload = JSON.parse(button.dataset.payload || '{{}}'); }}
    catch (_) {{ window.armaToast('Invalid action data.'); return; }}
    window.armaAction(button.dataset.action, payload);
  }});
  if (window.qt && qt.webChannelTransport && window.QWebChannel) {{
    new QWebChannel(qt.webChannelTransport, channel => {{
      bridge = channel.objects.armaDashboard;
      if (typeof window.armaPageReady === 'function') window.armaPageReady();
    }});
  }}
}})();
</script>
</body>
</html>"""
    return base


def _settings_page(browser) -> str:
    settings = browser.settings
    search_engines = [
        ("https://www.google.com/search?q=", "Google"),
        ("https://duckduckgo.com/?q=", "DuckDuckGo"),
        ("https://www.bing.com/search?q=", "Bing"),
    ]
    current_engine = str(settings.default_search_engine or search_engines[0][0])
    known = {value for value, _label in search_engines}
    engine_options = "".join(
        f'<option value="{_e(value)}"{" selected" if current_engine == value else ""}>{_e(label)}</option>'
        for value, label in search_engines
    )
    if current_engine not in known:
        engine_options += f'<option value="{_e(current_engine)}" selected>Saved custom search engine</option>'
    def checkbox(name: str, label: str, detail: str, value: bool) -> str:
        checked = " checked" if value else ""
        return (
            f'<label class="check-row"><input type="checkbox" name="{_e(name)}"{checked}>'
            f'<span class="check-copy"><strong>{_e(label)}</strong><small>{_e(detail)}</small></span></label>'
        )
    body = f"""
<div class="layout">
<main>
  <form id="settings-form">
    <section class="panel">
      <div class="panel-head"><h3>Browsing</h3><p>Set the pages and search behavior used by this profile.</p></div>
      <div class="panel-body">
        <div class="form-grid">
          <div class="field full"><label for="homepage">Homepage</label>
            <input id="homepage" name="homepage" type="url" value="{_e(settings.homepage)}" required>
            <span class="field-hint">Use a website URL or an ARMA internal page such as arma://dashboard/.</span>
          </div>
          <div class="field"><label for="startup_page">Startup page</label>
            <select id="startup_page" name="startup_page">
              <option value="dashboard"{" selected" if settings.startup_page == "dashboard" else ""}>ARMA dashboard</option>
              <option value="homepage"{" selected" if settings.startup_page == "homepage" else ""}>Homepage</option>
            </select>
          </div>
          <div class="field"><label for="new_tab_page">New tab page</label>
            <select id="new_tab_page" name="new_tab_page">
              <option value="dashboard"{" selected" if settings.new_tab_page == "dashboard" else ""}>ARMA dashboard</option>
              <option value="homepage"{" selected" if settings.new_tab_page == "homepage" else ""}>Homepage</option>
            </select>
          </div>
          <div class="field full"><label for="search_engine">Default search engine</label>
            <select id="search_engine" name="search_engine">{engine_options}</select>
          </div>
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h3>Privacy and appearance</h3><p>These options are saved to the current profile.</p></div>
      <div class="panel-body">
        <div class="check-grid">
          {checkbox("dark_mode", "Dark appearance", "Use the dark browser theme.", settings.dark_mode)}
          {checkbox("private_mode", "Private browsing", "Use an off-the-record profile.", settings.private_mode)}
          {checkbox("save_history", "Save history", "Keep visited pages for this profile.", settings.save_history)}
          {checkbox("save_cookies", "Save cookies", "Keep website cookies between runs.", settings.save_cookies)}
          {checkbox("hardware_acceleration", "Hardware acceleration", "Use accelerated rendering where available.", settings.hardware_acceleration)}
          {checkbox("site_compatibility_mode", "Site compatibility", "Use a more compatible browser user-agent.", settings.site_compatibility_mode)}
          {checkbox("proxy_panel_visible", "Show Tor panel on startup", "Remember whether the Tor panel is visible.", settings.proxy_panel_visible)}
        </div>
      </div>
    </section>
    <section class="panel">
      <div class="panel-head"><h3>Downloads</h3><p>Choose where files from the browser are stored.</p></div>
      <div class="panel-body">
        <div class="field">
          <label for="download_folder">Download folder</label>
          <div style="display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px">
            <input id="download_folder" name="download_folder" type="text" value="{_e(settings.download_folder)}" required>
            <button type="button" id="browse-folder">Browse…</button>
          </div>
        </div>
      </div>
    </section>
    <div class="form-actions">
      <button type="button" data-action="navigate_internal" data-payload='{{"host":"history"}}'>History</button>
      <button type="button" data-action="navigate_internal" data-payload='{{"host":"downloads"}}'>Downloads</button>
      <button class="primary" type="submit">Save settings</button>
    </div>
  </form>
  <p class="footer-note">Hardware acceleration changes may require a full browser restart to take effect.</p>
</main>
<aside><h2>ARMA Browser</h2>
  <p>Settings are stored in the <strong>{_e(browser.selected_profile)}</strong> profile. Private browsing uses separate temporary storage.</p>
  <div class="banner">Your Tor panel has its own connection settings and can be opened from the globe button in the browser toolbar.</div>
</aside>
</div>
<script>
document.getElementById('settings-form').addEventListener('submit', event => {{
  event.preventDefault();
  const field = name => document.getElementById(name).value;
  const checked = name => document.querySelector('[name="' + name + '"]').checked;
  window.armaAction('save_browser_settings', {{
    homepage: field('homepage'),
    startup_page: field('startup_page'),
    new_tab_page: field('new_tab_page'),
    default_search_engine: field('search_engine'),
    download_folder: field('download_folder'),
    dark_mode: checked('dark_mode'),
    private_mode: checked('private_mode'),
    save_history: checked('save_history'),
    save_cookies: checked('save_cookies'),
    hardware_acceleration: checked('hardware_acceleration'),
    site_compatibility_mode: checked('site_compatibility_mode'),
    proxy_panel_visible: checked('proxy_panel_visible')
  }});
}});
document.getElementById('browse-folder').addEventListener('click', () => window.armaAction('browse_download_folder'));
window.setDownloadFolder = value => {{ document.getElementById('download_folder').value = String(value || ''); }};
</script>"""
    return _shell(browser, "Settings", "Personalize browsing, privacy, and download behavior.", body, "settings")


def _history_page(browser) -> str:
    history = getattr(browser, "history", None)
    if history is None or browser.settings.private_mode or not browser.settings.save_history:
        body = """
<div class="layout"><main><section class="panel"><div class="empty">
  <div class="glyph">◷</div><strong>History is unavailable</strong>
  <p>History is disabled for this session or profile.</p>
  <a class="button" href="arma://settings/">Review settings</a>
</div></section></main>
<aside><h2>Browsing history</h2><p>History can be turned off in Settings. Private sessions never display a persistent history.</p></aside></div>"""
        return _shell(browser, "History", "Find a previously visited page.", body, "history")

    links = []
    total_visits = 0
    for url, visits in reversed(list(history.history.items())):
        if not isinstance(url, str):
            continue
        visit_rows = visits if isinstance(visits, list) else []
        total_visits += len(visit_rows)
        details = []
        for index in range(len(visit_rows) - 1, max(-1, len(visit_rows) - 6), -1):
            visit = visit_rows[index] if isinstance(visit_rows[index], dict) else {}
            label = f"{visit.get('date', 'Unknown date')} · {visit.get('time', 'Unknown time')}"
            details.append(
                '<div class="visit"><time>' + _e(label) + '</time>' +
                _action("Remove visit", "history_delete_visit",
                        {"url": url, "date": str(visit.get("date", "")), "time": str(visit.get("time", "")), "index": index},
                        "ghost danger") + '</div>'
            )
        links.append(
            f'<article class="history-item" data-filter-text="{_e(url.casefold())}">'
            f'<div class="item-top"><div style="min-width:0"><div class="item-title">{_e(url)}</div>'
            f'<div class="item-sub">{len(visit_rows)} visit{"s" if len(visit_rows) != 1 else ""}</div></div>'
            f'<span class="status-pill">History</span></div>'
            '<div class="actions">'
            + _action("Open", "history_open", {"url": url}, "primary")
            + _action("Remove URL", "history_delete_url", {"url": url}, "danger")
            + '</div>' + ''.join(details) + '</article>'
        )
    listing = "".join(links) or '<div class="empty"><div class="glyph">◷</div><strong>No history yet</strong><p>Pages you visit will appear here.</p></div>'
    body = f"""
<div class="page-head"><div><h2>Recent pages</h2><p class="subtitle">{len(history.history)} URLs · {total_visits} visits</p></div>
  <div style="display:flex;gap:7px;flex-wrap:wrap">
    <input id="history-filter" type="search" placeholder="Filter by URL…" aria-label="Filter history" style="width:min(260px,56vw)">
    {_action("Clear history", "history_clear", {}, "danger")}
  </div>
</div>
<div id="history-list" class="list">{listing}</div>
<p class="footer-note">Use “Remove visit” to delete a single timestamp, or “Remove URL” to remove every recorded visit for that address.</p>
<script>
document.getElementById('history-filter').addEventListener('input', event => {{
 const value = event.target.value.trim().toLocaleLowerCase();
 document.querySelectorAll('.history-item').forEach(item => {{
   item.hidden = !item.textContent.toLocaleLowerCase().includes(value);
 }});
}});
</script>"""
    return _shell(browser, "History", "Search and manage your browsing history.", body, "history")


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "Size unknown"
    amount = float(max(0, int(value)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{amount:.1f} TB"


def _downloads_page(browser) -> str:
    manager = getattr(browser, "download_manager", None)
    raw_records = manager.get_downloads() if manager is not None else []
    cards = []
    counts = {"downloading": 0, "completed": 0, "failed": 0, "cancelled": 0, "requested": 0}
    for raw in reversed(raw_records):
        download = normalize_download(raw)
        if download is None:
            continue
        state = download["status"]
        counts[state] = counts.get(state, 0) + 1
        ident = download.get("id")
        payload = {"id": ident}
        received, total = download["received"], download["total"]
        percent = min(100, int(received * 100 / total)) if total and total > 0 else None
        if state in {"requested", "downloading"}:
            state_text = "Paused" if raw.get("paused") else ("Starting" if state == "requested" else "Downloading")
        else:
            state_text = state.title()
        details = [state_text]
        details.append(f"{_format_bytes(received)} received")
        if total is not None:
            details.append(f"of {_format_bytes(total)}")
        if download.get("error"):
            details.append(download["error"])
        if percent is not None:
            details.append(f"{percent}%")
        if state in {"requested", "downloading"}:
            action_buttons = (
                _action("Cancel", "downloads_cancel", payload, "danger")
                + _action("Resume" if raw.get("paused") else "Pause", "downloads_resume" if raw.get("paused") else "downloads_pause", payload)
            )
            progress = f'<div class="progress-track"><div class="progress-value" style="width:{percent if percent is not None else 35}%"></div></div>'
        elif state == "completed":
            action_buttons = (
                _action("Open file", "downloads_open", payload, "primary")
                + _action("Show folder", "downloads_folder", payload)
                + _action("Delete file", "downloads_delete_file", payload, "danger")
                + _action("Remove entry", "downloads_remove", payload)
            )
            progress = '<div class="progress-track"><div class="progress-value" style="width:100%"></div></div>'
        else:
            action_buttons = _action("Remove entry", "downloads_remove", payload, "danger")
            progress = ""
        cards.append(
            f'<article class="download-item">'
            f'<div class="item-top"><div style="min-width:0"><div class="item-title">{_e(download["filename"])}</div>'
            f'<div class="item-sub">{_e(download["url"] or download["path"])}</div></div>'
            f'<span class="status-pill">{_e(state_text)}</span></div>'
            f'<div class="item-sub" style="margin-top:10px">{_e(" · ".join(details))}</div>'
            + progress
            + f'<div class="actions">{action_buttons}</div></article>'
        )
    main_content = "".join(cards) or '<div class="empty"><div class="glyph">⇩</div><strong>No downloads yet</strong><p>Files you download will appear here while the browser is open.</p></div>'
    body = f"""
<div class="page-head"><div><h2>Download manager</h2><p class="subtitle">{counts['downloading'] + counts['requested']} active · {counts['completed']} completed</p></div>
  <div style="display:flex;gap:7px;flex-wrap:wrap">
    <button type="button" data-action="downloads_refresh">Refresh</button>
    {_action("Clear finished", "downloads_clear_finished", {}, "danger")}
  </div>
</div>
<div class="list">{main_content}</div>
<p class="footer-note">Download records are kept in memory for the active browser profile. Deleting a completed file is restricted to files within the configured download folder.</p>"""
    return _shell(browser, "Downloads", "Track progress and manage downloaded files.", body, "downloads")


def render_internal_page(browser, host: str) -> str:
    host = str(host or "").strip().lower()
    if host == "settings":
        return _settings_page(browser)
    if host == "history":
        return _history_page(browser)
    if host == "downloads":
        return _downloads_page(browser)
    raise ValueError(f"Unsupported ARMA internal page: {host}")

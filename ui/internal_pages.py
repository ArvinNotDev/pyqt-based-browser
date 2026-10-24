"""Responsive ARMA internal pages rendered only on the app-owned arma:// origin."""

from __future__ import annotations

import base64
import html
import json
import os
from typing import Any

from app_paths import user_data_path
from managers.storage import validate_profile_name

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
        ("Bookmarks", "bookmarks"),
        ("History", "history"),
        ("Downloads", "downloads"),
        ("Profiles", "profile"),
        ("Settings", "settings"),
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
/* Browser settings: searchable, categorized, and responsive like a native preferences view. */
.settings-topbar { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
.settings-menu-toggle { display:none; white-space:nowrap; background:var(--surface); }
.settings-search-wrap { display:flex; align-items:center; gap:8px; flex:1; min-width:0; padding:0 11px;
 background:var(--surface); border:1px solid var(--line); border-radius:11px; box-shadow:var(--shadow); }
.settings-search-wrap .search-glyph { color:var(--muted); font-size:20px; line-height:1; }
.settings-search-wrap input { border:0; background:transparent; outline:0; box-shadow:none; min-height:40px; padding:8px 0; }
.settings-search-wrap input:focus { border:0; box-shadow:none; }
.settings-search-wrap kbd { flex:0 0 auto; color:var(--muted); background:var(--bg); border:1px solid var(--line);
 border-radius:5px; padding:2px 5px; font-size:10px; }
.settings-save-status { flex:0 0 auto; color:var(--muted); font-size:11px; }
.settings-save-status.saving { color:var(--accent); }
.settings-save-status.error { color:var(--danger); }
.settings-layout { display:grid; grid-template-columns:208px minmax(0,1fr); gap:16px; align-items:start; position:relative; }
.settings-sidebar { position:sticky; top:12px; display:flex; flex-direction:column; gap:4px; padding:9px;
 border:1px solid var(--line); background:var(--surface); border-radius:14px; box-shadow:var(--shadow); }
.settings-sidebar-heading { display:flex; align-items:center; justify-content:space-between; padding:8px 9px 12px;
 color:var(--muted); font-size:10px; font-weight:800; letter-spacing:1.15px; }
.settings-menu-close { display:none; min-height:27px; width:27px; padding:0; font-size:19px; }
.settings-category { width:100%; justify-content:flex-start; text-align:left; border-color:transparent; background:transparent;
 min-height:39px; padding:7px 10px; font-size:12px; color:var(--muted); }
.settings-category .category-icon { width:20px; text-align:center; color:currentColor; font-size:14px; }
.settings-category.active { color:var(--accent); background:var(--accent-soft); border-color:color-mix(in srgb,var(--accent) 22%,transparent); }
.settings-category[hidden] { display:none; }
.settings-no-categories { padding:7px 10px; color:var(--muted); font-size:12px; }
.settings-main { min-width:0; }
.settings-section { display:none; min-width:0; }
.settings-section.active { display:block; animation:settings-fade-in .14s ease-out; }
@keyframes settings-fade-in { from { opacity:.78; transform:translateY(2px); } to { opacity:1; transform:translateY(0); } }
.settings-section-head { margin:2px 1px 15px; }
.settings-section-head h2 { font-size:22px; margin:3px 0 4px; letter-spacing:-.35px; }
.settings-section-head p { margin:0; color:var(--muted); font-size:12px; }
.section-kicker { color:var(--accent); letter-spacing:1.4px; font-size:9px; font-weight:800; }
.settings-panel { border-radius:13px; }
.settings-panel + .settings-panel { margin-top:12px; }
.settings-panel .panel-head { padding:12px 15px; }
.settings-panel .panel-body { padding:5px 15px; }
.setting-list { display:flex; flex-direction:column; }
.setting-row { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:13px 0;
 border-bottom:1px solid var(--line); min-width:0; }
.setting-row:last-child { border-bottom:0; }
.setting-row[hidden] { display:none !important; }
.setting-copy { min-width:0; display:flex; flex-direction:column; gap:3px; }
.setting-copy > label, .setting-copy > strong { font-size:12px; font-weight:750; }
.setting-copy small { max-width:520px; color:var(--muted); font-size:11px; line-height:1.45; }
.setting-control:not([type=checkbox]) { width:min(320px,52%); flex:0 1 320px; }
.setting-input-with-button { display:flex; align-items:center; gap:7px; flex:0 1 370px; min-width:0; }
.setting-input-with-button input { flex:1; min-width:0; }
.setting-input-with-button button { flex:0 0 auto; }
.setting-toggle { cursor:pointer; }
.setting-toggle .setting-control[type=checkbox] { position:absolute; width:1px; height:1px; opacity:0; pointer-events:none; }
.check-ui { position:relative; flex:0 0 38px; width:38px; height:22px; border-radius:999px;
 background:var(--line); box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--text) 9%,transparent); transition:background .16s ease; }
.check-ui::after { content:""; position:absolute; width:16px; height:16px; top:3px; left:3px; border-radius:50%;
 background:var(--surface-2); box-shadow:0 1px 3px #0002; transition:transform .16s ease; }
.setting-control[type=checkbox]:checked + .check-ui { background:var(--accent); }
.setting-control[type=checkbox]:checked + .check-ui::after { transform:translateX(16px); }
.setting-control[type=checkbox]:focus-visible + .check-ui { outline:3px solid color-mix(in srgb,var(--accent) 38%,transparent); outline-offset:3px; }
.theme-switch { position:relative; display:inline-flex; flex:0 0 auto; cursor:pointer; }
.theme-switch input { position:absolute; width:1px; height:1px; opacity:0; }
.theme-track { display:flex; align-items:center; width:64px; height:36px; padding:3px; border-radius:999px;
 background:linear-gradient(135deg,#e9f0fa,#d6e2f2); border:1px solid #c7d5e8; transition:background .16s,border-color .16s; }
.theme-thumb { display:grid; place-items:center; width:28px; height:28px; border-radius:50%; color:#b47a10;
 background:#fff; box-shadow:0 2px 5px #172c461c; transform:translateX(0); transition:transform .17s cubic-bezier(.2,.8,.2,1),background .16s; }
.theme-symbol { display:block; font:700 16px/1 "Segoe UI Symbol",sans-serif; transform:translateY(-.25px); }
.theme-switch input:checked + .theme-track { background:linear-gradient(135deg,#344b68,#202d40); border-color:#536b8a; }
.theme-switch input:checked + .theme-track .theme-thumb { transform:translateX(27px); color:#fff; background:#79a9eb; }
.theme-switch input:focus-visible + .theme-track { outline:3px solid color-mix(in srgb,var(--accent) 35%,transparent); outline-offset:3px; }
.settings-empty-search { padding:28px; margin-top:12px; }
.settings-empty-search p { margin-bottom:0; color:var(--muted); }
.settings-empty-search[hidden], .settings-backdrop[hidden] { display:none !important; }
.settings-backdrop { position:fixed; inset:0; z-index:49; background:rgba(9,15,25,.46); backdrop-filter:blur(2px); }
@media (max-width:1000px) {
 .settings-layout { grid-template-columns:178px minmax(0,1fr); gap:11px; }
 .settings-sidebar { padding:7px; }
 .setting-row { gap:10px; }
 .setting-control:not([type=checkbox]) { width:48%; }
}
@media (max-width:850px) {
 .settings-topbar { align-items:stretch; flex-wrap:wrap; }
 .settings-menu-toggle { display:inline-flex; align-items:center; gap:8px; }
 .settings-search-wrap { min-width:170px; }
 .settings-save-status { width:100%; }
 .settings-layout { grid-template-columns:minmax(0,1fr); }
 .settings-sidebar { display:none; position:fixed; top:12px; bottom:12px; left:12px; z-index:50;
   width:min(286px,calc(100vw - 48px)); overflow:auto; align-self:auto; }
 body.settings-menu-open .settings-sidebar { display:flex; animation:settings-drawer-in .16s ease-out; }
 .settings-menu-close { display:inline-flex; }
 .settings-sidebar-heading { position:sticky; top:0; background:var(--surface); z-index:1; }
 @keyframes settings-drawer-in { from { opacity:.6; transform:translateX(-8px); } to { opacity:1; transform:translateX(0); } }
 .setting-row { align-items:flex-start; }
 .setting-control:not([type=checkbox]) { width:50%; flex-basis:50%; }
 .setting-input-with-button { flex-basis:52%; }
}
@media (max-width:560px) {
 .settings-topbar { gap:7px; }
 .settings-menu-toggle { min-height:38px; padding:6px 8px; }
 .settings-menu-toggle span:last-child { font-size:11px; }
 .settings-search-wrap { min-width:0; padding:0 8px; }
 .settings-search-wrap kbd { display:none; }
 .settings-section-head h2 { font-size:20px; }
 .setting-row { flex-direction:column; align-items:stretch; gap:9px; }
 .setting-control:not([type=checkbox]), .setting-input-with-button { width:100%; max-width:none; flex-basis:auto; }
 .theme-switch { align-self:flex-start; }
}

.toast { position:fixed; bottom:18px; left:50%; transform:translate(-50%,20px); opacity:0; pointer-events:none;
 max-width:min(600px,calc(100vw - 28px)); padding:11px 15px; border:1px solid var(--line); border-radius:11px;
 background:var(--surface-2); box-shadow:var(--shadow); transition:all .18s; z-index:20; }
.toast.show { transform:translate(-50%,0); opacity:1; }
@media (max-width:800px) {
 body { padding:14px 12px 28px; }
 header { align-items:flex-start; flex-direction:column; gap:14px; }
 .nav { width:100%; display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); }
 .nav-link { padding:8px 4px; font-size:12px; }
 .layout { grid-template-columns:minmax(0,1fr); }
 aside { order:2; }
 .form-grid { grid-template-columns:minmax(0,1fr); }
 .check-grid { grid-template-columns:minmax(0,1fr); }
 .page-head { align-items:flex-start; flex-direction:column; }
}

/* Premium, consistent surfaces for the built-in pages. */
html, body {
  background:
    radial-gradient(ellipse at 8% -6%, color-mix(in srgb,var(--accent) 8%,transparent), transparent 32rem),
    var(--bg);
}
body { padding:clamp(14px,2vw,26px) clamp(12px,3vw,34px) 34px; }
.app { max-width:1160px; }
header {
  padding:14px 16px; margin-bottom:22px; border:1px solid var(--line);
  border-radius:20px; background:var(--surface); box-shadow:var(--shadow);
  backdrop-filter:blur(16px);
}
.brand { gap:11px; }
.brand-mark { border-radius:15px; box-shadow:0 8px 20px rgba(28,101,188,.20); }
.nav { gap:3px; padding:4px; border-radius:14px; background:var(--surface-2); box-shadow:none; }
.nav-link { min-height:34px; transition:color .15s,background .15s,transform .15s; }
.nav-link:active { transform:translateY(1px); }
.nav-link.active { box-shadow:inset 0 0 0 1px color-mix(in srgb,var(--accent) 18%,transparent); }
.page-head { margin-bottom:15px; }
.page-head h2 { font-size:22px; letter-spacing:-.4px; }
.page-tools { display:flex; align-items:center; justify-content:flex-end; flex-wrap:wrap; gap:8px; }
.page-tools > input { width:min(280px,64vw); flex:0 1 280px; }
.panel { border-radius:17px; box-shadow:0 10px 28px rgba(25,50,80,.055); }
html.dark .panel { box-shadow:0 12px 30px rgba(0,0,0,.16); }
.panel-head { padding:16px 18px; background:linear-gradient(115deg,color-mix(in srgb,var(--accent) 5%,var(--surface)),var(--surface)); }
.panel-body { padding:18px; }
.history-item, .download-item {
  padding:16px; background:var(--surface-2); border-radius:15px;
  box-shadow:0 4px 14px rgba(25,50,80,.035);
  transition:border-color .16s,box-shadow .16s,transform .16s;
}
.history-item:hover, .download-item:hover {
  border-color:color-mix(in srgb,var(--accent) 45%,var(--line));
  box-shadow:var(--shadow); transform:translateY(-1px);
}
.item-title { line-height:1.4; }
.status-pill { white-space:nowrap; border-radius:999px; padding:5px 10px; }
.actions button { min-height:32px; font-weight:650; }
.progress-track { height:7px; border-radius:999px; }
.progress-value { border-radius:999px; }
.settings-sidebar { backdrop-filter:blur(14px); }
.settings-panel { border-radius:15px; }
.settings-panel .panel-head { padding:13px 16px; }
.settings-panel .panel-body { padding:6px 16px; }
.setting-row { transition:background .14s; }
.setting-row:focus-within { background:color-mix(in srgb,var(--accent) 5%,transparent); border-radius:10px; }
.stat-strip {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr));
  gap:10px; margin:0 0 16px;
}
.stat-card {
  display:flex; align-items:center; gap:12px; min-width:0; padding:13px 15px;
  border:1px solid var(--line); border-radius:15px; background:var(--surface);
  box-shadow:var(--shadow);
}
.stat-icon {
  display:grid; place-items:center; flex:0 0 36px; width:36px; height:36px;
  border-radius:11px; color:var(--accent); background:var(--accent-soft);
  font-size:19px; font-weight:800;
}
.stat-copy { display:flex; flex-direction:column; min-width:0; gap:2px; }
.stat-copy strong { font-size:20px; line-height:1.05; letter-spacing:-.45px; }
.stat-copy small { color:var(--muted); font-size:11px; overflow-wrap:anywhere; }
.history-item[hidden], .download-item[hidden] { display:none !important; }
@media (max-width:800px) {
  header { padding:13px; border-radius:17px; }
  .page-tools { width:100%; justify-content:flex-start; }
  .page-tools > input { width:100%; flex:1 1 200px; }
  .stat-strip { grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }
  .stat-card { padding:11px; gap:9px; }
  .stat-icon { flex-basis:31px; width:31px; height:31px; border-radius:10px; }
}
@media (max-width:480px) {
  .stat-strip { grid-template-columns:minmax(0,1fr); }
  .stat-card { padding:12px 14px; }
  .page-head h2 { font-size:20px; }
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
            f'<label class="setting-row setting-toggle" data-search="{_e(name.replace("_", " ") + " " + label + " " + detail)}">'
            f'<span class="setting-copy"><strong>{_e(label)}</strong><small>{_e(detail)}</small></span>'
            f'<input class="setting-control" id="{_e(name)}" name="{_e(name)}" type="checkbox"{checked}>'
            f'<span class="check-ui" aria-hidden="true"></span></label>'
        )

    sections = (
        ("general", "General", "home homepage startup new tab search engine", "⌂"),
        ("appearance", "Appearance", "theme light dark colors appearance mode tabs title bar layout", "◐"),
        ("privacy", "Privacy & security", "private history cookies compatibility profile", "◇"),
        ("performance", "Performance", "hardware gpu acceleration rendering restart", "↯"),
        ("downloads", "Downloads", "download directory folder proxy panel startup", "↓"),
    )
    category_buttons = "".join(
        f'<button type="button" class="settings-category{" active" if key == "general" else ""}" '
        f'data-section="{key}" data-search="{_e(search + " " + label)}">'
        f'<span class="category-icon" aria-hidden="true">{icon}</span><span>{label}</span></button>'
        for key, label, search, icon in sections
    )

    body = f"""
<div class="settings-topbar">
  <button type="button" id="settings-menu-toggle" class="settings-menu-toggle" aria-expanded="false" aria-controls="settings-sidebar">
    <span aria-hidden="true">☰</span><span>Categories</span>
  </button>
  <label class="settings-search-wrap" for="settings-search">
    <span class="search-glyph" aria-hidden="true">⌕</span>
    <input id="settings-search" type="search" placeholder="Search settings…" autocomplete="off" aria-label="Search settings">
    <kbd>Ctrl K</kbd>
  </label>
  <span id="settings-save-status" class="settings-save-status" role="status" aria-live="polite">Changes save automatically</span>
</div>

<div class="settings-layout">
  <div id="settings-backdrop" class="settings-backdrop" hidden></div>
  <nav id="settings-sidebar" class="settings-sidebar" aria-label="Settings categories">
    <div class="settings-sidebar-heading"><span>SETTINGS</span>
      <button type="button" id="settings-menu-close" class="settings-menu-close" aria-label="Close settings categories">×</button>
    </div>
    {category_buttons}
    <p id="settings-no-categories" class="settings-no-categories" hidden>No matching categories</p>
  </nav>

  <main class="settings-main">
    <section class="settings-section active" id="section-general" data-section="general" aria-labelledby="heading-general">
      <div class="settings-section-head"><span class="section-kicker">YOUR BROWSER</span><h2 id="heading-general">General</h2>
        <p>Set your homepage, new-tab behavior, and search provider.</p></div>
      <section class="panel settings-panel">
        <div class="panel-head"><h3>Startup & browsing</h3><p>Changes are applied and saved to this profile as you make them.</p></div>
        <div class="panel-body setting-list">
          <div class="setting-row" data-search="homepage home website start page address">
            <div class="setting-copy"><label for="homepage">Homepage</label><small>A web address or an ARMA page such as arma://dashboard/.</small></div>
            <input class="setting-control" id="homepage" name="homepage" type="url" value="{_e(settings.homepage)}" placeholder="https://example.com">
          </div>
          <div class="setting-row" data-search="startup page launch open browser">
            <div class="setting-copy"><label for="startup_page">When browser opens</label><small>Choose the page shown when a new browser session starts.</small></div>
            <select class="setting-control" id="startup_page" name="startup_page">
              <option value="dashboard"{" selected" if settings.startup_page == "dashboard" else ""}>ARMA dashboard</option>
              <option value="homepage"{" selected" if settings.startup_page == "homepage" else ""}>Homepage</option>
            </select>
          </div>
          <div class="setting-row" data-search="new tab page open tab">
            <div class="setting-copy"><label for="new_tab_page">New tab page</label><small>Choose what opens in a fresh tab.</small></div>
            <select class="setting-control" id="new_tab_page" name="new_tab_page">
              <option value="dashboard"{" selected" if settings.new_tab_page == "dashboard" else ""}>ARMA dashboard</option>
              <option value="homepage"{" selected" if settings.new_tab_page == "homepage" else ""}>Homepage</option>
            </select>
          </div>
          <div class="setting-row" data-search="search engine google duckduckgo bing web search">
            <div class="setting-copy"><label for="default_search_engine">Search engine</label><small>Used when you type a search instead of an address.</small></div>
            <select class="setting-control" id="default_search_engine" name="default_search_engine">{engine_options}</select>
          </div>
        </div>
      </section>
    </section>

    <section class="settings-section" id="section-appearance" data-section="appearance" aria-labelledby="heading-appearance">
      <div class="settings-section-head"><span class="section-kicker">PERSONALIZE</span><h2 id="heading-appearance">Appearance</h2>
        <p>Choose the color theme for the browser chrome and built-in pages.</p></div>
      <section class="panel settings-panel">
        <div class="panel-head"><h3>Color theme</h3><p>The theme updates immediately and is remembered for this profile.</p></div>
        <div class="panel-body setting-list">
          <div class="setting-row theme-setting-row" data-search="dark light theme appearance color mode sun moon">
            <div class="setting-copy"><label for="dark_mode">Dark appearance</label><small>Slide the switch to move between light and dark themes.</small></div>
            <label class="theme-switch" aria-label="Toggle dark appearance">
              <input class="setting-control" id="dark_mode" name="dark_mode" type="checkbox" role="switch"{" checked" if settings.dark_mode else ""}>
              <span class="theme-track"><span class="theme-thumb"><span class="theme-symbol">{"☾" if settings.dark_mode else "☀"}</span></span></span>
            </label>
          </div>
        </div>
      </section>
      <section class="panel settings-panel">
        <div class="panel-head"><h3>Tab layout</h3><p>Choose how the tab strip fits into the browser chrome.</p></div>
        <div class="panel-body setting-list">
          {checkbox("tabs_in_title_bar", "Show tabs in the title bar", "Move tabs to the top row, hide the ARMA Browser label, and keep the window controls on the right.", settings.tabs_in_title_bar)}
        </div>
      </section>
      <section class="panel settings-panel">
        <div class="panel-head"><h3>Site compatibility</h3><p>Some websites behave better with a standard Chromium user-agent.</p></div>
        <div class="panel-body setting-list">
          {checkbox("site_compatibility_mode", "Use a standard browser identity", "Hides the QtWebEngine product marker; it does not install extensions.", settings.site_compatibility_mode)}
        </div>
      </section>
    </section>

    <section class="settings-section" id="section-privacy" data-section="privacy" aria-labelledby="heading-privacy">
      <div class="settings-section-head"><span class="section-kicker">YOUR DATA</span><h2 id="heading-privacy">Privacy & security</h2>
        <p>Control which browsing data is kept between sessions.</p></div>
      <section class="panel settings-panel">
        <div class="panel-head"><h3>Browsing data</h3><p>These switches take effect as soon as you change them.</p></div>
        <div class="panel-body setting-list">
          {checkbox("private_mode", "Private browsing", "Use an off-the-record profile for this browser profile.", settings.private_mode)}
          {checkbox("save_history", "Save browsing history", "Keep visited pages for this profile.", settings.save_history)}
          {checkbox("save_cookies", "Keep cookies between sessions", "Save website cookies between browser runs.", settings.save_cookies)}
        </div>
      </section>
    </section>

      <section class="panel settings-panel">
        <div class="panel-head"><h3>Browser profiles</h3><p>Switch, create, or personalize separate browsing profiles without opening another window.</p></div>
        <div class="panel-body">
          <p class="field-hint">Each profile keeps its own browser settings, bookmarks, history and site storage.</p>
          <a class="button" href="arma://profile/">Manage profiles <span aria-hidden="true">↗</span></a>
        </div>
      </section>

    <section class="settings-section" id="section-performance" data-section="performance" aria-labelledby="heading-performance">
      <div class="settings-section-head"><span class="section-kicker">RENDERING</span><h2 id="heading-performance">Performance</h2>
        <p>Choose how Chromium renders web pages.</p></div>
      <section class="panel settings-panel">
        <div class="panel-head"><h3>Graphics</h3><p>Hardware acceleration changes require restarting the browser to fully take effect.</p></div>
        <div class="panel-body setting-list">
          {checkbox("hardware_acceleration", "Use hardware acceleration", "Use the GPU where supported. A restart is needed after changing this setting.", settings.hardware_acceleration)}
          {checkbox("webgpu_enabled", "Enable WebGPU", "Experimental web graphics API. Restart required; enable it only if this system can create a WebGPU context.", settings.webgpu_enabled)}
        </div>
      </section>
      <p class="footer-note">If Chromium reports “Failed to create WebGPU Context Provider”, leave WebGPU disabled to avoid repeated context creation failures while keeping normal GPU composition available. Graphics options are read at startup and require a browser restart.</p>
    </section>

    <section class="settings-section" id="section-downloads" data-section="downloads" aria-labelledby="heading-downloads">
      <div class="settings-section-head"><span class="section-kicker">FILES</span><h2 id="heading-downloads">Downloads</h2>
        <p>Manage where files are stored and whether the Tor side panel opens with the browser.</p></div>
      <section class="panel settings-panel">
        <div class="panel-head"><h3>Download location</h3><p>The download manager and its left-side drawer share this folder.</p></div>
        <div class="panel-body setting-list">
          <div class="setting-row" data-search="download folder directory path location save files">
            <div class="setting-copy"><label for="download_folder">Download folder</label><small>Changes are saved after you finish typing or leave the field.</small></div>
            <div class="setting-input-with-button"><input class="setting-control" id="download_folder" name="download_folder" type="text" value="{_e(settings.download_folder)}">
              <button type="button" id="browse-folder" aria-label="Browse for download folder">Browse…</button></div>
          </div>
        </div>
      </section>
      <section class="panel settings-panel">
        <div class="panel-head"><h3>Tor panel</h3><p>Only controls panel visibility. Tor routing must still be connected separately.</p></div>
        <div class="panel-body setting-list">
          {checkbox("proxy_panel_visible", "Show Tor panel when the browser opens", "Remember the Tor panel's open or closed state on startup.", settings.proxy_panel_visible)}
        </div>
      </section>
    </section>
    <div id="settings-empty-search" class="panel settings-empty-search" hidden><strong>No matching settings</strong><p>Try a different term such as “theme”, “history”, or “download”.</p></div>
  </main>
</div>

<script>
(() => {{
  const sectionButtons = Array.from(document.querySelectorAll('.settings-category'));
  const sections = Array.from(document.querySelectorAll('.settings-section'));
  const search = document.getElementById('settings-search');
  const sidebar = document.getElementById('settings-sidebar');
  const toggle = document.getElementById('settings-menu-toggle');
  const closeButton = document.getElementById('settings-menu-close');
  const backdrop = document.getElementById('settings-backdrop');
  const status = document.getElementById('settings-save-status');
  const empty = document.getElementById('settings-empty-search');
  const debounceTimers = new Map();
  let statusTimer = null;

  function mobileMenu() {{ return window.matchMedia('(max-width: 850px)').matches; }}
  function closeMenu() {{
    document.body.classList.remove('settings-menu-open');
    toggle.setAttribute('aria-expanded', 'false');
    backdrop.hidden = true;
  }}
  function openMenu() {{
    if (!mobileMenu()) return;
    document.body.classList.add('settings-menu-open');
    toggle.setAttribute('aria-expanded', 'true');
    backdrop.hidden = false;
  }}
  function chooseSection(key) {{
    const target = sections.find(section => section.dataset.section === key);
    if (!target || target.hidden) return;
    sections.forEach(section => section.classList.toggle('active', section === target));
    sectionButtons.forEach(button => {{
      const active = button.dataset.section === key;
      button.classList.toggle('active', active);
      button.setAttribute('aria-current', active ? 'page' : 'false');
    }});
    if (mobileMenu()) closeMenu();
  }}
  function filterSettings(query) {{
    const needle = String(query || '').trim().toLocaleLowerCase();
    const matchingSections = [];
    sections.forEach(section => {{
      let matchingRows = 0;
      section.querySelectorAll('.setting-row').forEach(row => {{
        const content = (row.dataset.search || '') + ' ' + row.textContent + ' ' +
          Array.from(row.querySelectorAll('input,select')).map(input => input.value || input.name).join(' ');
        const matches = !needle || content.toLocaleLowerCase().includes(needle);
        row.hidden = !matches;
        if (matches) matchingRows += 1;
      }});
      const matches = !needle || matchingRows > 0 ||
        (section.id + ' ' + (section.querySelector('h2')?.textContent || '')).toLocaleLowerCase().includes(needle);
      if (matches) matchingSections.push(section.dataset.section);
    }});
    sectionButtons.forEach(button => {{
      const haystack = (button.dataset.search || '') + ' ' + button.textContent;
      button.hidden = Boolean(needle) && !haystack.toLocaleLowerCase().includes(needle) &&
        !matchingSections.includes(button.dataset.section);
    }});
    document.querySelectorAll('.settings-sidebar-heading').forEach(element => {{
      element.hidden = Boolean(needle) && !sectionButtons.some(button => !button.hidden);
    }});
    const active = sections.find(section => section.classList.contains('active'));
    if (needle && (!active || !matchingSections.includes(active.dataset.section)) && matchingSections.length) {{
      chooseSection(matchingSections[0]);
    }}
    if (needle && matchingSections.length === 0) {{
      sections.forEach(section => section.classList.remove('active'));
    }} else if (!needle && !sections.some(section => section.classList.contains('active'))) {{
      chooseSection('general');
    }}
    empty.hidden = !needle || matchingSections.length > 0;
    sidebar.classList.toggle('searching', Boolean(needle));
  }}
  function showStatus(message, error = false) {{
    status.textContent = message;
    status.classList.toggle('error', Boolean(error));
    status.classList.toggle('saving', message === 'Saving…');
    clearTimeout(statusTimer);
    if (message !== 'Saving…') {{
      statusTimer = setTimeout(() => {{
        if (!status.classList.contains('error')) status.textContent = 'Changes save automatically';
      }}, 2400);
    }}
  }}
  window.armaSettingSaved = (name, message, failed = false) => {{
    if (name === 'dark_mode') {{
      const input = document.getElementById('dark_mode');
      const symbol = document.querySelector('.theme-symbol');
      if (input && symbol) symbol.textContent = input.checked ? '☾' : '☀';
    }}
    showStatus(message || (failed ? 'Could not save this setting' : 'Setting saved'), failed);
  }};
  function submitSetting(input, immediate = false) {{
    const name = input.name;
    if (!name) return;
    const value = input.type === 'checkbox' ? Boolean(input.checked) : input.value;
    if (name === 'dark_mode') {{
      const symbol = document.querySelector('.theme-symbol');
      if (symbol) symbol.textContent = input.checked ? '☾' : '☀';
      window.armaSetTheme(input.checked ? 'dark' : 'light');
    }}
    showStatus('Saving…');
    const send = () => window.armaAction('set_browser_setting', {{name, value}});
    if (debounceTimers.has(name)) clearTimeout(debounceTimers.get(name));
    if (immediate || input.type === 'checkbox' || input.tagName === 'SELECT') {{
      send();
    }} else {{
      const timer = setTimeout(send, 420);
      debounceTimers.set(name, timer);
    }}
  }}

  sectionButtons.forEach(button => button.addEventListener('click', () => chooseSection(button.dataset.section)));
  toggle.addEventListener('click', () => {{
    if (document.body.classList.contains('settings-menu-open')) closeMenu();
    else openMenu();
  }});
  closeButton.addEventListener('click', closeMenu);
  backdrop.addEventListener('click', closeMenu);
  search.addEventListener('input', () => filterSettings(search.value));
  search.addEventListener('keydown', event => {{
    if (event.key === 'Escape') {{ search.value = ''; filterSettings(''); search.blur(); }}
  }});
  document.addEventListener('keydown', event => {{
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {{
      event.preventDefault(); search.focus(); if (mobileMenu()) openMenu();
    }}
    if (event.key === 'Escape') closeMenu();
  }});
  document.querySelectorAll('.setting-control').forEach(input => {{
    if (input.type === 'checkbox' || input.tagName === 'SELECT') {{
      input.addEventListener('change', () => submitSetting(input, true));
    }} else {{
      input.addEventListener('input', () => submitSetting(input, false));
      input.addEventListener('blur', () => submitSetting(input, true));
    }}
  }});
  document.getElementById('browse-folder').addEventListener('click', () => window.armaAction('browse_download_folder'));
  window.setDownloadFolder = value => {{
    const input = document.getElementById('download_folder');
    input.value = String(value || '');
    submitSetting(input, true);
  }};
  window.addEventListener('resize', () => {{ if (!mobileMenu()) closeMenu(); }});
  chooseSection('general');
}})();
</script>"""
    return _shell(browser, "Settings", "Personalize browsing, privacy, performance, and files.", body, "settings")

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
<div class="page-head"><div><h2>Recent pages</h2><p class="subtitle">Search addresses and manage individual visits.</p></div>
  <div class="page-tools" role="search">
    <input id="history-filter" type="search" placeholder="Filter by URL…" aria-label="Filter history">
    {_action("Clear history", "history_clear", {}, "danger")}
  </div>
</div>
<div class="stat-strip" aria-label="Browsing history summary">
  <div class="stat-card"><span class="stat-icon" aria-hidden="true">◷</span><span class="stat-copy"><strong>{len(history.history)}</strong><small>Saved addresses</small></span></div>
  <div class="stat-card"><span class="stat-icon" aria-hidden="true">↗</span><span class="stat-copy"><strong>{total_visits}</strong><small>Recorded visits</small></span></div>
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


def _bookmarks_page(browser) -> str:
    manager = getattr(browser, "bookmarks_manager", None)
    if manager is None:
        body = """
<div class="layout"><main><section class="panel"><div class="empty">
  <div class="glyph">✦</div><strong>Bookmarks are unavailable</strong>
  <p>The current browser profile could not open its bookmark store.</p>
  <a class="button" href="arma://dashboard/">Back to Home</a>
</div></section></main>
<aside><h2>Saved pages</h2><p>Your bookmarks are stored per browser profile.</p></aside></div>"""
        return _shell(browser, "Bookmarks", "Keep your favorite pages close at hand.", body, "bookmarks")

    try:
        records = manager.list_bookmarks()
    except (OSError, RuntimeError, TypeError, ValueError):
        records = []
        manager_unavailable = True
    else:
        manager_unavailable = False

    cards = []
    internal_count = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        bookmark_id = raw.get("id")
        title = raw.get("title")
        url = raw.get("url")
        if not all(isinstance(value, str) and value for value in (bookmark_id, title, url)):
            continue
        if url.startswith("arma://"):
            internal_count += 1
        payload = {"id": bookmark_id}
        cards.append(
            f'<article class="history-item bookmark-item" data-filter-text="{_e((title + " " + url).casefold())}">'
            f'<div class="item-top"><div style="min-width:0">'
            f'<div class="item-title">{_e(title)}</div>'
            f'<div class="item-sub">{_e(url)}</div></div>'
            f'<span class="status-pill">{_e("ARMA page" if url.startswith("arma://") else "Website")}</span></div>'
            f'<div class="actions">'
            + _action("Open", "bookmark_open", payload, "primary")
            + _action("Open in new tab", "bookmark_open_new", payload)
            + _action("Remove", "bookmark_remove", payload, "danger")
            + '</div></article>'
        )

    if manager_unavailable:
        listing = (
            '<div class="empty"><div class="glyph">!</div><strong>Could not load bookmarks</strong>'
            '<p>Try refreshing this page. Your saved data has not been changed.</p></div>'
        )
    else:
        listing = "".join(cards) or (
            '<div class="empty"><div class="glyph">✦</div><strong>No bookmarks yet</strong>'
            '<p>Use the bookmark star in the browser toolbar to save a website or ARMA page.</p>'
            '<a class="button primary" href="arma://dashboard/">Explore your Home page</a></div>'
        )

    website_count = max(0, len(cards) - internal_count)
    body = f"""
<div class="page-head">
  <div><h2>Saved pages</h2><p class="subtitle">Find, open, or remove bookmarks from the current profile.</p></div>
  <div class="page-tools" role="search">
    <input id="bookmark-filter" type="search" placeholder="Search bookmarks…" aria-label="Search bookmarks">
    <button type="button" data-action="bookmarks_refresh">Refresh</button>
  </div>
</div>
<div class="stat-strip" aria-label="Bookmark summary">
  <div class="stat-card"><span class="stat-icon" aria-hidden="true">✦</span><span class="stat-copy"><strong>{len(cards)}</strong><small>Saved items</small></span></div>
  <div class="stat-card"><span class="stat-icon" aria-hidden="true">↗</span><span class="stat-copy"><strong>{website_count}</strong><small>Websites</small></span></div>
  <div class="stat-card"><span class="stat-icon" aria-hidden="true">A</span><span class="stat-copy"><strong>{internal_count}</strong><small>ARMA pages</small></span></div>
</div>
<div id="bookmark-list" class="list">{listing}</div>
<p class="footer-note">Bookmarks belong to this browser profile. “Open in new tab” keeps this page in place; removing a bookmark does not delete the website or its files.</p>
<script>
(() => {{
  const filter = document.getElementById('bookmark-filter');
  if (!filter) return;
  filter.addEventListener('input', () => {{
    const needle = filter.value.trim().toLocaleLowerCase();
    document.querySelectorAll('.bookmark-item').forEach(item => {{
      item.hidden = !item.dataset.filterText.includes(needle);
    }});
  }});
}})();
</script>"""
    return _shell(browser, "Bookmarks", "Keep your favorite pages close at hand.", body, "bookmarks")


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
<div class="page-head"><div><h2>Download manager</h2><p class="subtitle">Manage active transfers and completed files in one place.</p></div>
  <div class="page-tools">
    <button type="button" data-action="downloads_refresh">Refresh</button>
    {_action("Clear finished", "downloads_clear_finished", {}, "danger")}
  </div>
</div>
<div class="stat-strip" aria-label="Download summary">
  <div class="stat-card"><span class="stat-icon" aria-hidden="true">↓</span><span class="stat-copy"><strong>{counts['downloading'] + counts['requested']}</strong><small>Active transfers</small></span></div>
  <div class="stat-card"><span class="stat-icon" aria-hidden="true">✓</span><span class="stat-copy"><strong>{counts['completed']}</strong><small>Completed</small></span></div>
  <div class="stat-card"><span class="stat-icon" aria-hidden="true">!</span><span class="stat-copy"><strong>{counts['failed'] + counts['cancelled']}</strong><small>Failed or cancelled</small></span></div>
</div>
<div class="list">{main_content}</div>
<p class="footer-note">Download records are kept in memory for the active browser profile. Deleting a completed file is restricted to files within the configured download folder.</p>"""
    return _shell(browser, "Downloads", "Track progress and manage downloaded files.", body, "downloads")



def _profile_page(browser) -> str:
    """Render a profile manager inside the current browser tab."""
    settings = browser.settings
    selected = str(getattr(browser, "selected_profile", "Guest") or "Guest")
    navbar = getattr(browser, "navbar", None)
    configured = getattr(navbar, "profiles", None) or getattr(settings, "profiles_list", None) or ["Guest"]
    profiles: list[str] = []
    seen: set[str] = set()
    for raw_name in configured:
        try:
            name = validate_profile_name(raw_name)
        except ValueError:
            continue
        if name.casefold() not in seen:
            profiles.append(name)
            seen.add(name.casefold())
    if selected and selected not in profiles:
        profiles.insert(0, selected)
    if not profiles:
        profiles = [selected or "Guest"]

    def avatar_markup(name: str, *, large: bool = False) -> str:
        classes = "profile-avatar profile-avatar-large" if large else "profile-avatar"
        fallback = _e("".join(part[0] for part in name.split()[:2]).upper() or "A")
        image_path = user_data_path("profile_data", name, "profile", "image.png")
        try:
            if os.path.isfile(image_path) and os.path.getsize(image_path) <= 1_500_000:
                with open(image_path, "rb") as stream:
                    encoded = base64.b64encode(stream.read()).decode("ascii")
                return f'<span class="{classes}"><img alt="" src="data:image/png;base64,{encoded}"></span>'
        except OSError:
            pass
        return f'<span class="{classes}"><span class="profile-avatar-fallback">{fallback}</span></span>'

    cards = []
    for name in profiles:
        active = name == selected
        is_last = len(profiles) <= 1
        controls = (
            '<span class="profile-active-pill"><span aria-hidden="true">✓</span> Current profile</span>'
            if active else _action("Switch to profile", "profile_switch", {"name": name}, "primary")
        )
        if not active and not is_last:
            controls += _action("Remove", "profile_delete", {"name": name}, "danger")
        hint = "This is the profile currently used by your browser." if active else "Settings and browsing data stay separate from other profiles."
        cards.append(f"""
          <article class="profile-card{" profile-card-active" if active else ""}">
            {avatar_markup(name)}
            <div class="profile-card-copy">
              <div class="profile-card-title"><h3>{_e(name)}</h3>{"<span class='profile-active-dot' aria-label='Active'></span>" if active else ""}</div>
              <p>{_e(hint)}</p>
            </div>
            <div class="profile-card-actions">{controls}</div>
          </article>
        """)
    profile_rows = "".join(cards)
    current_avatar_path = user_data_path("profile_data", selected, "profile", "image.png")
    existing_avatar = ""
    try:
        if os.path.isfile(current_avatar_path) and os.path.getsize(current_avatar_path) <= 1_500_000:
            with open(current_avatar_path, "rb") as stream:
                encoded = base64.b64encode(stream.read()).decode("ascii")
            existing_avatar = f'<img id="profile-existing-avatar" alt="" hidden src="data:image/png;base64,{encoded}">'
    except OSError:
        existing_avatar = ""

    body = f"""
<style>
.profile-layout {{ display:grid; grid-template-columns:minmax(0,1.45fr) minmax(270px, .8fr); gap:16px; align-items:start; }}
.profile-stack {{ display:flex; flex-direction:column; gap:10px; }}
.profile-card {{ display:flex; align-items:center; gap:13px; min-width:0; padding:14px; border:1px solid var(--line); border-radius:14px; background:var(--surface); }}
.profile-card-active {{ border-color:var(--accent); box-shadow:0 0 0 2px color-mix(in srgb,var(--accent) 12%,transparent); }}
.profile-avatar {{ width:48px; height:48px; flex:0 0 48px; overflow:hidden; display:grid; place-items:center; border-radius:50%; border:1px solid var(--line); background:var(--accent-soft); color:var(--accent); font-weight:800; }}
.profile-avatar-large {{ width:148px; height:148px; flex-basis:148px; border-width:2px; }}
.profile-avatar img {{ width:100%; height:100%; display:block; object-fit:cover; border-radius:50%; }}
.profile-avatar-fallback {{ display:grid; place-items:center; width:100%; height:100%; font-size:17px; }}
.profile-avatar-large .profile-avatar-fallback {{ font-size:44px; }}
.profile-card-copy {{ flex:1; min-width:0; }}
.profile-card-title {{ display:flex; align-items:center; gap:8px; }}
.profile-card-title h3 {{ margin:0; font-size:14px; overflow-wrap:anywhere; }}
.profile-card-copy p {{ margin:4px 0 0; color:var(--muted); font-size:12px; }}
.profile-active-dot {{ width:8px; height:8px; background:#35b77b; border-radius:50%; }}
.profile-card-actions {{ display:flex; flex-wrap:wrap; gap:7px; align-items:center; justify-content:flex-end; }}
.profile-active-pill {{ display:inline-flex; align-items:center; gap:6px; color:var(--accent); background:var(--accent-soft); font-size:11px; font-weight:750; border-radius:8px; padding:7px 9px; white-space:nowrap; }}
.profile-create-form {{ display:flex; align-items:center; gap:9px; }}
.profile-create-form input {{ flex:1; width:100%; min-width:0; }}
.profile-editor {{ display:flex; flex-direction:column; gap:14px; }}
.profile-editor-head {{ display:flex; flex-direction:column; align-items:center; text-align:center; gap:5px; }}
.profile-editor-head h3 {{ margin:0; }}
.profile-editor-head p {{ color:var(--muted); margin:0; font-size:12px; }}
#profile-avatar-canvas {{ width:190px; height:190px; border-radius:50%; background:var(--surface-2); border:1px solid var(--line); touch-action:none; cursor:grab; }}
#profile-avatar-canvas:active {{ cursor:grabbing; }}
.profile-editor-controls {{ display:grid; grid-template-columns:1fr auto; gap:8px; align-items:center; }}
.profile-editor-controls input[type=range] {{ width:100%; accent-color:var(--accent); }}
.profile-help {{ color:var(--muted); font-size:11px; margin:0; }}
@media (max-width:900px) {{ .profile-layout {{ grid-template-columns:minmax(0,1fr); }} .profile-card {{ flex-wrap:wrap; }} .profile-card-actions {{ width:100%; justify-content:flex-start; }} }}
@media (max-width:520px) {{ .profile-create-form {{ flex-direction:column; align-items:stretch; }} .profile-avatar-large {{ width:116px; height:116px; flex-basis:116px; }} }}
</style>
<div class="page-head">
  <div><h2>Manage profiles</h2><p class="subtitle">Switch browsing identities and personalize each profile without leaving the browser.</p></div>
</div>
<div class="profile-layout">
  <main class="profile-stack">
    <section class="panel">
      <div class="panel-head"><h3>Your profiles</h3><p>{len(profiles)} profile{"s" if len(profiles) != 1 else ""} · the selected profile controls the current browser session.</p></div>
      <div class="panel-body profile-stack">{profile_rows}</div>
    </section>
    <section class="panel">
      <div class="panel-head"><h3>Create a profile</h3><p>A fresh profile starts with default browser preferences and separate website storage.</p></div>
      <div class="panel-body">
        <form id="profile-create-form" class="profile-create-form">
          <input id="profile-create-name" name="profile-name" type="text" maxlength="120" autocomplete="off" placeholder="e.g. Work, Study, Personal" aria-label="New profile name" required>
          <button type="submit" class="primary">Create profile</button>
        </form>
        <p class="footer-note">Use a distinct name for each browsing context. Names cannot contain path separators or reserved operating-system characters.</p>
      </div>
    </section>
  </main>
  <aside>
    <div class="profile-editor">
      <div class="profile-editor-head">
        <h2>Profile picture</h2>
        <p>Customize the avatar for <strong>{_e(selected)}</strong>.</p>
      </div>
      {avatar_markup(selected, large=True)}
      <canvas id="profile-avatar-canvas" width="512" height="512" aria-label="Circular profile picture crop preview"></canvas>
      {existing_avatar}
      <input id="profile-image-file" type="file" accept="image/png,image/jpeg,image/webp,image/bmp" hidden>
      <button type="button" id="profile-choose-image">Choose image…</button>
      <div class="profile-editor-controls">
        <label for="profile-image-zoom" class="field-label">Zoom</label>
        <span id="profile-image-zoom-value" class="field-hint">100%</span>
        <input id="profile-image-zoom" type="range" min="100" max="400" step="5" value="100" aria-label="Profile image zoom">
        <span></span>
      </div>
      <div class="actions">
        <button type="button" id="profile-image-reset" class="ghost">Reset crop</button>
        <button type="button" id="profile-image-save" class="primary" disabled>Save picture</button>
        {_action("Remove picture", "profile_avatar_remove", {"name": selected}, "danger")}
      </div>
      <p class="profile-help">Drag the image to reposition it, use the wheel or zoom slider to adjust it, then save. The picture is cropped locally in this page.</p>
    </div>
  </aside>
</div>
<script>
(() => {{
  const createForm = document.getElementById('profile-create-form');
  const nameInput = document.getElementById('profile-create-name');
  createForm.addEventListener('submit', event => {{
    event.preventDefault();
    const name = nameInput.value.trim();
    if (!name) {{ nameInput.focus(); return; }}
    window.armaAction('profile_create', {{name}});
  }});

  const canvas = document.getElementById('profile-avatar-canvas');
  const ctx = canvas.getContext('2d');
  const fileInput = document.getElementById('profile-image-file');
  const chooseButton = document.getElementById('profile-choose-image');
  const resetButton = document.getElementById('profile-image-reset');
  const saveButton = document.getElementById('profile-image-save');
  const zoomSlider = document.getElementById('profile-image-zoom');
  const zoomLabel = document.getElementById('profile-image-zoom-value');
  const oldAvatar = document.getElementById('profile-existing-avatar');
  let sourceImage = null;
  let zoom = 1;
  let offsetX = 0;
  let offsetY = 0;
  let dirty = false;
  let dragging = false;
  let lastPoint = null;

  function paint() {{
    const size = canvas.width;
    ctx.clearRect(0, 0, size, size);
    ctx.save();
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    ctx.clip();
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--accent-soft').trim() || '#e2efff';
    ctx.fillRect(0, 0, size, size);
    if (sourceImage) {{
      const base = Math.max(size / sourceImage.naturalWidth, size / sourceImage.naturalHeight);
      const scale = base * zoom;
      const width = sourceImage.naturalWidth * scale;
      const height = sourceImage.naturalHeight * scale;
      ctx.drawImage(sourceImage, (size - width) / 2 + offsetX, (size - height) / 2 + offsetY, width, height);
    }} else {{
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#176fc1';
      ctx.font = '700 44px Segoe UI, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('ARMA', size / 2, size / 2);
    }}
    ctx.restore();
    zoomLabel.textContent = Math.round(zoom * 100) + '%';
    saveButton.disabled = !sourceImage || !dirty;
  }}

  function loadImage(source) {{
    const image = new Image();
    image.onload = () => {{
      sourceImage = image;
      zoom = 1;
      offsetX = 0;
      offsetY = 0;
      dirty = true;
      zoomSlider.value = '100';
      paint();
    }};
    image.onerror = () => window.armaToast('That image could not be opened.', 'warning');
    image.src = source;
  }}

  if (oldAvatar && oldAvatar.src) {{
    loadImage(oldAvatar.src);
    dirty = false;
  }} else {{
    paint();
  }}

  chooseButton.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {{
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    if (!/^image\/(png|jpeg|webp|bmp)$/.test(file.type) || file.size > 12 * 1024 * 1024) {{
      window.armaToast('Choose a PNG, JPEG, WebP or BMP image under 12 MB.', 'warning');
      fileInput.value = '';
      return;
    }}
    const reader = new FileReader();
    reader.onload = () => loadImage(String(reader.result || ''));
    reader.onerror = () => window.armaToast('The selected image could not be read.', 'warning');
    reader.readAsDataURL(file);
  }});

  zoomSlider.addEventListener('input', () => {{
    zoom = Math.max(1, Math.min(4, Number(zoomSlider.value) / 100));
    dirty = true;
    paint();
  }});

  resetButton.addEventListener('click', () => {{
    if (!sourceImage) return;
    zoom = 1;
    offsetX = 0;
    offsetY = 0;
    zoomSlider.value = '100';
    dirty = true;
    paint();
  }});

  canvas.addEventListener('pointerdown', event => {{
    if (!sourceImage) return;
    dragging = true;
    lastPoint = {{x:event.clientX, y:event.clientY}};
    canvas.setPointerCapture(event.pointerId);
  }});
  canvas.addEventListener('pointermove', event => {{
    if (!dragging || !lastPoint) return;
    const ratioX = canvas.width / Math.max(1, canvas.clientWidth);
    const ratioY = canvas.height / Math.max(1, canvas.clientHeight);
    offsetX += (event.clientX - lastPoint.x) * ratioX;
    offsetY += (event.clientY - lastPoint.y) * ratioY;
    lastPoint = {{x:event.clientX, y:event.clientY}};
    dirty = true;
    paint();
  }});
  function stopDrag() {{ dragging = false; lastPoint = null; }}
  canvas.addEventListener('pointerup', stopDrag);
  canvas.addEventListener('pointercancel', stopDrag);
  canvas.addEventListener('wheel', event => {{
    if (!sourceImage) return;
    event.preventDefault();
    zoom = Math.max(1, Math.min(4, zoom * (event.deltaY < 0 ? 1.08 : 0.92)));
    zoomSlider.value = String(Math.round(zoom * 100));
    dirty = true;
    paint();
  }}, {{passive:false}});

  saveButton.addEventListener('click', () => {{
    if (!sourceImage || !dirty) return;
    const dataUrl = canvas.toDataURL('image/png');
    if (dataUrl.length > 1_900_000) {{
      window.armaToast('The cropped image is too large. Choose a smaller image.', 'warning');
      return;
    }}
    saveButton.disabled = true;
    window.armaAction('profile_avatar_save', {{name:{json.dumps(selected)}, data:dataUrl}});
  }});
}})();
</script>
<p class="footer-note">Removing a profile deletes its saved profile settings, browser storage, bookmarks, history and profile picture. Files already downloaded to your chosen download folder are not deleted.</p>
"""
    return _shell(browser, "Profiles", "Keep work, personal browsing and other contexts neatly separated.", body, "profile")


def render_internal_page(browser, host: str) -> str:
    host = str(host or "").strip().lower()
    if host == "settings":
        return _settings_page(browser)
    if host == "profile":
        return _profile_page(browser)
    if host == "history":
        return _history_page(browser)
    if host == "bookmarks":
        return _bookmarks_page(browser)
    if host == "downloads":
        return _downloads_page(browser)
    raise ValueError(f"Unsupported ARMA internal page: {host}")

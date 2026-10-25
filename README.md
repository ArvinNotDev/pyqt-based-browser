# ARMA Browser

<p align="center">
  <strong>A modern, profile-aware desktop browser built with Python, PySide6, and Qt WebEngine.</strong>
</p>

<p align="center">
  <a href="https://github.com/ArvinNotDev/pyqt-based-browser/actions/workflows/ci.yml"><img src="https://github.com/ArvinNotDev/pyqt-based-browser/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status"></a>
  <img src="https://img.shields.io/badge/Python-3.10%E2%80%933.13-3776AB?logo=python&logoColor=white" alt="Python 3.10–3.13">
  <img src="https://img.shields.io/badge/UI-PySide6%20%2B%20Qt%20WebEngine-41CD52" alt="PySide6 and Qt WebEngine">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
</p>

ARMA Browser brings everyday web navigation, a customizable start page, profile-based settings and data, downloads, and optional proxy/Tor tools into one desktop application. The redesigned browser chrome includes light and dark themes, a compact navigation workspace, and integrated pages for common browser tasks.

> **Beta software:** ARMA Browser is under active development. The Windows x64 one-file executable is unsigned, has no automatic updater, and should be treated as pre-release software. Read the limitations and privacy notes below before relying on it.

## Highlights

- **Modern browser chrome:** custom title bar, responsive tabs, unified address/search field, and coordinated light/dark themes.
- **Personal start page:** configurable shortcuts, bookmarks, recent and recently closed pages, notes, focus timer, wallpaper, and reorderable widgets.
- **Profiles and sessions:** separate profile preferences and browser data, profile management, and optional restoration of normal browsing sessions.
- **Built-in browser tools:** downloads, history, site permissions, find-in-page, zoom, developer tools, PDF export, printing, and page screenshots.
- **Privacy controls:** private browsing, profile-scoped data, and a lightweight host-based ad/tracker blocker.
- **Optional proxy/Tor integration:** proxy configuration, host rules, route exclusions, and bridge-related tools. Actual Tor connectivity depends on local configuration and network access.

## Quick links

- [Download the latest Windows beta](https://github.com/ArvinNotDev/pyqt-based-browser/releases)
- [Install from source](#install-from-source)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Packaging and release process](docs/PACKAGING.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Report a bug or regression](https://github.com/ArvinNotDev/pyqt-based-browser/issues)

## Contents

- [Features](#what-arma-browser-includes)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Support and prerequisites](#support-and-prerequisites)
- [Install from source](#install-from-source)
- [Dependencies and development checks](#dependencies-and-development-checks)
- [Windows beta executable](#windows-beta-executable)
- [Source releases](#source-releases)
- [Scope and troubleshooting](#current-scope-and-troubleshooting)
- [License](#license)

## What ARMA Browser includes

### Browsing and tabs

- Navigate with Back, Forward, Reload, Home, and the combined address and search bar.
- Enter a URL or search phrase in the address bar. Suggestions can use the current profile's browsing history.
- Open multiple pages in tabs, create a tab with the **+** control in the tab strip, and switch tabs with the mouse or keyboard.
- Open the customizable ARMA start page at startup and in new tabs by default. It includes a live clock, URL/search field, reorderable shortcuts, bookmarks, recent pages, recently closed tabs, quick notes, and a focus timer.
- Choose a built-in gradient or import a local dashboard wallpaper. Dashboard appearance, shortcuts, notes, widgets, and timer settings are kept separately for each profile.
- Hover over an inactive tab to preview it. Resize tab widths to fit the window, then use the tab-strip scroll controls when the window has more tabs than can fit.
- Right-click a tab to open, reload, duplicate, copy its address, close it, close other tabs, close tabs to its right, or reopen a recently closed tab.
- Closing the final tab opens a fresh dashboard tab. When **Restore previous session** is enabled, normal browsing tabs and the active profile are saved and restored at startup; private sessions are never stored.

### Bookmarks and history

- Add or remove the current page from bookmarks with the bookmark control or **Ctrl+D**.
- Open and manage bookmarks from the browser menu or bookmarks bar. Bookmark context menus include opening in the current or a new tab, copying the address, editing, and removing the bookmark.
- Browse and search history for the selected profile. The history window can remove a selected address or visit, clear history by date and time, or clear all history.
- History and bookmarks are stored by profile under `profile_data/` in the current working directory.

### Downloads

- Selecting **Downloads** from the browser menu opens an animated drawer on the left side of the browser. Starting a download also opens the drawer and shows a brief in-app notification.
- Download cards show the filename, source URL, progress, and current status. The action menu includes **Copy URL**, **Open file**, **Show in folder**, **Pause/Resume**, **Cancel**, **Remove from list**, and **Delete downloaded file** where each action applies.
- **Clear finished** removes completed, cancelled, and failed entries from the list. Removing an entry does not delete its file. Deleting a completed download asks for confirmation and removes the downloaded file from the configured download folder.
- Downloads use the computer's default Downloads folder unless a different folder is chosen in Settings. A download record exists in memory for the current browser session; the file itself remains in the selected folder. Private browsing also saves downloaded files there, so downloaded files are not automatically private or deleted when the browser closes.
- Once a download request is accepted, the tab that started it closes. The Downloads drawer remains available to track and manage the transfer.
- Closing the browser while downloads are active or paused asks whether to cancel them and close. Choosing **Cancel** keeps the browser open.

### Profiles, privacy, and settings

Settings are scoped to the selected profile. The Settings window includes:

- Homepage, default search URL, and download location.
- Startup and new-tab page behavior, plus dashboard clock, wallpaper, glass, accent, animation, and widget preferences.
- Light or dark appearance.
- History saving, cookie persistence, and private browsing controls.
- Website compatibility mode, which adjusts the browser user-agent string.
- The option to show the proxy panel when the browser starts.
- Restore-session and built-in ad/tracker-blocking preferences.
- Hardware acceleration preference, which requires a restart to change the running Chromium process.
- A built-in keyboard shortcut reference.

Private browsing uses a separate in-memory Qt WebEngine profile and does not keep browsing history, cookies, remembered site permissions, or session tabs between sessions. Downloads are still written to the configured folder, and any downloaded files remain there.

### Proxy and Tor tools

The browser includes an optional proxy panel for local proxy and Tor configuration, along with host blocking and route-exclusion rules. Tor routing depends on a usable Tor expert bundle, available local ports, and network access; bridge routes also need valid bridge lines and compatible transport support. A successful UI setup does not guarantee that a particular network or website will be reachable.

The browser uses its normal Qt/system network route by default. The proxy panel does not start a local proxy until you choose **Connect**. Switching between Tor and regular browsing restarts the browser so WebEngine applies the selected route from profile startup; open tabs are restored. The browser menu can switch the proxy panel, connect the current site directly when Tor routing is active, and toggle Gaming mode. Gaming mode temporarily disables ARMA Browser's registered browser keyboard shortcuts; turn it off from the same menu to restore them.

The browser menu also includes **Site permissions**, **Find in page** (`Ctrl+F`), zoom controls (`Ctrl+=`, `Ctrl+-`, and `Ctrl+0`), **Developer tools** (`F12` or `Ctrl+Shift+I`), **Save page as PDF**, **Print page**, and a screenshot of the currently visible page. Supported site permissions prompt before granting protected capabilities and can be remembered per site; previously saved decisions can be cleared from **Site permissions**.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+T` | Open a new tab |
| `Ctrl+W` | Close the current tab |
| `Ctrl+Shift+T` | Reopen a recently closed tab |
| `Ctrl+Tab` or `Ctrl+PageDown` | Select the next tab |
| `Ctrl+Shift+Tab` or `Ctrl+PageUp` | Select the previous tab |
| `Ctrl+1` through `Ctrl+8` | Select a tab by position |
| `Ctrl+9` | Select the last tab |
| `Ctrl+L` or `Alt+D` | Focus the address bar |
| `Ctrl+R` or `F5` | Reload the current page |
| `Alt+Left` / `Alt+Right` | Go back / forward |
| `Alt+Home` | Open the homepage |
| `Ctrl+D` | Bookmark the current page |
| `Ctrl+H` | Open history |
| `Ctrl+J` | Open Downloads |
| `Ctrl+,` | Open Settings |

Gaming mode pauses the shortcuts above until it is switched off. Web pages can continue to use their own keyboard input while Gaming mode is active.

## Support and prerequisites

- **Windows x64** is the primary release target.
- **Ubuntu Linux x64** is included in CI and can run from source with the system packages below. Other Linux distributions may need equivalent libraries.
- **macOS** is not covered by CI and is not currently a supported platform claim.
- Python **3.10–3.13** is the declared range.

## Install from source

Run commands from the repository root. Some settings, profile data, and proxy files use paths relative to the working directory, so use a writable checkout.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

If PowerShell blocks environment activation, use `.venv\Scripts\python.exe` in place of `python`.

### Ubuntu Linux

Qt WebEngine and QR decoding require system libraries in addition to the Python packages:

```bash
sudo apt-get update
sudo apt-get install -y libegl1 libgl1 libxcb-cursor0 libxkbcommon-x11-0 libzbar0
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Run from a graphical desktop session. QR scanning is optional and also requires camera access.

## Dependencies and development checks

`requirements.txt` pins the direct runtime dependencies. The PySide6 package supplies its matching Addons, Essentials, and shiboken packages. `requirements-dev.txt` adds pytest and Ruff for contributors.

The project CI compiles the application and runs its unit suite on Windows and Ubuntu for Python 3.10–3.13. The suite uses temporary directories and mocks for persistence and proxy/Tor process interactions; it does not make live Tor or public-network connections. CI does not claim macOS support.

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q main.py managers proxy ui tests
python -m ruff check tests
python -m pytest -ra
```

## Windows beta executable

Download **ARMA-Browser.exe** from [GitHub Releases](https://github.com/ArvinNotDev/pyqt-based-browser/releases). The Windows x64 one-file build bundles Python, PySide6/Qt WebEngine, the application assets, and the Windows Tor expert-bundle archive. A separate Python installation is not required.

On first launch, Windows may take a little longer while the one-file bundle extracts its runtime. The executable is currently unsigned, so Windows SmartScreen or antivirus software may show a warning. Only run it if you trust this repository and have verified the release asset/checksum. This beta has no automatic updater.

Settings, browser profiles, history, and proxy state for the frozen build are stored under `%LOCALAPPDATA%\ARMA Browser`. These files are separate from the executable and are retained between launches.

## Source releases

The release workflow creates a versioned source ZIP and a SHA-256 sidecar from a Git tag. To build the same archive locally from a tag:

```powershell
./scripts/package-source.ps1 -Tag v1.2.3
```

The source archive includes the tracked Windows and Linux x64 Tor bundles. The executable is a Windows beta build; Linux users can still run from source using the instructions above.

See [packaging and release notes](docs/PACKAGING.md) and the [release checklist](docs/RELEASE_CHECKLIST.md) for limitations and validation details.

## Current scope and troubleshooting

- **Ad blocking and browser extensions:** ARMA Browser includes a lightweight host-based blocker for common ad/tracker domains, but not a full EasyList-compatible or cosmetic filter, and it has no extension store. Some ads may remain and some embedded content may need the blocker disabled. Website compatibility mode only changes the user-agent string; it does not disable a site's ad-block detection or change proxy behavior.
- **A website blocks access or a download:** the site may require an extension, login, cookie, or network route that is unavailable in the current session. Check the proxy panel and the site's own requirements. ARMA Browser does not promise to bypass a site's access checks.
- **Qt WebEngine fails to start on Linux:** install the distribution's Qt WebEngine dependencies, including OpenGL, XCB, and xkbcommon libraries, and launch from a graphical session.
- **QR scanner or camera errors:** install the OS `zbar` library and check camera permissions. QR scanning is optional for browsing.
- **Tor does not connect:** check that a compatible bundle is installed, local ports are available, and the network allows Tor traffic. Bridge connections need valid bridge lines and matching transport support.
- **Settings or profile data cannot be saved:** run the checkout from a writable location. This project does not yet move all mutable files to the operating system's standard per-user application-data directory.
- **Shortcut behavior differs by desktop:** some environments reserve keys globally or limit keyboard input. Gaming mode only controls shortcuts registered by ARMA Browser.

## License

MIT. See [LICENSE](LICENSE).

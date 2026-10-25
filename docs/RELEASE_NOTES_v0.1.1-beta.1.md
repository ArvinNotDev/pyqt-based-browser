# ARMA Browser v0.1.1-beta.1 — Modern Browser Beta

This beta brings the complete `ui/modern-browser-chrome` feature branch into the mainline and refreshes the Windows x64 portable build. It remains a prerelease, not a claim of production readiness.

## What's new

### Modernized browser interface
- Refined the custom title bar, tab strip, navigation toolbar, address/search field, menus, and browser workspace.
- Improved light and dark theme styling, interaction states, keyboard focus, and layout behavior at narrower window sizes.
- Added clearer per-tab controls, including audio mute/unmute, and improved navigation feedback.

### A more capable start page and internal pages
- Enhanced the dashboard with reorderable widgets, configurable widget sizes, shortcuts, wallpaper, bookmarks, quick notes, recent pages, recently closed tabs, and a focus timer.
- Added integrated internal pages for profiles, bookmarks, history, downloads, and settings.
- Expanded profile management, including profile creation, switching, removal, and profile-avatar editing.
- Kept profile-specific preferences and browser data separated.

### Session and browsing workflows
- Added optional restoration of the previous normal browsing session and active profile; private sessions are not saved as normal sessions.
- Improved recently closed tabs and tab-management behavior.
- Added site-permission controls, find-in-page, zoom, developer tools, page-to-PDF, print, and visible-page screenshots.
- Added cache-bypass reload and an option to open the current HTTP/HTTPS page in the system browser.

### Downloads and privacy controls
- Improved Downloads with overlay and pinned side-panel layouts, richer progress details, and actions for failed or cancelled items.
- Added a lightweight host-based ad/tracker blocker. It is not a full EasyList-compatible or cosmetic filter, and some ads or blocked-site compatibility issues may remain.
- Clarified private-browsing boundaries: private history and site data are isolated, but downloaded files are still saved to the selected download folder and remain there after the browser closes.

### Proxy and Tor integration
- Integrated the updated TorProxy and proxy-panel workflows, with improved connection lifecycle handling, configuration, bridge-related diagnostics, host rules, and route exclusions.
- Normal browsing continues to use the system/Qt network route unless the user explicitly configures and connects a proxy.
- A successful setup screen does not guarantee Tor bootstrap, bridge connectivity, or access to a particular site; those outcomes depend on the local bundle, configuration, ports, and network.

### Windows portable packaging
- Provides a single Windows x64 executable with the Python, PySide6/Qt WebEngine runtime, application assets, and Windows Tor bundle included.
- Includes a SHA-256 sidecar for checking the downloaded executable for accidental corruption.
- Stores mutable data for the frozen build under `%LOCALAPPDATA%\\ARMA Browser`, outside the temporary one-file extraction directory.

## Download and run

1. Download `ARMA-Browser.exe` from the Assets section of this release.
2. Optionally verify the download with `ARMA-Browser.exe.sha256`.
3. Save the executable to a writable folder and launch it. A separate Python installation is not required.
4. The first launch may take longer while the one-file runtime extracts.

The executable is unsigned. Windows SmartScreen or antivirus software may show a warning because the build has no code-signing certificate or established reputation. Only run it if you trust this project and downloaded it from this repository's release page.

## Known limitations and validation notes

- This is beta software; regressions and compatibility issues are possible.
- The automated Windows packaging smoke test checks that the executable starts and creates persistent user data. It does not fully validate interactive rendering, downloads, or live Tor bootstrap and bridge connectivity.
- At the time of publishing, the branch's complete CI suite was not fully green: several UI integration tests failed, and a Linux Qt WebEngine test terminated with a segmentation fault. Those checks must not be interpreted as passing; additional validation is still needed.
- Qt WebEngine media/codec support varies with the bundled build and the website.
- The executable targets Windows x64 only. Linux users can run from source using the repository README; macOS binaries are not currently supported.
- There is no automatic updater yet.

Please report reproducible issues in [GitHub Issues](https://github.com/ArvinNotDev/pyqt-based-browser/issues), including your OS, Python version if applicable, and steps to reproduce.

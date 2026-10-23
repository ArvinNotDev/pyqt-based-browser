# ARMA Browser v0.1.0-beta.1 — Windows Beta

**A first portable Windows build of ARMA Browser.** This prerelease packages the application and its Python/Qt runtime into one executable so a separate Python installation is not required.

## What's new

### A more refined browser interface
- Redesigned light and dark browser chrome with porcelain-glass and obsidian-glass palettes.
- More consistent spacing and sizing across the title bar, navigation toolbar, address field, tabs, and menus.
- Clearer active-tab, hover, pressed, focus, and disabled states.

### A more useful start page
- Reorder dashboard cards using drag-and-drop; the selected order persists between launches.
- Keep the bookmarks strip on the dashboard instead of reserving space on ordinary websites.
- Improved dashboard spacing, responsive card sizing, and reduced-motion support.

### Better download and navigation workflows
- Open Downloads as an overlay without shrinking the site, or switch to a pinned side-panel layout.
- Keep the active website when toggling between overlay and docked download layouts.
- Make Actions available for failed and cancelled download records.
- Add a cache-bypass reload command (`Ctrl+Shift+R`) and a shortcut to open the current HTTP/HTTPS page in the system browser.
- Add per-tab audio mute/unmute controls and clearer diagnostics when a site's audio asset cannot be decoded.

### More reliable portable-app data
- Bundle the Windows x64 runtime, Qt WebEngine dependencies, dashboard assets, icons, and the Windows Tor expert-bundle archive in a single EXE.
- Store settings, profiles, history, and mutable proxy state in the user's local application-data folder instead of the temporary one-file extraction directory.
- Include SHA-256 metadata so the downloaded executable can be checked for accidental corruption.

## Download and run

1. Download **`ARMA-Browser.exe`** from the Assets section below.
2. Optionally verify it against **`ARMA-Browser.exe.sha256`**.
3. Save the EXE to a writable folder and double-click it. No separate Python setup is required.
4. The first launch may take longer while the one-file runtime extracts.

The Windows x64 build is unsigned. Windows SmartScreen or antivirus software may display a warning because the executable has not been signed or built up a reputation. Only run it if you trust this project and the file came from this GitHub release.

User settings and browser data are stored under `%LOCALAPPDATA%\ARMA Browser`.

## Known beta limitations

- This is a prerelease; expect bugs and occasional layout or compatibility issues.
- There is no automatic updater yet.
- Live Tor bootstrap, bridge setup, and network-route behavior are not covered by the automated executable smoke check.
- Qt WebEngine media/codec support varies by build and by the site; some embedded media may not play.
- The application is packaged for Windows x64 only. Linux users can run the source checkout using the README instructions.

Please report reproducible crashes or regressions in the repository's [Issues](https://github.com/ArvinNotDev/pyqt-based-browser/issues), including Windows version and steps to reproduce.

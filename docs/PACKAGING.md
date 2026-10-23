# Packaging and release process

## Windows one-file beta

The Windows x64 beta is built on a clean `windows-latest` GitHub Actions runner from the exact commit being released. The build uses the pinned runtime dependencies and PyInstaller 6.22.3. The release contains one self-contained `ARMA-Browser.exe` plus a SHA-256 sidecar; it does not require users to install Python separately.

The build script is:

```powershell
./scripts/build-windows-onefile.ps1
```

The script packages the application icons, dashboard assets, the Windows Tor expert-bundle archive, PySide6/Qt WebEngine, and the runtime dependencies. It checks the output exists and is plausible in size, then writes `dist/ARMA-Browser.exe.sha256`.

The one-file bootloader extracts bundled resources to a temporary directory. Frozen builds therefore store mutable settings, profiles, history, and proxy configuration under `%LOCALAPPDATA%\\ARMA Browser`, rather than attempting to persist data beside the executable or inside the temporary extraction directory. Static icons and dashboard files are resolved from the bundled resource root.

The beta workflow launches the built EXE on the Windows runner and verifies that it remains running long enough to initialize its profile data. This catches basic missing-runtime or immediate-startup failures. It is not a substitute for a manual clean-machine check of Qt WebEngine rendering, downloads, or live Tor connectivity.

## Beta limitations

- The EXE is currently unsigned. Windows SmartScreen or antivirus software may show an origin or reputation warning.
- The first launch may take longer while the single-file bundle extracts its runtime.
- This release targets Windows x64 only. It does not claim support for Windows ARM64, Linux, or macOS binaries.
- Live Tor bootstrap, bridges, and network routes are not exercised by the automated packaging smoke check. The included Windows Tor archive is provided for the optional proxy/Tor workflow, but live connectivity depends on the user's network and configuration.
- Qt WebEngine media support depends on the codecs available in the bundled Qt build and the media used by a website.
- There is no automatic update mechanism yet.

## Source releases

The source-release workflow can create a versioned source ZIP and SHA-256 sidecar from a Git tag. To build the same archive locally from a fetched tag:

```powershell
./scripts/package-source.ps1 -Tag v1.2.3
```

The source archive includes the tracked Windows and Linux x64 Tor archives. The customized `proxy/exclude_hosts.json` is marked `export-ignore` because it is a local exclusion list rather than a distribution default. The packaging script checks for required application assets and rejects profile data or proxy state from the source ZIP.

## Tracked Tor archives

The repository includes a Windows x64 Tor expert-bundle archive and a Linux x64 archive. The Windows one-file build includes only the Windows archive. The tracked Windows archive is approximately 17 MB compressed; the Linux archive is not embedded in the Windows executable.

The repository's bundled Tor archive does not include a committed checksum sidecar. The app may fetch current Tor Project checksum metadata when validating the archive. Release validation should distinguish successful packaging from verified live Tor connectivity.

## Release checklist

1. Check the current CI status and review any failed or skipped tests.
2. Build the one-file EXE on a clean Windows runner using `scripts/build-windows-onefile.ps1`.
3. Confirm the binary smoke check and SHA-256 generation succeed.
4. Publish the EXE and checksum as a prerelease, clearly labeled Beta.
5. Manually test a clean Windows environment for startup, Qt WebEngine rendering, icons, navigation, settings persistence, profiles, downloads, and shutdown.
6. Validate Tor bootstrap and bridge behavior separately if live Tor is part of the release claim.


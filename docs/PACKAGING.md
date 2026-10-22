# Packaging and release process

## Supported deliverable

The reproducible deliverable is a source ZIP built from a version tag on Windows. It contains the tracked application source, assets, pinned runtime requirements, documentation, and the tracked Windows and Linux x64 Tor archives. The customized `proxy/exclude_hosts.json` is marked `export-ignore` because it contains a domain exclusion list rather than a distribution default; the app starts with an empty exclusion list when that file is absent. The packaging script checks for required assets and rejects settings, proxy state, histories, or profile data in the ZIP. Install it into a writable directory with Python 3.10–3.13 and the commands in the README. The release workflow attaches the ZIP and a SHA-256 checksum file to the GitHub release.

To build the same artifact locally from a fetched tag:

```powershell
./scripts/package-source.ps1 -Tag v1.2.3
```

The script requires Git and the requested tag to exist locally. `git archive` packages the committed tag, not uncommitted working-tree changes. Compare the sidecar hash with `Get-FileHash -Algorithm SHA256` after downloading.

## Why there is no executable package

PyInstaller was considered, but a reliable frozen layout cannot be confirmed without changing application-owned path handling and then smoke-testing the result on a clean Windows machine:

- `proxy.utils.resource_path()` uses the `proxy/` source directory in source mode and the PyInstaller extraction root in frozen mode.
- Proxy configuration and cached Tor checksum files are written under that resource root, which may be inside the packaged application.
- Tor bundle discovery uses the resource root while extraction uses the process working directory and the relative `bundles/` path.
- Browser profiles and some proxy state use relative working-directory paths.
- Qt WebEngine needs its helper process and resources packaged and exercised with the actual pinned PySide6 wheel.

These differences can make writes fail in protected install locations or make downloaded/extracted Tor files invisible to the app. The current release process therefore makes no PyInstaller, installer, or portable-executable claim. A follow-up executable package needs a consistent writable user-data directory, explicit read-only bundled resources, a bundle migration plan, and fresh-machine smoke coverage for startup, Qt WebEngine, icons, profiles, and Tor extraction.

## Tracked Tor archives

The repository contains approximately 48.5 MB of compressed Tor expert bundle archives (Windows x64 and Linux x64). They are kept in Git and included in the source release. Removing them would remove the offline bundle path; moving them to Git LFS would require coordinated clone, CI, and release download behavior. Any such change should first verify archive hashes and test both fresh Git clones and source release downloads.

The updater fetches Tor release metadata and checksum files when asked to refresh the list. The currently tracked archives have no matching checksum files in the repository. The current offline check treats a missing checksum file as acceptable, so it does not establish integrity for a bundled or previously downloaded archive in that case. Release operators should independently verify the published Tor checksum before relying on an archive.

## Release steps

1. Ensure CI passes on Windows and Ubuntu for all declared Python versions.
2. Review the release checklist in `docs/RELEASE_CHECKLIST.md`, including any expected failures and skipped tests.
3. Create and push an annotated version tag such as `v1.2.3` after the source changes have been merged to `main`.
4. Confirm the Windows source-release workflow published the ZIP and `.sha256` file.
5. Download the release ZIP into a clean, writable Windows environment, verify the checksum, create a virtual environment, install `requirements.txt`, and perform the manual smoke checks.
6. Record any live Tor or platform checks separately from the automated unit-test results.

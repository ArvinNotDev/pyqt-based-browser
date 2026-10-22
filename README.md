# PyQt Based Browser

A Python desktop browser built with PySide6 and Qt WebEngine. The source includes tabbed browsing, navigation and search, profile settings and history, plus a local proxy UI with Tor bundle management and host block/exclusion rules. Tor routing requires a usable Tor bundle and a successful connection; it has not been validated here against the live Tor network.

## Support

- Windows x64 is the primary release target.
- Ubuntu Linux x64 is included in CI and can run from source with the system libraries listed below. Other distributions may need equivalent Qt WebEngine and barcode-reader libraries.
- macOS is not currently covered by CI and is not a supported platform claim.
- Python 3.10 through 3.13 is the declared range.

## Install from source

Run the browser from the repository root. The application currently stores some state relative to the source tree or working directory, including `proxy/config.json`, `settings.json`, `profile_data/`, and proxy rule files. Use a writable checkout.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

If PowerShell blocks activation, use `.venv\Scripts\python.exe` in place of `python` for the installation and run commands.

### Ubuntu Linux

Qt WebEngine and QR decoding need system libraries in addition to the Python wheels:

```bash
sudo apt-get update
sudo apt-get install -y libegl1 libgl1 libxcb-cursor0 libxkbcommon-x11-0 libzbar0
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Other Linux distributions need the equivalent OpenGL, XCB, xkbcommon, and `zbar` runtime packages. Camera access is needed for QR scanning.

## Dependencies

`requirements.txt` contains pinned direct runtime dependencies identified from application imports. It keeps a single `PySide6` pin; the matching Addons, Essentials, and shiboken packages are installed through that package's dependencies. `requirements-dev.txt` includes the runtime set plus pytest and Ruff.

The Tor UI can use the Windows and Linux x64 archives tracked under `proxy/bundles/`, or download a compatible archive from the Tor Project through its bundle updater. The updater attempts to cache the published SHA-256 sums when it refreshes the available versions. The current offline bundle check accepts an archive when no matching checksum file is cached, so that path does not guarantee archive integrity. Do not treat the bundled Tor archives as independently verified by the application.

## Test and check

```bash
python -m pip install -r requirements-dev.txt
python -m compileall -q main.py managers proxy ui tests
python -m ruff check tests
python -m pytest -ra
```

The tests use temporary directories and mocks for persistence and proxy/Tor process interactions. They do not connect to Tor or the public network. Tests for bookmark/download managers and the URL utility are skipped while those modules are absent from this branch; once their source files are added, the tests import them normally and expose API or dependency errors. Two existing defects are recorded as strict expected failures: malformed settings reads and invalid proxy port validation.

GitHub Actions runs these checks on Windows and Ubuntu for Python 3.10–3.13. The workflow does not claim macOS validation or run live Tor integration tests.

## Source release

The release workflow publishes a ZIP made from a version tag and a SHA-256 sidecar. To make one locally from a checked-out tag:

```powershell
./scripts/package-source.ps1 -Tag v1.2.3
```

The source archive includes the tracked Tor bundle archives and is expected to be installed with Python and `requirements.txt`. There is no standalone executable installer yet. A PyInstaller build was evaluated and deferred: current code mixes resources under `proxy/`, paths under the process working directory, and mutable configuration under the bundle resource root. Those paths need a single writable application-data/resource layout, followed by a clean-machine Qt WebEngine and Tor bundle smoke test, before a frozen executable can be claimed as reproducible.

See [the packaging and release notes](docs/PACKAGING.md) and [release checklist](docs/RELEASE_CHECKLIST.md) before publishing a version.

## Troubleshooting

- **Qt WebEngine does not start on Linux:** install the distribution's Qt WebEngine dependencies, including OpenGL, XCB, and xkbcommon runtime libraries. Run from a graphical session for interactive browsing.
- **QR scanner import or camera errors:** install the OS `zbar` library and check camera permissions. QR scanning is optional to normal browsing.
- **Tor does not connect:** check that a compatible bundle exists, the configured local ports are available, and the network permits Tor. Bridge connectivity needs valid bridge lines and the matching transport support in the selected bundle.
- **State cannot be written:** run the source checkout from a writable directory. The current application does not consistently use the operating system's per-user application-data directory.
- **Global shortcut behavior differs on Linux:** the `keyboard` dependency may require desktop/session permissions that vary by distribution.

## License

MIT. See [LICENSE](LICENSE).

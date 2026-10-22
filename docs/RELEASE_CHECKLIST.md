# Release checklist

Use this checklist for each release candidate. Record the OS, Python version, archive tag, and result for every manual check.

## Automated gates

- [ ] Windows CI passes for Python 3.10, 3.11, 3.12, and 3.13.
- [ ] Ubuntu CI passes for Python 3.10, 3.11, 3.12, and 3.13.
- [ ] Review the `XFAIL` and `SKIPPED` entries in pytest output; investigate unexpected changes.
- [ ] No live-network or live-Tor test is represented as passing unless it was run separately and recorded.

## Fresh Windows source install

- [ ] Download the release ZIP and verify its SHA-256 sidecar.
- [ ] Extract into a new writable directory with no existing browser configuration or profile data.
- [ ] Install Python 3.10–3.13 and create a clean virtual environment.
- [ ] Install `requirements.txt` and confirm `python -m pip check` succeeds.
- [ ] Start the application and confirm the main window and Qt WebEngine render.
- [ ] Create a profile, restart the app, and confirm the profile and its settings/history behave as expected.
- [ ] Navigate to a normal public page and test address-bar search and direct URL navigation.
- [ ] Download a file and confirm its destination and completion state.
- [ ] Start the local proxy and confirm configured ports, block rules, and exclusion rules behave as intended.
- [ ] If Tor is part of this release validation, start Tor with a compatible bundle, confirm bootstrap and browser connectivity, and test bridge configuration separately when relevant.
- [ ] Close the browser and proxy cleanly; confirm no child Tor process remains.
- [ ] Restart from the same extracted directory and confirm persisted state remains readable.

## Linux source smoke test

- [ ] On a fresh Ubuntu x64 environment, install the documented system libraries and pinned Python requirements.
- [ ] Confirm startup, Qt WebEngine rendering, profile persistence, and clean shutdown.
- [ ] If Tor is validated, use a compatible Linux x64 bundle and record live-network results separately.

## Known release gates

- [ ] Resolve or explicitly accept the current expected failures for malformed settings reads and invalid proxy-port validation.
- [ ] Confirm bookmark/download and URL utility tests are no longer skipped once those modules are integrated.
- [ ] Do not publish a frozen Windows executable until resource and mutable-data paths have been corrected and clean-machine Qt WebEngine/Tor bundle checks pass.

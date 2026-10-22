# Browser integration notes

These managers provide persistence and Qt WebEngine download handling. They do
not install themselves into `BrowserWindow`; the browser owner must wire them
to the active profile and its navigation lifecycle.

## Settings that still need browser integration

- Cookie persistence: `_apply_profile_settings()` currently always requests
  persistent cookies. It must choose a persistence policy from
  `Settings.save_cookies`.
- History persistence: construct history with
  `History(profile_name, enabled=settings.save_history)` (or guard every
  `add()` call) so disabled history is not recorded. Existing records are kept
  and remain available to the history manager.
- Private mode: `Settings.private_mode` is persisted, but the browser must
  select an off-the-record profile and apply the private-mode download policy.
  A profile-specific folder alone does not make browsing private.
- Hardware acceleration: the setting UI applies Qt startup flags when the
  user chooses to restart from that dialog. For later launches, startup code
  must load the preference and configure the environment before importing or
  initializing Qt WebEngine.
- Homepage and search engine are already consumed by browser navigation code.

## Manager attachment

Create one `BookmarksManager(profile_name)` for the selected profile and pass
it to the bookmark UI. Create one `DownloadManager(profile_name, download_dir)`
and call `attach_profile(QWebEngineProfile)` after creating each active WebEngine
profile. Reattach it when switching profiles. Download state is in memory and
is independent of browsing history.

# Browser integration contract

The settings and manager layer owns persisted preference values, profile-scoped
bookmark data, history records, and in-memory download request state. It does
not configure an active `QWebEngineProfile` by itself. Browser startup and
profile-switching code must apply runtime policies.

## Preferences the browser must enforce

- `save_history`: `History(profile_name, enabled=False)` prevents new records
  while retaining existing history data. The browser must also avoid routing
  visits into a history instance when history is disabled or private mode is
  active. Disabling history does not delete old records.
- `save_cookies`: the browser must set the active WebEngine profile's cookie
  persistence policy. Saving this boolean in `settings.json` has no runtime
  effect by itself.
- `private_mode`: the browser must choose an off-the-record profile and avoid
  persistent browser storage. Managers do not infer or enforce private mode
  from a profile name. The reviewed browser-core branch selects an
  off-the-record profile, disables history, and does not attach a download
  manager in private mode.
- `download_folder`: this is a stored path preference. The browser should
  apply it to the WebEngine profile and pass it to
  `DownloadManager(profile_name, download_dir=...)`. If omitted, the manager
  starts with the operating system's downloads directory and follows a
  non-empty attached profile path. Reattaching after the browser changes that
  profile path updates future download destinations when the manager had
  followed the prior profile path. Download records are session memory and do
  not become private merely because they are scoped by profile.
- `hardware_acceleration`: the saved preference must be loaded and applied
  before Qt WebEngine initializes on later launches. A settings value cannot
  change an already initialized engine.

The browser-core integration applies the history, cookie, private-profile,
download-folder, and hardware-acceleration policies above. Startup loads the
selected profile's acceleration preference before Qt WebEngine initializes;
changing that setting in the running application requires a restart. The data
layer does not claim cookie or private-mode behavior on its own.

## Stable manager APIs

`BookmarksManager(profile_name)` exposes `list_bookmarks()`,
`add_bookmark(title, url)`, `remove_bookmark(bookmark_id)`, and
`is_bookmarked(url)`. Each record contains `id`, `title`, `url`, and
`created_at`. Returned records are detached snapshots; modifying them does not
change manager state. Bookmark files are stored separately by profile.

`DownloadManager(profile_name, download_dir=None)` exposes
`attach_profile(profile)`, `get_downloads()`, `cancel(download_id)`,
`open_file(download_id)`, and `clear_finished()`, plus the
`downloads_changed` Qt signal. Records contain `id`, `file_name`, `path`,
`url`, `received_bytes`, `total_bytes`, `state`, and `error`. Public states are
`requested`, `downloading`, `completed`, `cancelled`, and `failed`. Getters
return detached snapshots. The signal fires when a record appears or its
progress/state changes. `clear_finished()` removes finished records from the
manager; it does not delete downloaded files.

The reviewed browser-core code constructs the managers with these signatures
and attaches downloads to the active WebEngine profile. The bookmark and
download dialogs call the canonical list, remove, cancel, and clear methods;
their compatibility helpers also recognize older aliases, but the data layer
does not need to provide those aliases. The downloads dialog opens completed
files through desktop services; `open_file()` remains available to other
callers.

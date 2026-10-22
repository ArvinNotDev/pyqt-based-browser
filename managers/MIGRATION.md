# Storage migration

The managers keep existing data in place and migrate only when a compatible
read or later write requires it.

## Settings

- Existing per-profile entries in `settings.json` keep their names and remain
  readable. Updating one profile does not replace other profiles or unknown
  top-level entries.
- Older profile lists stored under a hashed machine key are read, copied to
  `__pyqt_browser_meta_v1__.profiles`, and left at the old key for downgrade
  compatibility. New writes no longer query machine identifiers.
- A legacy flat settings object is retained under
  `__pyqt_browser_legacy_flat_settings_v1__` when another write is made. Its
  recognized values remain available to the `Guest` profile.
- Invalid or missing fields use current defaults. A missing profile resets to
  defaults instead of inheriting the values from a previously loaded profile.
- A malformed settings document is copied to a unique `.corrupt-*.bak` file
  before recovery rewrites it. Complete top-level records around damaged
  members are retained when they can be decoded; if none can be recovered,
  the repaired document starts empty and the original remains in the backup.
- Loading a healthy settings document does not rewrite it. The next save after
  recovery writes a normal settings document and keeps the backup unchanged.

## History

History accepts the existing URL-to-object and URL-to-list layouts, plus legacy
row lists containing `url` or `link`. Reads normalize visits in memory; the
next write stores the current URL-to-list layout. Malformed JSON stays untouched
until a write is requested, at which point a unique `.corrupt-*.bak` copy is
made before the atomic replacement.

## Bookmarks

Bookmark storage is profile-scoped at `profile_data/<profile>/bookmarks.json`.
The manager reads list files, bookmark envelopes, and ID-keyed maps while
preserving valid record IDs. It writes back using the detected container shape.

Settings, history, and bookmark writes use a temporary file beside the target
and replace the destination only after the full JSON document has been flushed.

"""Small adapters for displaying manager-owned bookmark and download records."""

from collections.abc import Mapping


def record_value(record, *names, default=None):
    """Read a field from a mapping or record object without assuming a storage type."""
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if hasattr(record, name):
            value = getattr(record, name)
            if callable(value):
                if name.startswith("get_") or name in {
                    "url",
                    "state",
                    "status",
                    "downloadFileName",
                    "downloadDirectory",
                    "receivedBytes",
                    "totalBytes",
                }:
                    return value()
                continue
            return value
    return default


def manager_records(manager, methods, attributes):
    """Read records through a manager's public getter or collection property."""
    for name in methods:
        getter = getattr(manager, name, None)
        if callable(getter):
            records = getter()
            break
    else:
        for name in attributes:
            if hasattr(manager, name):
                records = getattr(manager, name)
                if callable(records):
                    records = records()
                break
        else:
            raise AttributeError(
                f"{type(manager).__name__} does not expose any of: "
                f"{', '.join((*methods, *attributes))}"
            )

    if records is None:
        return []
    if isinstance(records, Mapping):
        return list(records.values())
    if isinstance(records, (str, bytes)):
        raise TypeError("Manager records must be a collection of records, not text")
    return list(records)


def call_manager(manager, methods, *args):
    """Call the first available public manager operation or report a clear error."""
    for name in methods:
        operation = getattr(manager, name, None)
        if callable(operation):
            return operation(*args)
    raise AttributeError(
        f"{type(manager).__name__} does not provide any of: {', '.join(methods)}"
    )


def normalize_bookmark(record):
    if isinstance(record, str):
        url = record.strip()
        return {"id": url, "title": url, "url": url} if url else None
    url = record_value(record, "url", "href", "link", default="")
    if not isinstance(url, str) and callable(getattr(url, "toString", None)):
        url = url.toString()
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    title = record_value(record, "title", "name", "label", default="")
    if not isinstance(title, str) or not title.strip():
        title = url
    identifier = record_value(record, "id", "bookmark_id", "key", default=url)
    return {"id": identifier, "title": title.strip(), "url": url}


def normalize_download(record):
    """Normalize common manager record fields for display, not persistence."""
    path = record_value(
        record,
        "file_path",
        "path",
        "target_path",
        "destination",
        "download_path",
        default="",
    )
    if path is None:
        path = ""
    path = str(path)
    filename = record_value(
        record,
        "filename",
        "file_name",
        "download_file_name",
        "suggested_filename",
        "downloadFileName",
        "name",
        default="",
    )
    if not filename and path:
        import os
        filename = os.path.basename(path)
    if not filename:
        filename = "Download"
    if not path:
        directory = record_value(record, "download_directory", "directory", "downloadDirectory", default="")
        if directory:
            import os
            path = os.path.join(str(directory), str(filename))

    url = record_value(record, "url", "origin_url", "source_url", "source", default="")
    status = record_value(record, "status", "state", "final_status", default="unknown")
    status = getattr(status, "name", status)
    status = str(status).strip().split(".")[-1].casefold().replace(" ", "_").replace("-", "_")
    status = {
        "downloadrequested": "queued",
        "downloadinprogress": "downloading",
        "downloadcompleted": "completed",
        "downloadcancelled": "cancelled",
        "downloadcanceled": "cancelled",
        "downloadinterrupted": "failed",
    }.get(status, status)
    if status == "unknown":
        if record_value(record, "is_completed", "completed", default=False):
            status = "completed"
        elif record_value(record, "is_cancelled", "cancelled", "canceled", default=False):
            status = "cancelled"
        elif record_value(record, "is_failed", "failed", default=False):
            status = "failed"
    received = record_value(
        record,
        "received_bytes",
        "bytes_received",
        "downloaded_bytes",
        "bytes_downloaded",
        "received_bytes_value",
        "receivedBytes",
        default=None,
    )
    total = record_value(
        record,
        "total_bytes",
        "bytes_total",
        "expected_bytes",
        "expected_size",
        "total_size",
        "size_bytes",
        "size",
        "total_bytes_value",
        "totalBytes",
        default=None,
    )
    progress = record_value(record, "progress", "progress_percent", default=None)
    error = record_value(record, "error", "error_message", default="")
    identifier = record_value(record, "id", "download_id", "guid", default=None)
    return {
        "id": identifier,
        "filename": str(filename),
        "path": path,
        "url": str(url or ""),
        "status": status,
        "received": received,
        "total": total,
        "progress": progress,
        "error": str(error or ""),
    }

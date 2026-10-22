import os
import sys
import tarfile
import logging
import ntpath
import shutil
import tempfile

logger = logging.getLogger(__name__)
MAX_TAR_MEMBERS = 10000
MAX_UNPACKED_BUNDLE_BYTES = 1024 * 1024 * 1024

def resource_path(relative_path):
    if getattr(sys, "_MEIPASS", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)

def extract_tar_gz_file(filename, dst):
    """Extract a Tor bundle after validating every archive member path."""
    destination = os.path.abspath(dst)
    parent = os.path.dirname(destination)
    os.makedirs(parent, exist_ok=True)
    if os.path.lexists(destination):
        raise FileExistsError(f"Bundle destination already exists: {destination}")

    staging = tempfile.mkdtemp(prefix=".tor-extract-", dir=parent)
    try:
        with tarfile.open(filename, "r:gz") as tar:
            members = tar.getmembers()
            if len(members) > MAX_TAR_MEMBERS:
                raise ValueError("Archive contains too many members")
            if sum(max(0, member.size) for member in members) > MAX_UNPACKED_BUNDLE_BYTES:
                raise ValueError("Archive exceeds the extraction size limit")
            seen = set()
            for member in members:
                name = member.name
                drive, _ = ntpath.splitdrive(name)
                if (not name or drive or name.startswith(("/", "\\")) or "\\" in name):
                    raise ValueError("Archive contains an absolute or malformed path")
                parts = name.rstrip("/").split("/")
                if not parts or any(part in ("", ".", "..") for part in parts):
                    raise ValueError("Archive contains a path traversal component")
                if any(":" in part or part.endswith((" ", ".")) for part in parts):
                    raise ValueError("Archive contains a platform-unsafe filename")
                if os.name == "nt":
                    reserved = {"CON", "PRN", "AUX", "NUL"}
                    reserved.update(f"COM{number}" for number in range(1, 10))
                    reserved.update(f"LPT{number}" for number in range(1, 10))
                    if any(part.split(".", 1)[0].upper() in reserved for part in parts):
                        raise ValueError("Archive contains a reserved Windows filename")
                normalized = "/".join(parts)
                if normalized in seen:
                    raise ValueError("Archive contains duplicate paths")
                seen.add(normalized)
                target = os.path.abspath(os.path.join(staging, *normalized.split("/")))
                if os.path.commonpath((staging, target)) != staging:
                    raise ValueError("Archive member escapes the destination")
                if not (member.isdir() or member.isfile()):
                    raise ValueError("Archive contains a link or special file")

            tar.extractall(path=staging, members=members)
        os.replace(staging, destination)
        return destination
    except Exception as e:
        logger.error("Tor bundle extraction failed (%s)", type(e).__name__)
        raise
    finally:
        if os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)

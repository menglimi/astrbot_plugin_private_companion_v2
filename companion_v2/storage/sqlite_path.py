"""SQLite read-only paths, including Windows network shares and Unicode names."""

from pathlib import Path
from urllib.parse import quote


def readonly_uri(path):
    resolved = Path(path).resolve()
    value = resolved.as_posix()
    # SQLite's Windows build rejects a non-local URI authority. Four slashes
    # retain the UNC path with an empty authority instead of file://server/.
    uri = "file://" + quote(value, safe="/:") if value.startswith("//") else resolved.as_uri()
    return uri + "?mode=ro"

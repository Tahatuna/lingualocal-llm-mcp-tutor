"""Small JSON / bytes cache on disk, keyed by a hash of the request. Answers never change, so there is no expiry."""
import hashlib
import json
import os
import tempfile

from . import config


def _path(kind, key, ext):
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
    return os.path.join(config.DATA_DIR, "cache", kind, h[:2], h + ext)


def get_json(kind, key):
    try:
        with open(_path(kind, key, ".json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def put_json(kind, key, value):
    _write(_path(kind, key, ".json"), json.dumps(value, ensure_ascii=False).encode("utf-8"))


def get_bytes(kind, key):
    try:
        with open(_path(kind, key, ".bin"), "rb") as f:
            return f.read()
    except OSError:
        return None


def put_bytes(kind, key, data):
    _write(_path(kind, key, ".bin"), data)


def _write(path, data):
    # Write then rename: a reader never sees half a file.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)

"""Testing compatibility helpers supporting both pytest and standalone unittest."""

import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Any, Dict


class RaisesContext:
    def __init__(self, expected_exc):
        self.expected_exc = expected_exc
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None or not issubclass(exc_type, self.expected_exc):
            raise AssertionError(f"Expected exception {self.expected_exc}, but got {exc_type}")
        self.value = exc_val
        return True


def raises(exc_type):
    return RaisesContext(exc_type)


class MonkeyPatch:
    def __init__(self):
        self._set_envs = []
        self._set_attrs = []
        self._orig_cwd = None

    def setenv(self, key: str, value: str):
        old = os.environ.get(key)
        self._set_envs.append((key, old))
        os.environ[key] = value

    def delenv(self, key: str, raising: bool = False):
        if key in os.environ:
            old = os.environ.pop(key)
            self._set_envs.append((key, old))

    def setattr(self, target: Any, name_or_value: Any, value: Any = None):
        if value is None and isinstance(target, str):
            import importlib
            mod_name, attr_name = target.rsplit(".", 1)
            target = importlib.import_module(mod_name)
            name = attr_name
            val = name_or_value
        else:
            name = name_or_value
            val = value
        orig = getattr(target, name)
        self._set_attrs.append((target, name, orig))
        setattr(target, name, val)

    def chdir(self, path: str):
        if self._orig_cwd is None:
            self._orig_cwd = os.getcwd()
        os.chdir(str(path))

    def undo(self):
        for key, old in reversed(self._set_envs):
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
        for target, name, orig in reversed(self._set_attrs):
            setattr(target, name, orig)
        if self._orig_cwd is not None:
            os.chdir(self._orig_cwd)


class TempPath:
    def __init__(self, path: str):
        self._path = path

    def __str__(self):
        return self._path

    def __fspath__(self):
        return self._path

    def __truediv__(self, other):
        return TempPath(os.path.join(self._path, str(other)))

    @property
    def parent(self):
        return TempPath(os.path.dirname(self._path))

    def mkdir(self, parents=False, exist_ok=False):
        os.makedirs(self._path, exist_ok=exist_ok)

    def write_text(self, text, encoding="utf-8"):
        with open(self._path, "w", encoding=encoding) as f:
            f.write(text)

    def read_text(self, encoding="utf-8"):
        with open(self._path, "r", encoding=encoding) as f:
            return f.read()

    def is_file(self):
        return os.path.isfile(self._path)

    def is_dir(self):
        return os.path.isdir(self._path)

    def exists(self):
        return os.path.exists(self._path)

    def symlink_to(self, target):
        os.symlink(str(target), self._path)

    def chmod(self, mode):
        os.chmod(self._path, mode)

    def unlink(self, missing_ok=False):
        try:
            os.remove(self._path)
        except FileNotFoundError:
            if not missing_ok:
                raise


@contextmanager
def temporary_directory():
    d = tempfile.mkdtemp(prefix="test_eselect_")
    try:
        yield TempPath(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)

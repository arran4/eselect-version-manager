"""Unit tests for diagnostic doctor tool."""

from eselect_version_manager.doctor import run_doctor
from eselect_version_manager.config import get_shims_dir


def test_doctor_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("PATH", f"{get_shims_dir()}:/usr/bin:/bin")

    all_passed, lines = run_doctor(current_dir=str(tmp_path))
    assert isinstance(lines, list)
    assert any("PATH check:" in line for line in lines)
    assert any("Doctor result:" in line for line in lines)

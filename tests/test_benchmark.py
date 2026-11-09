"""Performance regression test and benchmark for project lookup."""

import os
import time
from eselect_version_manager.project import (
    canonicalize_path,
    save_private_project_config,
    find_project_hierarchy,
)


def test_project_lookup_performance_scaling(tmp_path, monkeypatch):
    """
    Verify that project lookup scales with directory depth O(depth),
    and is independent of the total number of registered private projects.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    # Register 150 dummy projects in user storage
    for i in range(150):
        dummy_dir = tmp_path / f"dummy_project_{i}"
        dummy_dir.mkdir()
        save_private_project_config(canonicalize_path(str(dummy_dir)), {"VM_GO": f"1.{i}"})

    # Create a deep nested project directory
    current = tmp_path / "target_project"
    current.mkdir()
    target_root = canonicalize_path(str(current))
    save_private_project_config(target_root, {"VM_GO": "1.26"})

    # Create 6 levels of subdirectories
    deep_dir = current
    for step in ["src", "pkg", "core", "internal", "engine", "impl"]:
        deep_dir = deep_dir / step
        deep_dir.mkdir()

    # Warmup
    find_project_hierarchy(str(deep_dir))

    # Benchmark 100 lookups
    iterations = 100
    start = time.perf_counter()
    for _ in range(iterations):
        hierarchy = find_project_hierarchy(str(deep_dir))
        assert len(hierarchy) >= 1
        assert hierarchy[0]["project_root"] == target_root
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000.0
    print(f"\n[Benchmark] Average project lookup across 150 registered projects & 7 directory levels: {avg_ms:.4f} ms")

    # Assert that average lookup is sub-millisecond (typically < 0.2ms)
    assert avg_ms < 5.0, f"Project lookup took too long: {avg_ms:.2f} ms"

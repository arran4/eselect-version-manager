#!/usr/bin/env python3
"""Standalone test runner without external dependencies."""

import inspect
import os
import sys
import time

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.compat import temporary_directory, MonkeyPatch


def run_all_tests():
    test_modules = [
        "tests.test_config",
        "tests.test_project",
        "tests.test_benchmark",
        "tests.test_version_matching",
        "tests.test_providers",
        "tests.test_resolver",
        "tests.test_conversion",
        "tests.test_shims",
        "tests.test_doctor",
        "tests.test_cli",
    ]

    total = 0
    passed = 0
    failed = 0
    errors = []

    print(f"Starting eselect-version-manager test suite ({len(test_modules)} modules)...")
    start_time = time.perf_counter()

    for mod_name in test_modules:
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception as e:
            print(f"E Failed to import {mod_name}: {e}")
            failed += 1
            continue

        test_funcs = [
            (name, func)
            for name, func in inspect.getmembers(mod, inspect.isfunction)
            if name.startswith("test_")
        ]

        for name, func in test_funcs:
            total += 1
            sig = inspect.signature(func)
            kwargs = {}

            # Prepare fixtures if requested by signature
            try:
                with temporary_directory() as tmp_path:
                    mp = MonkeyPatch()
                    try:
                        if "tmp_path" in sig.parameters:
                            kwargs["tmp_path"] = tmp_path
                        if "monkeypatch" in sig.parameters:
                            kwargs["monkeypatch"] = mp

                        func(**kwargs)
                        passed += 1
                        print(f"✓ {mod_name}.{name}")
                    finally:
                        mp.undo()
            except Exception as e:
                failed += 1
                errors.append((f"{mod_name}.{name}", e))
                print(f"✗ {mod_name}.{name}: {e}")

    elapsed = time.perf_counter() - start_time
    print("\n" + "=" * 60)
    print(f"Test Summary: {passed}/{total} passed in {elapsed:.3f}s")
    if failed:
        print(f"FAILED: {failed} test(s) failed:")
        for name, err in errors:
            print(f"  - {name}: {err}")
        return 1

    print("ALL TESTS PASSED SUCCESSFULLY!")
    return 0


if __name__ == "__main__":
    sys.exit(run_all_tests())

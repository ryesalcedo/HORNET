#!/usr/bin/env python3
"""Local validation for scripts/install_hornet.py (Windows-safe subset)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import zlib
import base64
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL_SCRIPT = ROOT / "scripts" / "install_hornet.py"
TEST_DIR = ROOT / ".test-install"


def load_install_module():
    spec = importlib.util.spec_from_file_location("install_hornet", INSTALL_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_syntax() -> None:
    subprocess.check_call([sys.executable, "-m", "py_compile", str(INSTALL_SCRIPT)])
    print("PASS: syntax compile")


def test_payload() -> dict:
    mod = load_install_module()
    data = json.loads(zlib.decompress(base64.b64decode(mod.PAYLOAD)))
    assert isinstance(data, dict) and data, "payload empty"
    required = {
        "pyproject.toml",
        "hornet/__init__.py",
        "hornet/config.py",
        "config/models.yaml",
        "config/settings.yaml",
        "scripts/build_schema_cache.py",
        ".env.example",
    }
    missing = sorted(required - set(data))
    assert not missing, f"missing embedded files: {missing}"
    print(f"PASS: payload decodes to {len(data)} files")
    return data


def test_extract_and_install(data: dict) -> None:
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True)

    for rel, content in data.items():
        dest = TEST_DIR / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")

    venv = TEST_DIR / ".venv"
    subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    vpy = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.check_call([str(vpy), "-m", "pip", "install", "-q", "-e", str(TEST_DIR)])

    out = subprocess.check_output(
        [
            str(vpy),
            "-c",
            "from hornet.config import load_settings; from hornet.cli import main; "
            "s=load_settings(); print(s.orchestrator.model); print(s.resident_models); "
            "print('cli_ok')",
        ],
        text=True,
    ).strip().splitlines()
    assert out, "import smoke test produced no output"
    assert out[-1] == "cli_ok"
    print(f"PASS: pip install + import (model={out[0]}, resident={out[1]})")

    hornet_bin = venv / ("Scripts/hornet.exe" if sys.platform == "win32" else "bin/hornet")
    assert hornet_bin.exists(), f"missing entry point: {hornet_bin}"
    print(f"PASS: console script exists ({hornet_bin.name})")


def main() -> int:
    print(f"testing {INSTALL_SCRIPT}")
    test_syntax()
    data = test_payload()
    test_extract_and_install(data)
    print("\nALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

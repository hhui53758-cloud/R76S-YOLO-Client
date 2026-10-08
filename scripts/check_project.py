"""Validate model digests and reject accidental private files in the source tree."""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", ".venv-train", "venv", "__pycache__", "dist", "build", "release", "datasets", "training_runs"}

def main() -> None:
    manifest = json.loads((ROOT / "deploy/model_manifest.json").read_text(encoding="utf-8"))
    for artifact in manifest["artifacts"].values():
        path = ROOT / "deploy" / artifact["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != artifact["sha256"]:
            raise AssertionError(f"Model hash mismatch: {path.name}")
    for line in (ROOT / "deploy/SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, name = line.split()
        if hashlib.sha256((ROOT / "deploy" / name).read_bytes()).hexdigest() != expected:
            raise AssertionError(f"Model checksum mismatch: {name}")
    count = 0
    for path in ROOT.rglob("*"):
        relative = path.relative_to(ROOT)
        if not path.is_file() or any(part in SKIP for part in relative.parts):
            continue
        if path.stat().st_size >= 100 * 1024 * 1024:
            raise AssertionError(f"Oversized repository file: {relative}")
        if path.name.startswith(("codex_r76s_", "id_rsa", "id_ed25519")) or path.name == "known_hosts" or path.suffix in {".key", ".pem", ".log", ".etl"}:
            raise AssertionError(f"Private/runtime file found: {relative}")
        if path.suffix == ".py":
            source = path.read_text(encoding="utf-8-sig")
            ast.parse(source, filename=str(relative))
            if ("PRIVATE" + " KEY-----") in source:
                raise AssertionError(f"Credential found: {relative}")
        count += 1
    print(f"PROJECT_CHECK_PASSED: {count} files; model checksums valid")

if __name__ == "__main__":
    main()

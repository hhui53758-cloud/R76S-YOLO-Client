"""Create a source ZIP using Git's tracked and non-ignored file inventory."""
from __future__ import annotations
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts/check_project.py")], check=True)
    inventory = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).decode("utf-8").split("\0")
    output = ROOT.parent / f"{ROOT.name}-source.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(set(filter(None, inventory))):
            path = ROOT / name
            if path.is_file():
                archive.write(path, f"{ROOT.name}/{name}")
    print(f"SOURCE_EXPORT_PASSED: {output}")

if __name__ == "__main__":
    main()

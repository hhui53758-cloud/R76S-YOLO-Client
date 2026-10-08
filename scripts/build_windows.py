"""Build a portable Windows directory and ZIP from repository-relative paths."""
from __future__ import annotations
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Windows EXE builds must run on Windows.")
    subprocess.run([sys.executable, str(ROOT / "scripts/check_project.py")], check=True)
    client = ROOT / "windows_client"
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
               "--onedir", "--windowed", "--name", "R76S-YOLO-Client",
               "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
               "--specpath", str(ROOT / "build"),
               "--add-data", f"{ROOT / 'deploy/best.onnx'};deploy",
               "--add-data", f"{ROOT / 'deploy/model_manifest.json'};deploy"]
    # Official Python is recommended. Preserve compatibility with a Conda build host.
    for name in ("tcl86t.dll", "tk86t.dll", "ffi.dll"):
        binary = Path(sys.prefix) / "Library/bin" / name
        if binary.is_file():
            command.extend(["--add-binary", f"{binary};."])
    for module in ("torch", "torchvision", "ultralytics", "matplotlib", "pandas", "scipy", "paramiko"):
        command.extend(["--exclude-module", module])
    command.append(str(client / "app.py"))
    subprocess.run(command, cwd=ROOT, check=True)
    output = ROOT / "dist/R76S-YOLO-Client"
    for name in ("network_to_r76s.ps1", "network_to_dhcp.ps1", "切换到R76S网络.bat", "恢复普通网线自动获取IP.bat"):
        shutil.copy2(client / name, output / name)
    shutil.copy2(client / "PORTABLE_README.txt", output / "README_使用说明.txt")
    shutil.copy2(client / "用户使用说明.md", output / "完整用户使用说明.txt")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", output / "THIRD_PARTY_NOTICES.md")
    shutil.copytree(ROOT / "licenses", output / "licenses", dirs_exist_ok=True)
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    archive = Path(shutil.make_archive(str(release / "R76S-YOLO-Client-Windows-x64"), "zip", ROOT / "dist", output.name))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (release / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(f"BUILD_PASSED: {archive}")

if __name__ == "__main__":
    main()

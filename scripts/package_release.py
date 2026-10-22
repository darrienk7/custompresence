"""Build the app and its platform installer. Used automatically by GitHub Actions."""

import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from urllib.request import urlretrieve


ROOT = Path(__file__).resolve().parents[1]
WEBVIEW_BOOTSTRAPPER = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"


def package_windows(version):
    compiler = shutil.which("iscc") or "C:/Program Files (x86)/Inno Setup 6/ISCC.exe"
    if not Path(compiler).is_file():
        raise RuntimeError("Inno Setup 6 is required to build the Windows installer.")
    bootstrapper = ROOT / "build/installer/MicrosoftEdgeWebview2Setup.exe"
    bootstrapper.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(WEBVIEW_BOOTSTRAPPER, bootstrapper)
    subprocess.run([compiler, f"/DMyAppVersion={version}", str(ROOT / "packaging/windows.iss")], check=True)


def package_macos():
    architecture = platform.machine()
    if architecture not in {"arm64", "x86_64"}:
        raise RuntimeError(f"Unsupported Mac architecture: {architecture}")
    suffix = "AppleSilicon" if architecture == "arm64" else "Intel"
    destination = ROOT / f"dist/CustomPresence-macOS-{suffix}.dmg"
    with tempfile.TemporaryDirectory(dir=ROOT / "build") as temporary:
        staging = Path(temporary)
        shutil.copytree(ROOT / "dist/CustomPresence.app", staging / "CustomPresence.app", symlinks=True)
        (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
        subprocess.run(["hdiutil", "create", "-volname", "Custom Presence", "-srcfolder", str(staging),
                        "-ov", "-format", "UDZO", str(destination)], check=True)


def main():
    if sys.platform not in {"win32", "darwin"}:
        raise RuntimeError("Build releases on Windows or macOS.")
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(ROOT / "custompresence.spec")],
                   cwd=ROOT, check=True)
    if sys.platform == "win32":
        package_windows(metadata["project"]["version"])
    else:
        package_macos()


if __name__ == "__main__":
    main()

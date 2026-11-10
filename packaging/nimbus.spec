# PyInstaller build recipe for a one-folder Windows release. Run via scripts/build_release.py,
# which renders the icon first.
# ruff: noqa
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "assets" / "nimbus.ico"), "assets"),
    (str(ROOT / "assets" / "nimbus.png"), "assets"),
    # The display font and line icons are read at runtime through config.paths.asset_path.
    (str(ROOT / "assets" / "fonts"), "assets/fonts"),
    (str(ROOT / "assets" / "icons"), "assets/icons"),
]
binaries = []
hiddenimports = ["win32com.client", "keyring.backends.Windows"]

# Libraries Nimbus never uses that other packages can drag in; excluding them keeps the
# download small.
UNUSED = ("torch", "paddle", "openvino", "transformers", "speech_recognition", "pydub", "sklearn", "tensorflow")


def _wanted(module: str) -> bool:
    return not any(part in module for part in UNUSED)


# These ship native libraries (sqlite-vec's vec0.dll, pdfium, the WinRT projections) or load
# plugins dynamically, which static analysis misses.
for package in ("sqlite_vec", "fastembed", "pypdfium2", "pypdfium2_raw", "winrt"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += [m for m in package_hidden if _wanted(m)]
# These only need their model/config files plus the submodules on the ONNX path.
for package in ("markitdown", "magika", "onnxruntime"):
    datas += collect_data_files(package)
    hiddenimports += collect_submodules(package, filter=_wanted)

analysis = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[*UNUSED, "matplotlib", "tkinter", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Nimbus",
    icon=str(ROOT / "assets" / "nimbus.ico"),
    console=False,
    upx=False,
)
COLLECT(exe, analysis.binaries, analysis.datas, name="Nimbus", upx=False)

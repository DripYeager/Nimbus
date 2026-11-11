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
for package in ("sqlite_vec", "fastembed", "pypdfium2", "pypdfium2_raw", "winrt", "ctranslate2", "faster_whisper"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += [m for m in package_hidden if _wanted(m)]
# These only need their data files (models, configs, python-docx's blank document template)
# plus their submodules.
for package in ("markitdown", "magika", "onnxruntime", "docx"):
    datas += collect_data_files(package)
    hiddenimports += collect_submodules(package, filter=_wanted)

# Approved code runs use the app as their Python (Nimbus.exe --run-code), so the libraries and
# standard modules people reach for in data work must be inside the bundle even where Nimbus
# itself never imports them. matplotlib draws with the file-only Agg backend.
SANDBOX_MODULES = (
    "statistics", "csv", "math", "cmath", "decimal", "fractions", "datetime", "calendar", "zoneinfo",
    "collections", "itertools", "functools", "operator", "heapq", "bisect", "json", "re", "random",
    "string", "textwrap", "difflib", "pprint", "pathlib", "glob", "fnmatch", "io", "zipfile",
    "hashlib", "base64", "uuid", "time", "dataclasses", "enum", "typing", "unicodedata",
    "openpyxl", "matplotlib.pyplot", "matplotlib.backends.backend_agg",
)
hiddenimports += list(SANDBOX_MODULES)
hiddenimports += collect_submodules("pandas", filter=lambda m: _wanted(m) and ".tests" not in m)
datas += collect_data_files("matplotlib")
# MCP: the bridge other apps start (Nimbus.exe --mcp) and connections to other apps' servers.
# Its command-line extras aren't used and pull in packages Nimbus doesn't ship.
hiddenimports += collect_submodules("mcp", filter=lambda m: _wanted(m) and not m.startswith("mcp.cli"))
hiddenimports += collect_submodules("mcp_types")

analysis = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[*UNUSED, "tkinter", "IPython", "pytest"],
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

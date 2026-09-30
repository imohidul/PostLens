# PyInstaller build recipe for the PostLens desktop app.
#   pyinstaller packaging/postlens.spec --noconfirm
# Produces dist/PostLens/ (Windows, Linux) or dist/PostLens.app (macOS).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

datas = [
    (str(ROOT / "postlens" / "static"), "postlens/static"),
    (str(ROOT / "postlens" / "data"), "postlens/data"),
]
binaries = []
hiddenimports = collect_submodules("postlens") + collect_submodules("uvicorn")

# Packages that ship data files or load plugins dynamically.
for pkg in ("playwright", "trafilatura", "justext", "courlan", "tld", "htmldate", "dateparser",
            "fastembed", "tokenizers", "onnxruntime", "keyring", "webview", "lxml"):
    try:
        d, b, h = collect_all(pkg)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "notebook", "scipy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PostLens",
    console=False,  # a desktop app: no black console window
    icon=str(ROOT / "packaging" / "icons" / ("icon.icns" if IS_MAC else "icon.ico")),
    target_arch=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PostLens")

if IS_MAC:
    import re
    version = re.search(r'__version__ = "([^"]+)"', (ROOT / "postlens" / "__init__.py").read_text()).group(1)
    app = BUNDLE(
        coll,
        name="PostLens.app",
        icon=str(ROOT / "packaging" / "icons" / "icon.icns"),
        bundle_identifier="io.github.imohidul.postlens",
        version=version,
        info_plist={
            "CFBundleName": "PostLens",
            "CFBundleDisplayName": "PostLens",
            "CFBundleShortVersionString": version,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )

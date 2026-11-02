"""Write packaging/version_info.txt (Windows file properties of the executables) from fttx_bom.__version__."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fttx_bom import __version__  # noqa: E402

nums = [int(x) for x in __version__.split(".")[:3]] + [0]
t = tuple(nums[:4])
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('FileDescription', 'FTTx BOM Tool'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'FTTx BOM Tool'),
      StringStruct('OriginalFilename', 'FTTx BOM Tool.exe'),
      StringStruct('ProductName', 'FTTx BOM Tool'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('LegalCopyright', '')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
(Path(__file__).parent / "version_info.txt").write_text(text, encoding="utf-8")
print(__version__)

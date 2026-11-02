"""Entry point of the packaged Windows application (FTTx BOM Tool.exe and fttx-bom.exe)."""
import sys

from fttx_bom.desktop import main

if __name__ == "__main__":
    sys.exit(main())

"""Entry point of the packaged command-line program (ftth_addrlist_cli.exe)."""
import sys

from ftth_addrlist.cli import main

if __name__ == "__main__":
    sys.exit(main())

import os
import sys
from pathlib import Path


def try_become_root(required: bool = False) -> None:
    if os.getuid() != 0:
        if "--sudo" in sys.argv:
            argv = [] + Path(f"/proc/{os.getpid()}/cmdline").read_text().split("\0")
            os.execv("/usr/bin/sudo", argv)
        elif required:
            print("Must be run as root (Add argument --sudo)")
            sys.exit(1)

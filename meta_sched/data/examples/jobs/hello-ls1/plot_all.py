#! /usr/bin/env pvpython

"""
Renders particle data from XYZ files as PNG images (and also make GIF animation).

Usage: ./plot.py <output folder name>
"""

import os
import sys
from multiprocessing import Pool
from pathlib import Path

os.chdir(Path(__file__).parent)


def render(xyz_path: Path) -> int:
    return os.system(f"{Path(__file__).parent / 'plot.py'} {xyz_path}")


output_path = Path(sys.argv[1])
xyz_paths = list(output_path.glob("*.xyz"))
with Pool() as pool:
    pool.map(render, xyz_paths)

os.chdir(Path(sys.argv[1]))
print("Making animation using ImageMagick ...", end="", flush=True)
os.system("convert -resize 50% -delay 10 -loop 0 *.png animation.gif")
print("Done!")
print("Optimizing GIF ...", end="", flush=True)
os.system("mogrify -layers 'optimize' -fuzz 7% animation.gif")
print("Done!")

#! /usr/bin/env pvpython

"""
Renders particle data from XYZ file as PNG image.

Usage: ./plot.py <xyz path>
"""

import math
import sys
from pathlib import Path

import paraview.simple as pvs

xyz_path = Path(sys.argv[1])
print("Rendering", xyz_path, "...", end="", flush=True)

pvs.XYZReader(FileName=str(xyz_path))
disp = pvs.Show()
disp.AtomicRadiusFactor = 0.25

XZLength = 132.6
YLength = 591.891
pvs.Box(
    Center=[XZLength / 2, YLength / 2, XZLength / 2],
    XLength=XZLength,
    YLength=YLength,
    ZLength=XZLength,
)
disp = pvs.Show()
disp.Representation = "Wireframe"
disp.AmbientColor = [0.0, 0.0, 0.0]


pvs.Render()

view = pvs.GetActiveViewOrCreate("RenderView")

view.Background = [1.0, 1.0, 1.0]
view.UseColorPaletteForBackground = 0
view.OrientationAxesVisibility = 0

view.ViewSize = [math.ceil(10 * x) for x in [YLength, XZLength / 2]]
view.CameraPosition = [XZLength / 2, YLength / 2, 0]
view.CameraFocalPoint = [XZLength / 2, YLength / 2, XZLength / 2]

# Set up the camera to visualize along Y-axis
view.CameraViewUp = [1, 0, 0]
view.CameraParallelProjection = 1
view.CameraParallelScale = 80  # 39.625

pvs.SaveScreenshot(str(xyz_path.with_suffix(".png")), ImageResolution=view.ViewSize)
print("Done!")

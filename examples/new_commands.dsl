# Demonstration of the eight added image operations.
# CROP coordinates and dimensions must fit the image at that point.
LOAD "input.png"
BRIGHTNESS 15
CONTRAST 1.2
SATURATION 1.3
FLIP HORIZONTAL
CROP 0 0 300 200
SHARPEN 0.8
THRESHOLD 128
MEDIAN_BLUR 3
SAVE "output.png"

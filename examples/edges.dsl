# Written the way you would naturally think about it: filter, then shrink.
# The optimiser moves RESIZE above BLUR and EDGE, which on a 12 MP input
# cuts the work by roughly 95%.
LOAD "photo.jpg"
BLUR 3
EDGE 80 160
RESIZE 400 300
SAVE "edges.png"

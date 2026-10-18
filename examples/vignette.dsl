# VIGNETTE is resolution-independent, so the optimiser may move the RESIZE above
# it: the vignette is then applied to 0.12 MP instead of 12 MP.
LOAD "photo.jpg"
VIGNETTE 60
RESIZE 400 300
SAVE "vignette.png"

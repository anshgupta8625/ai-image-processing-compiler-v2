# A plain thumbnail. Already near-optimal: the resize comes first,
# so there is nothing for strength reduction to hoist.
LOAD "photo.jpg"
RESIZE 320 240
BLUR 2
SAVE "thumb.jpg"

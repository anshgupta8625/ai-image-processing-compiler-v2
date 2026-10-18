# Every pass gets something to do here.
LOAD "photo.jpg"
ROTATE 90
ROTATE 270        # cancels the previous rotation
GRAYSCALE
GRAYSCALE         # idempotent, collapsed
BLUR 3
BLUR 4            # fused into BLUR 5
RESIZE 1000 1000
RESIZE 200 200    # the first resize is shadowed
SAVE "out.png"

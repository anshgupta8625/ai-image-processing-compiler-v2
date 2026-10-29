# DSL Reference

## Grammar

```
program   := statement*
statement := COMMAND argument* NEWLINE
argument  := NUMBER | STRING | DIRECTION
DIRECTION := HORIZONTAL | VERTICAL
COMMAND   := LOAD | SAVE | RESIZE | GRAYSCALE | BLUR | ROTATE | EDGE | VIGNETTE
            | BRIGHTNESS | CONTRAST | SATURATION | FLIP | CROP | SHARPEN
            | THRESHOLD | MEDIAN_BLUR
STRING    := '"' [^"\n\\]{0,128} '"'
NUMBER    := '-'? [0-9]+ ('.' [0-9]+)?
comment   := '#' .* end-of-line
```

The language is deliberately regular. There are no variables, no expressions,
no conditionals and **no loops** — a program is a straight-line pipeline. That
is a security property as much as a design one: a language with no iteration
construct cannot be made to run forever.

Commands are case-insensitive; `blur 3` and `BLUR 3` lex identically. Comments
run to end of line and are discarded by the lexer.

## Commands

| Command | Arguments | Effect |
|---|---|---|
| `LOAD "file"` | filename | Load the uploaded image. Must be first, exactly once. |
| `SAVE "file"` | filename | Write the result. Must be last, at least once. |
| `RESIZE w h` | two integers | Scale to `w × h`. `INTER_AREA` when shrinking. |
| `GRAYSCALE` | none | Convert to single-channel. Idempotent. |
| `BLUR r` | integer | Gaussian blur, kernel `2r+1`. |
| `ROTATE a` | integer | Rotate by a multiple of 90 degrees. |
| `EDGE [low high]` | none or two integers | Canny edge detection. Defaults to `100 200`. |
| `VIGNETTE s` | integer | Darken towards the corners with a radial falloff. Centre untouched; corners lose `s`% of their brightness. Defined in relative coordinates, so it looks the same at any size. |
| `BRIGHTNESS n` | integer | Add or subtract brightness, from −100 to 100. |
| `CONTRAST f` | number | Contrast multiplier from 0.1 to 3.0; 1.0 is unchanged. |
| `SATURATION f` | number | Saturation multiplier from 0 to 3.0; 1.0 is unchanged. |
| `FLIP HORIZONTAL` / `FLIP VERTICAL` | direction | Mirror the image horizontally or vertically. |
| `CROP x y w h` | four integers | Crop a rectangle from top-left coordinate `(x, y)` with dimensions `w × h`. Must fit the current image. |
| `SHARPEN f` | number | Sharpen details with strength from 0 to 3.0. |
| `THRESHOLD n` | integer | Convert to binary black and white using threshold 0–255. |
| `MEDIAN_BLUR k` | odd integer | Reduce noise with a kernel from 3 to 25. |

## Ranges

| Argument | Range |
|---|---|
| `RESIZE` width, height | 1 … 4096, product ≤ 16,777,216 |
| `BLUR` radius | 1 … 25 |
| `ROTATE` angle | multiple of 90, −360 … 360 |
| `EDGE` thresholds | `0 ≤ low < high ≤ 500` |
| `VIGNETTE` strength | 1 … 100 |
| `BRIGHTNESS` amount | −100 … 100 |
| `CONTRAST` factor | 0.1 … 3.0 |
| `SATURATION` factor | 0 … 3.0 |
| `CROP` x, y, width, height | x,y ≥ 0; width,height ≥ 1; rectangle within current image |
| `SHARPEN` strength | 0 … 3.0 |
| `THRESHOLD` value | 0 … 255 |
| `MEDIAN_BLUR` kernel | odd 3 … 25 |
| Program length | ≤ 100 lines, ≤ 50 operations |

Filenames are names, not paths — see [SECURITY.md §6](SECURITY.md#6-path-traversal-protection).

## Semantic rules

1. `LOAD` is the first command and appears exactly once.
2. `SAVE` appears at least once, and nothing follows the final `SAVE`.
3. Argument types must match the command's signature.
4. Numeric arguments must be in range.
5. `EDGE` thresholds must satisfy `low < high`.

Rule 2 is enforced rather than optimised away: an operation after `SAVE` is
almost always a mistake, and silently deleting it would hide the mistake.

## Examples

Thumbnail with softening:

```
LOAD "photo.jpg"
RESIZE 320 240
BLUR 2
SAVE "thumb.jpg"
```

Edge map — note the ordering, which the optimiser will fix for you:

```
LOAD "photo.jpg"
BLUR 3          # denoise before edge detection
EDGE 80 160
RESIZE 400 300  # the optimiser hoists this above BLUR and EDGE
SAVE "edges.png"
```

Rotations that cancel, folded away entirely:

```
LOAD "photo.jpg"
ROTATE 90
ROTATE 270      # net zero; both instructions are removed
GRAYSCALE
SAVE "grey.png"
```

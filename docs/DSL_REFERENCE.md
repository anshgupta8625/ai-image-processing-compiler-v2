# DSL Reference

## Grammar

```
program   := statement*
statement := COMMAND argument* NEWLINE
argument  := NUMBER | STRING
COMMAND   := LOAD | SAVE | RESIZE | GRAYSCALE | BLUR | ROTATE | EDGE | VIGNETTE
STRING    := '"' [^"\n\\]{0,128} '"'
NUMBER    := '-'? [0-9]+
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

## Ranges

| Argument | Range |
|---|---|
| `RESIZE` width, height | 1 … 4096, product ≤ 16,777,216 |
| `BLUR` radius | 1 … 25 |
| `ROTATE` angle | multiple of 90, −360 … 360 |
| `EDGE` thresholds | `0 ≤ low < high ≤ 500` |
| `VIGNETTE` strength | 1 … 100 |
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

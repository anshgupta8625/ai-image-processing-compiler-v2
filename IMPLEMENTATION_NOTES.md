# Image DSL: eight additional commands

This patch adds these commands to the compiler:

- `BRIGHTNESS n`: integer offset, -100 through 100.
- `CONTRAST factor`: numeric multiplier, 0.1 through 3.0; 1.0 is neutral.
- `SATURATION factor`: numeric multiplier, 0 through 3.0; 1.0 is neutral.
- `FLIP HORIZONTAL` or `FLIP VERTICAL`.
- `CROP x y width height`: non-negative origin, positive dimensions, and rectangle must fit the current image at execution time.
- `SHARPEN strength`: 0 through 3.0.
- `THRESHOLD value`: integer 0 through 255, returns a binary grayscale image.
- `MEDIAN_BLUR kernel`: odd integer 3 through 25.

## Apply

Extract this patch at the repository root and allow it to merge/overwrite the listed files. It contains only changed source/docs/tests, not a complete replacement for the repository. Existing `backend/compiler/tokens.py` and `backend/compiler/ast_nodes.py` require no changes.

Then from the backend directory run:

```powershell
python -m pytest -q
```

From the frontend directory run:

```powershell
npm test
npm run build
```

Note: CROP is checked against the image dimensions at runtime because preceding commands may resize or crop the image. The optimizer tracks crop output dimensions for cost estimates and does not reorder the new effects across existing operations.

"""Safe execution back end.

The dispatch table below is the security boundary at runtime. It maps IR opcode
strings to module-level functions, bound once at import. Execution does a dict
lookup and nothing else:

    handler = _HANDLERS[instr.op]      # KeyError if not whitelisted
    image = handler(image, *instr.args)

No getattr, no eval, no import driven by user text. If an opcode is not in the
table the program stops; there is no default branch.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

import security as sec

from .errors import ExecutionError
from .ir import IRProgram


def _op_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _op_resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    # INTER_AREA is the right choice when shrinking; it averages the source
    # pixels instead of sampling them, so downscales do not alias.
    shrinking = width * height < image.shape[0] * image.shape[1]
    interp = cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR
    return cv2.resize(image, (width, height), interpolation=interp)


def _op_blur(image: np.ndarray, radius: int) -> np.ndarray:
    kernel = radius * 2 + 1  # GaussianBlur requires an odd kernel size
    return cv2.GaussianBlur(image, (kernel, kernel), 0)


def _op_rotate(image: np.ndarray, angle: int) -> np.ndarray:
    # Only multiples of 90 are legal, so use the exact transpose-based rotations
    # rather than a general affine warp. No interpolation, no edge padding.
    return {
        0: lambda im: im,
        90: lambda im: cv2.rotate(im, cv2.ROTATE_90_CLOCKWISE),
        180: lambda im: cv2.rotate(im, cv2.ROTATE_180),
        270: lambda im: cv2.rotate(im, cv2.ROTATE_90_COUNTERCLOCKWISE),
    }[angle % 360](image)


def _op_edge(image: np.ndarray, low: int, high: int) -> np.ndarray:
    gray = _op_grayscale(image)
    return cv2.Canny(gray, low, high)


def _axis(n: int) -> np.ndarray:
    """Coordinates running -1 .. 1 across an axis of n pixels."""
    if n == 1:
        return np.zeros(1, dtype=np.float32)
    return np.linspace(-1.0, 1.0, n, dtype=np.float32)


def _op_vignette(image: np.ndarray, strength: int) -> np.ndarray:
    """Darken towards the corners with a radial falloff.

    The falloff is computed in normalised coordinates (centre 0, edges +-1), so
    the same strength gives the same look at any resolution. That is also why
    the optimiser may hoist a shrinking RESIZE above it: vignetting a small
    image and then enlarging is the same picture as the other order, up to
    interpolation. The factor is 1 at the centre and 1 - strength/100 at the
    corners, and is built as a broadcast sum of two 1-D arrays rather than a
    full meshgrid, which halves the temporary memory on large images.
    """
    h, w = image.shape[:2]
    k = 0.5 * strength / 100.0
    ys, xs = _axis(h), _axis(w)
    factor = 1.0 - k * (ys[:, None] ** 2 + xs[None, :] ** 2)
    np.clip(factor, 0.0, 1.0, out=factor)

    if image.ndim == 2:
        return np.rint(image * factor).astype(np.uint8)
    out = np.empty_like(image)
    for channel in range(image.shape[2]):
        out[:, :, channel] = np.rint(image[:, :, channel] * factor)
    return out


_HANDLERS = {
    "GRAYSCALE": _op_grayscale,
    "RESIZE": _op_resize,
    "BLUR": _op_blur,
    "ROTATE": _op_rotate,
    "EDGE": _op_edge,
    "VIGNETTE": _op_vignette,
}


class Executor:
    def __init__(self, upload_dir: Path, output_dir: Path):
        self.upload_dir = Path(upload_dir)
        self.output_dir = Path(output_dir)

    def run(self, ir: IRProgram, stored_input: str, persist: bool = True) -> dict:
        """Execute the IR.

        `persist=False` still does the encode-and-write work, so SAVE is timed
        honestly, but removes the file afterwards. Benchmark repeats use it so
        that timing a pipeline five times does not leave five images on disk.
        """
        timings: list[dict] = []
        image = None
        output_name = None
        started = time.perf_counter()

        for instr in ir.instrs:
            step_start = time.perf_counter()

            if instr.op == "LOAD":
                image = self._load(stored_input)
            elif instr.op == "SAVE":
                output_name = self._save(image, instr.args[0], persist)
            else:
                handler = _HANDLERS.get(instr.op)
                if handler is None:
                    # Unreachable via the public API; a defensive stop rather
                    # than a fallback that guesses what the user meant.
                    raise ExecutionError(f"Operation {instr.op} is not executable.",
                                         instr.line)
                if image is None:
                    raise ExecutionError("No image loaded.", instr.line)
                try:
                    image = handler(image, *instr.args)
                except cv2.error:
                    raise ExecutionError(
                        f"{instr.op} could not be applied to this image.", instr.line
                    ) from None

            elapsed_ms = (time.perf_counter() - step_start) * 1000
            timings.append({
                "line": instr.line,
                "op": instr.op,
                "args": instr.args,
                "ms": round(elapsed_ms, 3),
                "shape": list(image.shape[:2]) if image is not None else None,
            })

            if time.perf_counter() - started > sec.Limits.MAX_EXECUTION_SECONDS:
                raise ExecutionError("Program exceeded the execution time limit.",
                                     instr.line)

        return {
            "output_file": output_name,
            "total_ms": round((time.perf_counter() - started) * 1000, 3),
            "steps": timings,
        }

    def _load(self, stored_input: str):
        path = sec.resolve_inside(self.upload_dir, stored_input)
        if not path.exists():
            raise ExecutionError("The input image could not be found.")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ExecutionError("The input image could not be decoded.")
        height, width = image.shape[:2]
        # Re-check after decode: this is what catches a decompression bomb, a
        # small file that expands into an enormous raster.
        sec.validate_image_dimensions(width, height)
        return image

    def _save(self, image, requested_name: str, persist: bool = True) -> str:
        if image is None:
            raise ExecutionError("Nothing to save; no image was loaded.")
        safe_name = sec.generate_stored_name(requested_name)
        path = sec.resolve_inside(self.output_dir, safe_name)
        if not cv2.imwrite(str(path), image):
            raise ExecutionError("The output image could not be written.")
        if not persist:
            path.unlink(missing_ok=True)
            return safe_name
        return safe_name

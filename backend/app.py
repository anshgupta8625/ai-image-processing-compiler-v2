"""FastAPI application.

Three endpoints: upload an image, compile a program (no execution), and run a
program. Compile is separate from run so the frontend can show the token
stream, AST and IR while the user is still editing, before any image work
happens.

Error policy: SecurityError and CompilerError both carry user-safe messages and
are serialised directly. Anything else is caught by the catch-all handler,
logged in full, and returned as a generic 500 — a stack trace never crosses the
wire. See docs/SECURITY.md section 9.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import config
import security as sec
from compiler.errors import CompilerError
from compiler.executor import Executor
from compiler.pipeline import compile_program, execute

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("imgdsl.api")

app = FastAPI(title="Image DSL Compiler", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

executor = Executor(config.UPLOAD_DIR, config.OUTPUT_DIR)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CompileRequest(BaseModel):
    source: str = Field(..., max_length=sec.Limits.MAX_DSL_CHARS)
    width: int = Field(1000, ge=1, le=sec.Limits.MAX_IMAGE_WIDTH)
    height: int = Field(1000, ge=1, le=sec.Limits.MAX_IMAGE_HEIGHT)


class RunRequest(CompileRequest):
    image_id: str = Field(..., max_length=80)
    benchmark: bool = True


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@app.exception_handler(sec.SecurityError)
async def handle_security_error(_: Request, exc: sec.SecurityError):
    return JSONResponse(status_code=400, content=exc.to_response())


@app.exception_handler(CompilerError)
async def handle_compiler_error(_: Request, exc: CompilerError):
    return JSONResponse(status_code=400, content={"error": "Compilation failed",
                                                  **exc.to_dict()})


@app.exception_handler(Exception)
async def handle_unexpected(_: Request, exc: Exception):
    log.exception("unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal error", "message": "Something went wrong."},
    )


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    raw = request.headers.get("content-length")
    try:
        sec.validate_request_size(int(raw) if raw else None)
    except sec.SecurityError as exc:
        return JSONResponse(status_code=413, content=exc.to_response())
    return await call_next(request)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok", "version": app.version}


@app.get("/api/limits")
def limits():
    """The frontend renders these, so they are never hard-coded twice."""
    return {
        "commands": sorted(sec.ALLOWED_COMMANDS),
        "extensions": sorted(e.lstrip(".") for e in sec.ALLOWED_EXTENSIONS),
        "max_upload_mb": sec.Limits.MAX_UPLOAD_BYTES // (1024 * 1024),
        "max_dimensions": [sec.Limits.MAX_IMAGE_WIDTH, sec.Limits.MAX_IMAGE_HEIGHT],
        "max_lines": sec.Limits.MAX_DSL_LINES,
        "max_operations": sec.Limits.MAX_OPERATIONS,
        "max_blur_radius": sec.Limits.MAX_BLUR_RADIUS,
        "max_median_blur_kernel": sec.Limits.MAX_MEDIAN_BLUR_KERNEL,
        "max_resize_dim": sec.Limits.MAX_RESIZE_DIM,
        "vignette_range": [sec.Limits.MIN_VIGNETTE_STRENGTH,
                           sec.Limits.MAX_VIGNETTE_STRENGTH],
    }


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    stored = sec.validate_upload(file.filename or "", data, file.content_type)

    path = sec.resolve_inside(config.UPLOAD_DIR, stored)
    path.write_bytes(data)
    _sweep_old_uploads()

    # Dimensions come from a decode, which is also a validity check.
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        path.unlink(missing_ok=True)
        raise sec.SecurityError("The file could not be decoded as an image.",
                                code="INVALID_IMAGE")
    height, width = image.shape[:2]
    sec.validate_image_dimensions(width, height)

    log.info("upload accepted id=%s %dx%d %d bytes", stored, width, height, len(data))
    return {
        "image_id": stored,
        "width": width,
        "height": height,
        "megapixels": round(width * height / 1_000_000, 3),
        "security": sec.run_checklist("LOAD \"x.png\"\nSAVE \"y.png\"",
                                      upload=(file.filename or "", data)).to_dict(),
    }


def _rejection(exc: Exception, source: str):
    """Serialise a rejected program together with the checklist that caught it.

    The checklist is only attached when it actually fails, so the UI can show
    *which* gate stopped the program (path, resource limit, whitelist, ...)
    rather than a bare error. If every gate passed, the error is not a security
    rejection at all and falls through to the ordinary handlers.
    """
    report = sec.run_checklist(source)
    if report.ok:
        raise exc
    if isinstance(exc, sec.SecurityError):
        body = exc.to_response()
    else:
        body = {"error": "Compilation failed", **exc.to_dict()}
    body["security"] = report.to_dict()
    return JSONResponse(status_code=400, content=body)


@app.post("/api/compile")
def compile_only(req: CompileRequest):
    megapixels = req.width * req.height / 1_000_000
    try:
        result = compile_program(req.source, megapixels)
    except (sec.SecurityError, CompilerError) as exc:
        return _rejection(exc, req.source)
    result.pop("_unoptimized", None)
    result.pop("_optimized", None)
    result["security"] = sec.run_checklist(req.source).to_dict()
    return result


@app.post("/api/run")
def run(req: RunRequest):
    stored = sec.safe_basename(req.image_id)
    megapixels = req.width * req.height / 1_000_000

    try:
        compiled = compile_program(req.source, megapixels)
    except (sec.SecurityError, CompilerError) as exc:
        return _rejection(exc, req.source)
    started = time.perf_counter()
    outcome = execute(compiled, stored, executor, benchmark=req.benchmark)
    log.info("run completed in %.1f ms", (time.perf_counter() - started) * 1000)

    payload = {k: v for k, v in compiled.items() if not k.startswith("_")}
    payload.update(outcome)
    payload["security"] = sec.run_checklist(req.source).to_dict()
    payload["output_url"] = f"/api/image/{outcome['output_file']}"
    return payload


@app.get("/api/image/{image_id}")
def serve_image(image_id: str):
    path = sec.resolve_inside(config.OUTPUT_DIR, image_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(path)


# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------

def _sweep_old_uploads() -> None:
    """Remove uploads older than the TTL.

    Called opportunistically on upload rather than from a scheduler: this is a
    single-process academic deployment, and a background thread would be more
    moving parts than the problem needs.
    """
    cutoff = time.time() - config.UPLOAD_TTL_SECONDS
    for directory in (config.UPLOAD_DIR, config.OUTPUT_DIR):
        for item in directory.iterdir():
            try:
                if item.is_file() and item.stat().st_mtime < cutoff:
                    item.unlink()
            except OSError:
                log.debug("could not remove a stale file", exc_info=True)

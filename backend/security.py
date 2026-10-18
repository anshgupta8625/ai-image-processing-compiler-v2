"""
Security & Safe Execution Layer
===============================

Single source of truth for all input validation in the Image-DSL compiler.

Design rule: the compiler NEVER executes user-supplied strings. Commands are
matched against a frozen whitelist and dispatched to fixed Python callables.
There is no eval(), exec(), os.system(), subprocess or importlib anywhere in
the execution path.

This is an academic security layer. See docs/SECURITY.md for the threat model
and its documented limitations.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

LOG = logging.getLogger("imgdsl.security")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class Limits:
    """Resource ceilings. Tune these in one place."""

    MAX_UPLOAD_BYTES = 10 * 1024 * 1024      # 10 MB per image
    MAX_REQUEST_BYTES = 12 * 1024 * 1024     # 12 MB per HTTP request
    MAX_IMAGE_WIDTH = 4096
    MAX_IMAGE_HEIGHT = 4096
    MAX_PIXELS = 4096 * 4096                 # decompression-bomb guard
    MAX_DSL_LINES = 100
    MAX_DSL_CHARS = 8_000
    MAX_OPERATIONS = 50                      # pipeline length
    MAX_BLUR_RADIUS = 25
    MIN_VIGNETTE_STRENGTH = 1
    MAX_VIGNETTE_STRENGTH = 100
    MIN_RESIZE_DIM = 1
    MAX_RESIZE_DIM = 4096
    MAX_EXECUTION_SECONDS = 10


ALLOWED_COMMANDS = frozenset({
    "LOAD", "SAVE", "RESIZE", "GRAYSCALE", "BLUR", "ROTATE", "EDGE", "VIGNETTE",
})

ALLOWED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})

ALLOWED_MIME_TYPES = frozenset({
    "image/png", "image/jpeg", "image/webp",
})

# Magic-byte signatures, checked because a client-supplied MIME type is only a
# hint and an extension can be renamed.
_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)

# Filenames we are willing to create or read inside our own directories.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

# Pre-scan patterns. The whitelist already rejects all of these, but scanning
# first lets us return a specific, honest error and log the attempt.
_INJECTION_PATTERNS = re.compile(
    r"""(?ix)
    \b(?:eval|exec|compile|__import__|globals|locals|getattr|setattr)\s*\(
    | \bos\s*\.\s*(?:system|popen|remove|environ)
    | \bsubprocess\b
    | \bimport\s+\w
    | [;|&`$]                      # shell metacharacters
    | \$\{ | <\? | <script         # template / markup injection
    """,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SecurityError(Exception):
    """Raised for any rejected input.

    `message` is safe to show the user: it never contains server paths,
    environment values or stack detail. `detail` is for the server log only.
    """

    def __init__(self, message: str, *, code: str = "SECURITY_ERROR",
                 detail: str | None = None, line: int | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.line = line
        self.detail = detail or message

    def to_response(self) -> dict[str, Any]:
        """The only shape that should ever reach the frontend."""
        body: dict[str, Any] = {"error": "Security Error",
                                "code": self.code,
                                "message": self.message}
        if self.line is not None:
            body["line"] = self.line
        return body


def _reject(message: str, code: str, *, detail: str | None = None,
            line: int | None = None) -> "SecurityError":
    LOG.warning("security reject code=%s line=%s detail=%s",
                code, line, detail or message)
    return SecurityError(message, code=code, detail=detail, line=line)


# ---------------------------------------------------------------------------
# A. DSL input validation
# ---------------------------------------------------------------------------

def scan_source(source: str) -> None:
    """Cheap pre-lexer scan for obvious injection attempts and size abuse."""
    if not source or not source.strip():
        raise _reject("The program is empty.", "EMPTY_PROGRAM")

    if len(source) > Limits.MAX_DSL_CHARS:
        raise _reject(
            f"Program exceeds the maximum length of {Limits.MAX_DSL_CHARS} characters.",
            "PROGRAM_TOO_LONG")

    lines = source.splitlines()
    if len(lines) > Limits.MAX_DSL_LINES:
        raise _reject(
            f"Program exceeds the maximum of {Limits.MAX_DSL_LINES} lines.",
            "TOO_MANY_LINES")

    for number, line in enumerate(lines, start=1):
        code = line.split("#", 1)[0]
        if _INJECTION_PATTERNS.search(code):
            raise _reject(
                "This program contains characters or keywords that are not part "
                "of the DSL. Only the listed image commands are allowed.",
                "INJECTION_BLOCKED", detail=f"pattern match in line {number}",
                line=number)


def validate_command(name: str, *, line: int | None = None) -> str:
    """Return the canonical command name, or reject it."""
    candidate = (name or "").strip().upper()
    if candidate not in ALLOWED_COMMANDS:
        raise _reject(
            f"Unknown command '{candidate[:20]}'. Allowed commands: "
            + ", ".join(sorted(ALLOWED_COMMANDS)) + ".",
            "UNKNOWN_COMMAND", line=line)
    return candidate


def validate_operation_count(count: int) -> None:
    if count > Limits.MAX_OPERATIONS:
        raise _reject(
            f"Program uses {count} operations; the maximum is {Limits.MAX_OPERATIONS}.",
            "TOO_MANY_OPERATIONS")


# ---------------------------------------------------------------------------
# Parameter validation (per command)
# ---------------------------------------------------------------------------

def _as_int(value: Any, field_name: str, line: int | None) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise _reject(f"{field_name} must be a whole number.",
                      "INVALID_PARAMETER_TYPE", line=line)
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise _reject(f"{field_name} must be a whole number.",
                      "INVALID_PARAMETER_TYPE", line=line) from None
    return number


def validate_resize(width: Any, height: Any, *, line: int | None = None) -> tuple[int, int]:
    w = _as_int(width, "Width", line)
    h = _as_int(height, "Height", line)
    for label, value in (("Width", w), ("Height", h)):
        if value < Limits.MIN_RESIZE_DIM:
            raise _reject(f"{label} must be at least {Limits.MIN_RESIZE_DIM}.",
                          "INVALID_RESIZE", line=line)
        if value > Limits.MAX_RESIZE_DIM:
            raise _reject(
                f"{label} exceeds the maximum allowed value of {Limits.MAX_RESIZE_DIM}.",
                "INVALID_RESIZE", line=line)
    if w * h > Limits.MAX_PIXELS:
        raise _reject("Requested output image is too large.",
                      "INVALID_RESIZE", line=line)
    return w, h


def validate_blur(radius: Any, *, line: int | None = None) -> int:
    r = _as_int(radius, "Blur radius", line)
    if r < 1 or r > Limits.MAX_BLUR_RADIUS:
        raise _reject(
            f"Blur radius must be between 1 and {Limits.MAX_BLUR_RADIUS}.",
            "INVALID_BLUR", line=line)
    return r


def validate_vignette(strength: Any, *, line: int | None = None) -> int:
    v = _as_int(strength, "Vignette strength", line)
    if not Limits.MIN_VIGNETTE_STRENGTH <= v <= Limits.MAX_VIGNETTE_STRENGTH:
        raise _reject(
            f"Vignette strength must be between {Limits.MIN_VIGNETTE_STRENGTH} "
            f"and {Limits.MAX_VIGNETTE_STRENGTH}.",
            "INVALID_VIGNETTE", line=line)
    return v


def validate_rotate(angle: Any, *, line: int | None = None) -> int:
    a = _as_int(angle, "Angle", line)
    if a % 90 != 0 or not -360 <= a <= 360:
        raise _reject("Angle must be a multiple of 90 between -360 and 360.",
                      "INVALID_ANGLE", line=line)
    return a % 360


# ---------------------------------------------------------------------------
# B. Path traversal protection
# ---------------------------------------------------------------------------

def safe_basename(user_path: str, *, line: int | None = None) -> str:
    """Strip every directory component and validate what is left."""
    raw = (user_path or "").strip().strip('"').strip("'")
    if not raw:
        raise _reject("Invalid file path.", "INVALID_PATH", line=line)

    if "\x00" in raw:
        raise _reject("Invalid file path.", "INVALID_PATH",
                      detail="null byte in path", line=line)

    # Reject rather than silently strip: a program that asks for "../x.png"
    # is asking for something the DSL does not offer, and should be told so.
    if re.search(r"[\\/]", raw) or ".." in raw or raw.startswith("."):
        raise _reject("Invalid file path.", "INVALID_PATH",
                      detail="path separator or dot-segment in name", line=line)

    name = raw
    if not _SAFE_NAME_RE.match(name):
        raise _reject("Invalid file path.", "INVALID_PATH",
                      detail=f"rejected basename ({len(raw)} chars)", line=line)

    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise _reject(
            "Unsupported file type. Allowed: "
            + ", ".join(sorted(e.lstrip('.') for e in ALLOWED_EXTENSIONS)) + ".",
            "INVALID_EXTENSION", line=line)
    return name


def PurePosixName(raw: str) -> str:  # noqa: N802 - small helper, kept explicit
    """Last path component, treating both / and \\ as separators."""
    return re.split(r"[\\/]", raw)[-1]


def resolve_inside(base_dir: Path, filename: str, *, line: int | None = None) -> Path:
    """Resolve `filename` strictly inside `base_dir`.

    Uses the resolved real path so symlinks cannot escape the sandbox.
    """
    base = Path(base_dir).resolve()
    base.mkdir(parents=True, exist_ok=True)
    candidate = (base / safe_basename(filename, line=line)).resolve()
    if not candidate.is_relative_to(base):
        raise _reject("Invalid file path.", "PATH_TRAVERSAL",
                      detail="resolved outside sandbox", line=line)
    return candidate


def generate_stored_name(original_name: str) -> str:
    """Never store a user-controlled filename. Keep only the extension."""
    ext = Path(PurePosixName(original_name or "")).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise _reject("Unsupported file type.", "INVALID_EXTENSION")
    return f"{uuid.uuid4().hex}{ext}"


# ---------------------------------------------------------------------------
# C. File upload security
# ---------------------------------------------------------------------------

def sniff_mime(head: bytes) -> str | None:
    for signature, mime in _MAGIC:
        if head.startswith(signature):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_upload(filename: str, data: bytes, declared_mime: str | None = None) -> str:
    """Validate an uploaded image. Returns the safe stored filename."""
    if not data:
        raise _reject("The uploaded file is empty.", "EMPTY_UPLOAD")

    if len(data) > Limits.MAX_UPLOAD_BYTES:
        raise _reject(
            f"File exceeds the maximum upload size of "
            f"{Limits.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
            "UPLOAD_TOO_LARGE", detail=f"{len(data)} bytes")

    ext = Path(PurePosixName(filename or "")).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise _reject(
            "Unsupported file type. Allowed: PNG, JPG, JPEG, WEBP.",
            "INVALID_EXTENSION")

    if declared_mime and declared_mime.split(";")[0].strip() not in ALLOWED_MIME_TYPES:
        raise _reject("Unsupported file type.", "INVALID_MIME",
                      detail=f"declared {declared_mime!r}")

    actual = sniff_mime(data[:16])
    if actual is None:
        raise _reject("The file does not appear to be a valid image.",
                      "CONTENT_MISMATCH")
    if actual == "image/jpeg" and ext not in (".jpg", ".jpeg"):
        raise _reject("File contents do not match the file extension.",
                      "CONTENT_MISMATCH")
    if actual == "image/png" and ext != ".png":
        raise _reject("File contents do not match the file extension.",
                      "CONTENT_MISMATCH")
    if actual == "image/webp" and ext != ".webp":
        raise _reject("File contents do not match the file extension.",
                      "CONTENT_MISMATCH")

    return generate_stored_name(filename)


# ---------------------------------------------------------------------------
# D. Image size / resource limits
# ---------------------------------------------------------------------------

def validate_image_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise _reject("The image could not be read.", "INVALID_IMAGE")
    if width > Limits.MAX_IMAGE_WIDTH or height > Limits.MAX_IMAGE_HEIGHT:
        raise _reject(
            "Image exceeds the maximum allowed dimensions "
            f"({Limits.MAX_IMAGE_WIDTH}x{Limits.MAX_IMAGE_HEIGHT}).",
            "IMAGE_TOO_LARGE")
    if width * height > Limits.MAX_PIXELS:
        raise _reject("Image exceeds the maximum allowed pixel count.",
                      "IMAGE_TOO_LARGE")


# ---------------------------------------------------------------------------
# I / J. Request handling and frontend status
# ---------------------------------------------------------------------------

def validate_request_size(content_length: int | None) -> None:
    if content_length is not None and content_length > Limits.MAX_REQUEST_BYTES:
        raise _reject("Request body is too large.", "REQUEST_TOO_LARGE")


@dataclass
class SecurityReport:
    """Per-run checklist rendered by the frontend 'Security & Validation' panel."""

    checks: list[dict[str, Any]] = field(default_factory=list)

    def record(self, name: str, passed: bool, message: str = "", *,
               code: str | None = None, line: int | None = None) -> None:
        entry: dict[str, Any] = {
            "name": name,
            "passed": passed,
            "message": message,
            # Plain-English description of the gate, so the UI can explain
            # what each tick means without hard-coding the text a second time.
            "what": CHECK_INFO.get(name, ""),
        }
        if code is not None:
            entry["code"] = code
        if line is not None:
            entry["line"] = line
        self.checks.append(entry)

    @property
    def ok(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.ok, "checks": self.checks}


CHECK_NAMES = (
    "Command validation",
    "File validation",
    "Path validation",
    "Resource limits",
    "Safe execution",
)

CHECK_INFO = {
    "Command validation": (
        "Scans the raw program for injection patterns (eval, os.system, shell "
        "metacharacters, markup) and enforces length limits before the lexer runs."
    ),
    "File validation": (
        "An uploaded image must agree on extension, declared type and magic "
        "bytes, and stay under the size cap. A renamed script is refused."
    ),
    "Path validation": (
        "Every filename is rejected, not cleaned up, if it contains a path "
        "separator, '..', a leading dot or a disallowed extension."
    ),
    "Resource limits": (
        "Hard ceilings on operations, blur radius, resize size, vignette "
        "strength and image pixels stop denial-of-service by oversized work."
    ),
    "Safe execution": (
        "Only whitelisted commands exist, and they run through a fixed "
        "dispatch table: no eval, no getattr on user text."
    ),
}

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_STRING_LITERAL_RE = re.compile(r'"[^"\n]*"')
_INT_RE = re.compile(r"-?\d+")


def _statements(source: str) -> Iterable[tuple[int, str]]:
    """(line number, code with comments removed) for every non-blank line."""
    for number, raw in enumerate(source.splitlines(), start=1):
        code = raw.split("#", 1)[0].strip()
        if code:
            yield number, code


def check_paths(source: str) -> None:
    """Every quoted filename in the program must be a safe basename."""
    for number, code in _statements(source):
        for literal in _STRING_LITERAL_RE.findall(code):
            safe_basename(literal[1:-1], line=number)


def check_resource_limits(source: str) -> None:
    """Operation count and numeric parameters, checked on the raw text.

    The semantic analyser enforces the same ceilings through the same
    validators; running them here as well means the checklist reports the gate
    that actually stopped a program rather than a generic compile error.
    """
    validate_operation_count(sum(1 for _ in _statements(source)))

    for number, code in _statements(source):
        word = _WORD_RE.match(code)
        if not word:
            continue
        name = word.group(0).upper()
        rest = _STRING_LITERAL_RE.sub(" ", code[word.end():])
        numbers = _INT_RE.findall(rest)

        if name == "RESIZE" and len(numbers) == 2:
            validate_resize(numbers[0], numbers[1], line=number)
        elif name == "BLUR" and len(numbers) == 1:
            validate_blur(numbers[0], line=number)
        elif name == "ROTATE" and len(numbers) == 1:
            validate_rotate(numbers[0], line=number)
        elif name == "VIGNETTE" and len(numbers) == 1:
            validate_vignette(numbers[0], line=number)


def check_whitelist(source: str) -> None:
    """The first word of every statement must be a whitelisted command."""
    for number, code in _statements(source):
        word = _WORD_RE.match(code)
        validate_command(word.group(0) if word else code.split()[0], line=number)


def run_checklist(source: str, upload: tuple[str, bytes] | None = None) -> SecurityReport:
    """Run every check, building the report the frontend renders.

    Stops at the first failure and marks the remaining checks as not reached.
    """
    report = SecurityReport()
    steps: Iterable[tuple[str, Any]] = (
        ("Command validation", lambda: scan_source(source)),
        ("File validation",
         (lambda: validate_upload(*upload)) if upload else (lambda: None)),
        ("Path validation", lambda: check_paths(source)),
        ("Resource limits", lambda: check_resource_limits(source)),
        ("Safe execution", lambda: check_whitelist(source)),
    )
    failed = False
    for name, step in steps:
        if failed:
            report.record(name, False, "Not reached.")
            continue
        try:
            step()
            report.record(name, True)
        except SecurityError as exc:
            report.record(name, False, exc.message, code=exc.code, line=exc.line)
            failed = True
    return report

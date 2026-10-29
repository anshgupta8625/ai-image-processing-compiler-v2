"""Semantic analysis.

Syntax says the program is well-formed. Semantics says it is *meaningful*:

  1. Exactly one LOAD, and it comes first.
  2. At least one SAVE, and nothing after the last one.
  3. Every argument has the right type and lies inside its legal range.
  4. Filenames are safe (delegated to the security layer, not reimplemented).
  5. EDGE thresholds are ordered low < high.

Range checks call into security.py rather than duplicating the limits, so there
is exactly one place where "max blur radius" is defined.
"""

from __future__ import annotations

import security as sec

from .ast_nodes import Program
from .errors import SemanticError


def _security_to_semantic(exc: sec.SecurityError, line: int) -> SemanticError:
    """Translate a security rejection into a compiler diagnostic.

    The user-safe message crosses over; the internal detail does not.
    """
    return SemanticError(exc.message, line)


def analyse(program: Program) -> dict:
    commands = program.commands

    loads = [c for c in commands if c.name == "LOAD"]
    saves = [c for c in commands if c.name == "SAVE"]

    if not loads:
        raise SemanticError("Program must begin with a LOAD command.", commands[0].line)
    if len(loads) > 1:
        raise SemanticError(
            "Only one LOAD is allowed; this program has "
            f"{len(loads)}.", loads[1].line
        )
    if commands[0].name != "LOAD":
        raise SemanticError("LOAD must be the first command.", commands[0].line)
    if not saves:
        raise SemanticError("Program must end with a SAVE command.", commands[-1].line)

    last_save = max(i for i, c in enumerate(commands) if c.name == "SAVE")
    if last_save != len(commands) - 1:
        dead = commands[last_save + 1]
        raise SemanticError(
            f"{dead.name} appears after the final SAVE and would have no effect.",
            dead.line,
        )

    try:
        sec.validate_operation_count(len(commands))
    except sec.SecurityError as exc:
        raise _security_to_semantic(exc, commands[-1].line) from None

    for cmd in commands:
        _check_args(cmd)

    return {
        "operations": len(commands),
        "input": loads[0].args[0],
        "output": saves[-1].args[0],
    }


def _check_args(cmd) -> None:
    line = cmd.line
    try:
        if cmd.name in ("LOAD", "SAVE"):
            if not isinstance(cmd.args[0], str):
                raise SemanticError(f"{cmd.name} expects a quoted filename.", line)
            sec.safe_basename(cmd.args[0], line=line)

        elif cmd.name == "RESIZE":
            _require_ints(cmd, line)
            cmd.args = list(sec.validate_resize(cmd.args[0], cmd.args[1], line=line))

        elif cmd.name == "BLUR":
            _require_ints(cmd, line)
            cmd.args = [sec.validate_blur(cmd.args[0], line=line)]

        elif cmd.name == "VIGNETTE":
            _require_ints(cmd, line)
            cmd.args = [sec.validate_vignette(cmd.args[0], line=line)]

        elif cmd.name == "ROTATE":
            _require_ints(cmd, line)
            cmd.args = [sec.validate_rotate(cmd.args[0], line=line)]

        elif cmd.name == "EDGE":
            _require_ints(cmd, line)
            if len(cmd.args) == 2:
                low, high = cmd.args
                if not 0 <= low < high <= 500:
                    raise SemanticError(
                        "EDGE thresholds must satisfy 0 <= low < high <= 500.", line
                    )
            else:
                cmd.args = [100, 200]  # documented defaults

        elif cmd.name == "BRIGHTNESS":
            _require_ints(cmd, line)
            cmd.args = [sec.validate_brightness(cmd.args[0], line=line)]

        elif cmd.name == "CONTRAST":
            cmd.args = [sec.validate_contrast(cmd.args[0], line=line)]

        elif cmd.name == "SATURATION":
            cmd.args = [sec.validate_saturation(cmd.args[0], line=line)]

        elif cmd.name == "FLIP":
            cmd.args = [sec.validate_flip(cmd.args[0], line=line)]

        elif cmd.name == "CROP":
            _require_ints(cmd, line)
            cmd.args = list(sec.validate_crop(*cmd.args, line=line))

        elif cmd.name == "SHARPEN":
            cmd.args = [sec.validate_sharpen(cmd.args[0], line=line)]

        elif cmd.name == "THRESHOLD":
            _require_ints(cmd, line)
            cmd.args = [sec.validate_threshold(cmd.args[0], line=line)]

        elif cmd.name == "MEDIAN_BLUR":
            _require_ints(cmd, line)
            cmd.args = [sec.validate_median_blur(cmd.args[0], line=line)]

    except sec.SecurityError as exc:
        raise _security_to_semantic(exc, line) from None


def _require_ints(cmd, line: int) -> None:
    for arg in cmd.args:
        if not isinstance(arg, int):
            raise SemanticError(
                f"{cmd.name} expects numeric arguments, found {arg!r}.", line
            )

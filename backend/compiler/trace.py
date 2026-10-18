"""Per-line compilation trace.

The stage tabs (Tokens, AST, IR, ...) each show one stage for the whole
program. This module turns the same artefacts around: for every source line it
reports what *each* stage did with that line, from the lexer to the executor.
That is the view a reader needs to follow a single statement through the
compiler, and it is what the "Line by line" tab renders.

Nothing here makes a decision. Every fact is read from an artefact another
stage already produced (tokens, AST, IR, the optimiser's event log, the
executor's timings), so the trace cannot disagree with the compiler. The one
thing it adds is wording.

Everything in a trace derives from the user's own program, so none of it can
carry a server path or an internal detail.
"""

from __future__ import annotations

import copy

import security as sec

from .ast_nodes import Command, Program
from .ir import COST_PER_MP, IRProgram, profile
from .parser import ARITY
from .tokens import Token, TokenType


def _fmt_args(args: list) -> str:
    return ", ".join(str(a) for a in args)


def _instr_repr(op: str, args: list) -> str:
    return f"{op}({_fmt_args(args)})"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# ---------------------------------------------------------------------------
# Stage descriptions
# ---------------------------------------------------------------------------

def _lexer_stage(line_tokens: list[Token], has_newline: bool, source_line: str) -> dict:
    notes = []
    command = next((t for t in line_tokens if t.type == TokenType.COMMAND), None)
    if command is not None:
        written = source_line.strip().split(None, 1)[0] if source_line.strip() else ""
        # A keyword written as `blur` or `Blur` is stored upper-case.
        word = written.split('"')[0]
        if word and word != command.value:
            notes.append(f"Keyword {word!r} is case-insensitive and was stored as {command.value}.")
    if any(t.type == TokenType.STRING for t in line_tokens):
        notes.append("Quoted text became one STRING token; the lexer only accepts "
                     "up to 128 characters and no newline or backslash inside it.")
    if "#" in source_line:
        notes.append("Everything from # to the end of the line is a comment and "
                     "produces no token.")
    return {
        "tokens": [
            {"type": t.type.name, "value": t.value, "column": t.column}
            for t in line_tokens
        ],
        "terminator": "NEWLINE" if has_newline else "EOF",
        "summary": f"Scanned the line into {_plural(len(line_tokens), 'token')} "
                   f"ending in {'a NEWLINE' if has_newline else 'end of file'}.",
        "notes": notes,
    }


def _parser_stage(cmd: Command, written: list) -> dict:
    low, high, shape = ARITY[cmd.name]
    expected = f"{low}" if low == high else f"{low} to {high}"
    return {
        "rule": "statement := COMMAND argument* NEWLINE",
        "node": f"Command({cmd.name}) line={cmd.line}",
        "shape": shape,
        "arity": f"{cmd.name} takes {expected} argument(s); the line has {len(written)}.",
        "args": list(cmd.args),
        "summary": f"Matched the statement rule and built a Command({cmd.name}) AST node.",
    }


def _semantic_stage(cmd: Command, written: list) -> dict:
    """The checks the semantic analyser applied, with this line's actual values."""
    checks: list[dict] = []
    lim = sec.Limits

    def add(rule: str, detail: str) -> None:
        checks.append({"rule": rule, "detail": detail})

    def ints() -> None:
        add("Argument types", "every argument is a whole number")

    name = cmd.name
    if name in ("LOAD", "SAVE"):
        add("Position", "LOAD is the first command and appears exactly once"
            if name == "LOAD" else
            "SAVE is the last command; anything after it would never run")
        add("Filename", f'"{cmd.args[0]}" is a plain basename: no path separator, '
            f'no "..", no leading dot, extension in the allowed list '
            f'({", ".join(sorted(e.lstrip(".") for e in sec.ALLOWED_EXTENSIONS))})')
    elif name == "RESIZE":
        w, h = cmd.args
        ints()
        add("Range", f"1 ≤ {w} ≤ {lim.MAX_RESIZE_DIM} and 1 ≤ {h} ≤ {lim.MAX_RESIZE_DIM}")
        add("Pixel budget", f"{w} × {h} = {w * h:,} pixels, within the {lim.MAX_PIXELS:,} cap")
    elif name == "BLUR":
        r = cmd.args[0]
        ints()
        add("Range", f"1 ≤ {r} ≤ {lim.MAX_BLUR_RADIUS}")
        add("Kernel", f"Gaussian kernel will be {2 * r + 1} × {2 * r + 1} (always odd, "
            "as OpenCV requires)")
    elif name == "ROTATE":
        ints()
        angle = cmd.args[0]
        add("Range", "a multiple of 90 between -360 and 360")
        if written and written[0] != angle:
            add("Normalisation", f"{written[0]} is the same turn as {angle} (mod 360)")
    elif name == "EDGE":
        if not written:
            add("Defaults", f"no thresholds written, so low={cmd.args[0]} and "
                f"high={cmd.args[1]} were filled in")
        else:
            ints()
            add("Ordering", f"0 ≤ {cmd.args[0]} < {cmd.args[1]} ≤ 500")
    elif name == "VIGNETTE":
        s = cmd.args[0]
        ints()
        add("Range", f"{lim.MIN_VIGNETTE_STRENGTH} ≤ {s} ≤ {lim.MAX_VIGNETTE_STRENGTH}")
        add("Meaning", f"no darkening at the centre, {s}% at the corners")
    elif name == "GRAYSCALE":
        add("Arguments", "takes none; nothing to range-check")

    return {
        "checks": checks,
        "summary": f"Passed {_plural(len(checks), 'semantic check')}. Range limits come "
                   "from security.py, the single place they are defined.",
    }


def _cost_formula(op: str, args: list, mp: float) -> str:
    base = COST_PER_MP.get(op, 1.0)
    text = f"{base:g} units/MP × {max(mp, 0.01):.3f} MP"
    if op == "BLUR":
        text += f" × (1 + {args[0]}/5)"
    return text


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_trace(source: str, tokens: list[Token], ast: Program,
                unoptimized: IRProgram, optimized: IRProgram,
                line_events: dict[int, list[dict]], megapixels: float) -> list[dict]:
    """One entry per executable source line, in program order."""
    text_lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    by_line: dict[int, list[Token]] = {}
    newline_on: set[int] = set()
    for tok in tokens:
        if tok.type == TokenType.EOF:
            continue
        if tok.type == TokenType.NEWLINE:
            newline_on.add(tok.line)
        else:
            by_line.setdefault(tok.line, []).append(tok)

    commands = {c.line: c for c in ast.commands}
    u_rows = profile(unoptimized.instrs, megapixels)
    o_rows = profile(optimized.instrs, megapixels)
    opt_by_line = {i.line: (n, i) for n, i in enumerate(optimized.instrs)}

    trace: list[dict] = []

    for index, instr in enumerate(unoptimized.instrs):
        line = instr.line
        cmd = commands[line]
        source_line = text_lines[line - 1] if 0 < line <= len(text_lines) else ""
        line_tokens = by_line.get(line, [])
        written = [int(t.value) if t.type == TokenType.NUMBER else t.value
                   for t in line_tokens if t.type in (TokenType.NUMBER, TokenType.STRING)]

        mp_before, cost_before = u_rows[index]
        events = line_events.get(line, [])
        kinds = {e["effect"] for e in events}

        final = opt_by_line.get(line)
        if final is None:
            status = "removed"
        elif "rewritten" in kinds:
            status = "rewritten"
        elif "moved" in kinds:
            status = "moved"
        else:
            status = "kept"

        optimiser: dict = {
            "status": status,
            "events": events,
            "original_index": index,
            "cost_before": round(cost_before, 3),
            "megapixels_before": round(mp_before, 4),
        }

        if final is None:
            by = next((e["pass"] for e in reversed(events) if e["effect"] == "removed"),
                      "the optimiser")
            optimiser.update({
                "final_index": None,
                "final_instr": None,
                "cost_after": 0.0,
                "megapixels_after": None,
                "summary": f"Eliminated by {by}. It costs nothing at run time now.",
            })
        else:
            new_index, new_instr = final
            mp_after, cost_after = o_rows[new_index]
            # The explanation must come from the event that produced this
            # status, not simply the latest one: a line can be rewritten by one
            # pass and then merely shifted by another.
            by = next((e["pass"] for e in reversed(events) if e["effect"] == status), "")
            if status == "rewritten":
                summary = f"Rewritten as {_instr_repr(new_instr.op, new_instr.args)} by {by}."
                if abs(mp_after - mp_before) > 1e-9:
                    summary += (f" It also now runs on {mp_after:.3f} MP instead of "
                                f"{mp_before:.3f} MP.")
            elif status == "moved":
                summary = f"Moved from position {index} to {new_index} by {by}."
            elif abs(mp_after - mp_before) > 1e-9:
                summary = (f"Unchanged, but it now runs on {mp_after:.3f} MP instead of "
                           f"{mp_before:.3f} MP because a RESIZE was moved ahead of it.")
            else:
                summary = "No rewrite applied; emitted exactly as written."
            optimiser.update({
                "final_index": new_index,
                "final_instr": _instr_repr(new_instr.op, new_instr.args),
                "cost_after": round(cost_after, 3),
                "megapixels_after": round(mp_after, 4),
                "summary": summary,
            })

        trace.append({
            "line": line,
            "source": source_line.strip(),
            "command": cmd.name,
            "status": status,
            "lexer": _lexer_stage(line_tokens, line in newline_on, source_line),
            "parser": _parser_stage(cmd, written),
            "semantic": _semantic_stage(cmd, written),
            "ir": {
                "index": index,
                "instr": _instr_repr(instr.op, instr.args),
                "megapixels_in": round(mp_before, 4),
                "cost": round(cost_before, 3),
                "formula": _cost_formula(instr.op, instr.args, mp_before),
                "summary": f"Lowered to {_instr_repr(instr.op, instr.args)} at position "
                           f"{index}, with every argument explicit.",
            },
            "optimizer": optimiser,
            "execution": None,
        })

    return trace


_EXEC_SUMMARY = {
    "LOAD": "Read from the upload folder through resolve_inside, then the decoded "
            "size was checked again to catch a decompression bomb.",
    "SAVE": "Written under a freshly generated random filename; the requested name "
            "only contributed its extension.",
}


def attach_execution(trace: list[dict], steps: list[dict],
                     step_ms: dict[int, float] | None = None,
                     repeats: int | None = None) -> list[dict]:
    """Return a copy of the trace with the executor's measurements merged in.

    `step_ms` holds per-line medians from the benchmark's warm runs. They are
    preferred: a single cold run pays one-time setup costs (OpenCV's lazy
    initialisation, page faults) and can be several times slower than the
    steady state, which is exactly why the benchmark reports medians. Without
    them the single run is used and labelled as such.
    """
    result = copy.deepcopy(trace)
    by_line = {s["line"]: s for s in steps}
    for entry in result:
        step = by_line.get(entry["line"])
        if step is None:
            entry["execution"] = {
                "ran": False,
                "summary": "Never executed: the optimiser removed this instruction.",
            }
            continue
        height, width = (step["shape"] or [None, None])
        warm = step_ms.get(entry["line"]) if step_ms else None
        entry["execution"] = {
            "ran": True,
            "instr": _instr_repr(step["op"], step["args"]),
            "ms": warm if warm is not None else step["ms"],
            "basis": (f"median of {repeats} warm runs" if warm is not None
                      else "single run, includes one-time setup"),
            "width": width,
            "height": height,
            "summary": _EXEC_SUMMARY.get(
                step["op"],
                "Dispatched through the static handler table (no eval, no getattr) "
                "and timed."),
        }
    return result

"""Intermediate representation.

A flat list of Instr records. Lowering from the AST is almost one-to-one, which
raises the fair question of why have an IR at all. Two reasons:

  1. The AST carries source positions and argument sugar (EDGE with defaulted
     thresholds); the IR is fully explicit, so optimiser passes never have to
     ask "was this argument written or inferred?".
  2. Passes rewrite the IR freely. Keeping the AST immutable means the frontend
     can show the original tree next to the optimised IR, which is the whole
     point of the visualisation.

Each Instr carries a cost estimate in arbitrary units, used by the optimiser's
cost model. The units are calibrated against measured OpenCV timings on a
1000x1000 image; see docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .ast_nodes import Program

# Cost per megapixel, in arbitrary units. Relative magnitudes are what matter.
COST_PER_MP = {
    "LOAD": 8.0,
    "SAVE": 10.0,
    "RESIZE": 3.0,
    "GRAYSCALE": 1.0,
    "BLUR": 4.0,      # scaled further by radius
    "ROTATE": 2.5,
    "EDGE": 12.0,
    "VIGNETTE": 6.0,  # measured at roughly half of EDGE: one float mask, one multiply per channel
    "BRIGHTNESS": 1.2,
    "CONTRAST": 1.5,
    "SATURATION": 3.0,
    "FLIP": 0.8,
    "CROP": 0.5,
    "SHARPEN": 5.0,
    "THRESHOLD": 2.0,
    "MEDIAN_BLUR": 6.0,
}


@dataclass
class Instr:
    op: str
    args: list[Any] = field(default_factory=list)
    line: int = 0
    origin: str = "source"   # "source" or the name of the pass that created it

    def cost(self, megapixels: float) -> float:
        base = COST_PER_MP.get(self.op, 1.0) * max(megapixels, 0.01)
        if self.op == "BLUR":
            # Gaussian cost grows with kernel width, not area, because OpenCV
            # separates the kernel into two 1-D passes.
            base *= 1.0 + self.args[0] / 5.0
        return base

    def __repr__(self) -> str:
        arglist = ", ".join(str(a) for a in self.args)
        return f"{self.op}({arglist})"


def profile(instrs: list["Instr"], megapixels: float) -> list[tuple[float, float]]:
    """(megapixels entering, estimated cost) for each instruction.

    The raster size changes at every RESIZE, so the cost of an instruction
    depends on what ran before it. The optimiser's cost model and the
    per-line trace both read this one function, so they cannot disagree.
    """
    mp, rows = megapixels, []
    for instr in instrs:
        rows.append((mp, instr.cost(mp)))
        if instr.op == "RESIZE":
            mp = (instr.args[0] * instr.args[1]) / 1_000_000
        elif instr.op == "CROP":
            mp = (instr.args[2] * instr.args[3]) / 1_000_000
    return rows


@dataclass
class IRProgram:
    instrs: list[Instr] = field(default_factory=list)
    input_file: str = ""
    output_file: str = ""

    def clone(self) -> "IRProgram":
        return IRProgram(
            instrs=[Instr(i.op, list(i.args), i.line, i.origin) for i in self.instrs],
            input_file=self.input_file,
            output_file=self.output_file,
        )

    def listing(self) -> str:
        width = len(str(len(self.instrs)))
        rows = []
        for n, instr in enumerate(self.instrs):
            tag = "" if instr.origin == "source" else f"   ; {instr.origin}"
            rows.append(f"{n:>{width}}  {instr!r}{tag}")
        return "\n".join(rows)


def lower(program: Program) -> IRProgram:
    """AST -> IR."""
    ir = IRProgram()
    for cmd in program.commands:
        ir.instrs.append(Instr(op=cmd.name, args=list(cmd.args), line=cmd.line))
        if cmd.name == "LOAD":
            ir.input_file = cmd.args[0]
        elif cmd.name == "SAVE":
            ir.output_file = cmd.args[0]
    return ir

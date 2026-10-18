"""Abstract syntax tree.

The DSL is a flat command sequence, so the AST is shallow by design: a Program
holding an ordered list of Command nodes. There is no expression tree because
there are no expressions, and no block nodes because there is no control flow.
That absence is deliberate — see docs/SECURITY.md on why the language has no
loops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    line: int = 0


@dataclass
class Command(Node):
    name: str = ""
    args: list[Any] = field(default_factory=list)

    def __repr__(self) -> str:
        arglist = " ".join(repr(a) for a in self.args)
        return f"{self.name} {arglist}".strip()


@dataclass
class Program(Node):
    commands: list[Command] = field(default_factory=list)

    def pretty(self) -> str:
        """Indented tree dump, shown in the frontend's AST panel."""
        lines = ["Program"]
        for cmd in self.commands:
            lines.append(f"  Command({cmd.name}) line={cmd.line}")
            for arg in cmd.args:
                kind = type(arg).__name__
                lines.append(f"    Arg[{kind}]: {arg!r}")
        return "\n".join(lines)

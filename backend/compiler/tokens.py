"""Token definitions for the image DSL."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    COMMAND = auto()
    NUMBER = auto()
    STRING = auto()
    NEWLINE = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    line: int
    column: int

    def __repr__(self) -> str:
        return f"{self.type.name}({self.value!r})@{self.line}:{self.column}"

"""Compiler diagnostics.

Every error carries a stage, a human message and, where known, a line and
column. The frontend renders these in the error panel, so the message must be
about the *user's program*, never about the server.
"""

from __future__ import annotations


class CompilerError(Exception):
    stage = "compiler"

    def __init__(self, message: str, line: int | None = None, column: int | None = None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "message": self.message,
            "line": self.line,
            "column": self.column,
        }

    def __str__(self) -> str:
        where = f" (line {self.line}" + (f", col {self.column}" if self.column else "") + ")"
        return self.message + (where if self.line else "")


class LexError(CompilerError):
    stage = "lexer"


class ParseError(CompilerError):
    stage = "parser"


class SemanticError(CompilerError):
    stage = "semantic"


class ExecutionError(CompilerError):
    stage = "execution"

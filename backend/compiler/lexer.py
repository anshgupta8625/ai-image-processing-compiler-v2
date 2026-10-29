"""Hand-written lexer.

A regex-per-token-type scanner rather than a generated one, because the DSL has
sixteen keywords and three literal forms; a generator would be more machinery than
the grammar deserves, and hand-rolling keeps the error positions exact.

The lexer recognises a closed alphabet. Any character outside it is a LexError,
which is the first place an injection attempt dies even if it slipped past the
pre-scan in security.py.
"""

from __future__ import annotations

import re

from .errors import LexError
from .tokens import Token, TokenType

# Order matters: STRING before NUMBER so a quoted "12" is not read as a number.
_PATTERNS = [
    ("WHITESPACE", re.compile(r"[ \t]+")),
    ("COMMENT", re.compile(r"#[^\n]*")),
    ("STRING", re.compile(r'"([^"\n\\]{0,128})"')),
    ("NUMBER", re.compile(r"-?\d+(?:\.\d+)?")),
    ("WORD", re.compile(r"[A-Za-z_][A-Za-z_0-9]*")),
]


class Lexer:
    def __init__(self, source: str):
        self.source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.pos = 0
        self.line = 1
        self.column = 1

    def _advance(self, text: str) -> None:
        self.pos += len(text)
        self.column += len(text)

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        src = self.source

        while self.pos < len(src):
            char = src[self.pos]

            if char == "\n":
                tokens.append(Token(TokenType.NEWLINE, "\\n", self.line, self.column))
                self.pos += 1
                self.line += 1
                self.column = 1
                continue

            for name, pattern in _PATTERNS:
                match = pattern.match(src, self.pos)
                if not match:
                    continue

                text = match.group(0)
                start_col = self.column

                if name in ("WHITESPACE", "COMMENT"):
                    self._advance(text)
                    break
                if name == "STRING":
                    tokens.append(Token(TokenType.STRING, match.group(1), self.line, start_col))
                    self._advance(text)
                    break
                if name == "NUMBER":
                    tokens.append(Token(TokenType.NUMBER, text, self.line, start_col))
                    self._advance(text)
                    break
                # WORD: only commands are legal identifiers. There are no
                # variables in this language, so an unknown word is an error
                # here rather than a token the parser has to reject later.
                tokens.append(Token(TokenType.COMMAND, text.upper(), self.line, start_col))
                self._advance(text)
                break
            else:
                raise LexError(
                    f"Unexpected character {char!r}.", self.line, self.column
                )

        tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return tokens


def tokenize(source: str) -> list[Token]:
    return Lexer(source).tokenize()

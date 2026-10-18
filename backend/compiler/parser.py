"""Recursive-descent parser.

The grammar is regular, so this is really a loop over statements; "recursive
descent" is generous. Kept in that style anyway because it makes adding a
nested construct later a local change rather than a rewrite.

    program   := statement*
    statement := COMMAND argument* NEWLINE
    argument  := NUMBER | STRING

Arity is checked here, not in the semantic analyser, because arity is a
syntactic property of the command form and catching it early gives a better
error position.
"""

from __future__ import annotations

from .ast_nodes import Command, Program
from .errors import ParseError
from .tokens import Token, TokenType

# command -> (min_args, max_args, description of the expected shape)
ARITY = {
    "LOAD": (1, 1, 'LOAD "filename"'),
    "SAVE": (1, 1, 'SAVE "filename"'),
    "RESIZE": (2, 2, "RESIZE width height"),
    "GRAYSCALE": (0, 0, "GRAYSCALE"),
    "BLUR": (1, 1, "BLUR radius"),
    "ROTATE": (1, 1, "ROTATE angle"),
    "EDGE": (0, 2, "EDGE  or  EDGE low high"),
    "VIGNETTE": (1, 1, "VIGNETTE strength"),
}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    def _eat(self) -> Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def _skip_newlines(self) -> None:
        while self.current.type == TokenType.NEWLINE:
            self._eat()

    def parse(self) -> Program:
        program = Program(line=1)
        self._skip_newlines()

        while self.current.type != TokenType.EOF:
            program.commands.append(self._statement())
            self._skip_newlines()

        if not program.commands:
            raise ParseError("The program contains no commands.", 1)
        return program

    def _statement(self) -> Command:
        token = self.current
        if token.type != TokenType.COMMAND:
            raise ParseError(
                f"Expected a command, found {token.value!r}.", token.line, token.column
            )
        self._eat()
        name = token.value

        if name not in ARITY:
            raise ParseError(
                f"Unknown command {name!r}. Allowed: " + ", ".join(sorted(ARITY)) + ".",
                token.line,
                token.column,
            )

        args: list = []
        while self.current.type in (TokenType.NUMBER, TokenType.STRING):
            arg = self._eat()
            args.append(int(arg.value) if arg.type == TokenType.NUMBER else arg.value)

        if self.current.type not in (TokenType.NEWLINE, TokenType.EOF):
            bad = self.current
            raise ParseError(
                f"Unexpected {bad.value!r} after {name}.", bad.line, bad.column
            )

        low, high, shape = ARITY[name]
        if not low <= len(args) <= high:
            expected = f"{low}" if low == high else f"{low} to {high}"
            raise ParseError(
                f"{name} expects {expected} argument(s), got {len(args)}. Use: {shape}",
                token.line,
                token.column,
            )

        return Command(line=token.line, name=name, args=args)


def parse(tokens: list[Token]) -> Program:
    return Parser(tokens).parse()

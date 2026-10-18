import pytest

from compiler.errors import LexError
from compiler.lexer import tokenize
from compiler.tokens import TokenType


def kinds(source):
    return [t.type for t in tokenize(source) if t.type is not TokenType.EOF]


def test_commands_are_case_insensitive():
    assert tokenize("blur 3")[0].value == "BLUR"


def test_string_literal_keeps_inner_text_only():
    token = tokenize('LOAD "cat.png"')[1]
    assert token.type is TokenType.STRING
    assert token.value == "cat.png"


def test_quoted_number_is_a_string_not_a_number():
    assert tokenize('SAVE "12"')[1].type is TokenType.STRING


def test_comments_are_discarded():
    assert kinds("GRAYSCALE # make it grey") == [TokenType.COMMAND]


def test_negative_numbers_lex_as_one_token():
    tokens = tokenize("ROTATE -90")
    assert tokens[1].value == "-90"


def test_positions_are_tracked_across_lines():
    token = tokenize("GRAYSCALE\nBLUR 5")[2]
    assert (token.line, token.column) == (2, 1)


@pytest.mark.parametrize("source", ["BLUR @3", "LOAD $file", "EDGE %"])
def test_illegal_characters_rejected(source):
    with pytest.raises(LexError):
        tokenize(source)

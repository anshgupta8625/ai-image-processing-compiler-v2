import pytest

from compiler.errors import ParseError, SemanticError
from compiler.lexer import tokenize
from compiler.parser import parse
from compiler.semantic import analyse


def build(source):
    return parse(tokenize(source))


VALID = 'LOAD "a.png"\nRESIZE 800 600\nGRAYSCALE\nBLUR 3\nSAVE "b.png"'


def test_valid_program_parses():
    program = build(VALID)
    assert [c.name for c in program.commands] == [
        "LOAD", "RESIZE", "GRAYSCALE", "BLUR", "SAVE"
    ]


def test_blank_lines_are_ignored():
    assert len(build('\n\nLOAD "a.png"\n\n\nSAVE "b.png"\n').commands) == 2


@pytest.mark.parametrize("source", [
    "RESIZE 800",            # too few
    "RESIZE 800 600 400",    # too many
    "GRAYSCALE 5",           # takes none
    "BLUR",                  # needs one
])
def test_arity_errors(source):
    with pytest.raises(ParseError, match="expects"):
        build(source)


def test_unknown_command_rejected_by_parser():
    with pytest.raises(ParseError, match="Unknown command"):
        build("SHARPEN 3")


def test_errors_carry_a_line_number():
    with pytest.raises(ParseError) as e:
        build('LOAD "a.png"\nRESIZE 800')
    assert e.value.line == 2


# --- semantic rules ---

def test_program_must_start_with_load():
    with pytest.raises(SemanticError, match="LOAD must be the first"):
        analyse(build('GRAYSCALE\nLOAD "a.png"\nSAVE "b.png"'))


def test_only_one_load_allowed():
    with pytest.raises(SemanticError, match="Only one LOAD"):
        analyse(build('LOAD "a.png"\nLOAD "b.png"\nSAVE "c.png"'))


def test_save_required():
    with pytest.raises(SemanticError, match="end with a SAVE"):
        analyse(build('LOAD "a.png"\nGRAYSCALE'))


def test_operations_after_save_rejected():
    with pytest.raises(SemanticError, match="no effect"):
        analyse(build('LOAD "a.png"\nSAVE "b.png"\nGRAYSCALE'))


def test_edge_thresholds_default_when_omitted():
    program = build('LOAD "a.png"\nEDGE\nSAVE "b.png"')
    analyse(program)
    assert program.commands[1].args == [100, 200]


def test_edge_thresholds_must_be_ordered():
    with pytest.raises(SemanticError, match="low < high"):
        analyse(build('LOAD "a.png"\nEDGE 200 100\nSAVE "b.png"'))


def test_semantic_rejects_unsafe_filename():
    with pytest.raises(SemanticError, match="Invalid file path"):
        analyse(build('LOAD "../../etc/passwd.png"\nSAVE "b.png"'))


def test_blur_limit_enforced_in_semantics():
    with pytest.raises(SemanticError, match="Blur radius"):
        analyse(build('LOAD "a.png"\nBLUR 999\nSAVE "b.png"'))

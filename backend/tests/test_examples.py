"""The shipped example programs must keep compiling, and the unsafe one must not."""

from pathlib import Path

import pytest

import security as sec
from compiler.errors import CompilerError
from compiler.pipeline import compile_program

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
SAFE = sorted(p for p in EXAMPLES.glob("*.dsl") if p.name != "unsafe.dsl")


def test_examples_are_found():
    assert len(SAFE) >= 4


@pytest.mark.parametrize("path", SAFE, ids=lambda p: p.name)
def test_safe_examples_compile(path):
    result = compile_program(path.read_text(), megapixels=12.0)
    assert result["trace"] and result["optimized_ir"]


def test_unsafe_example_is_rejected():
    with pytest.raises((sec.SecurityError, CompilerError)):
        compile_program((EXAMPLES / "unsafe.dsl").read_text(), megapixels=12.0)


def test_vignette_example_hoists_the_resize():
    result = compile_program((EXAMPLES / "vignette.dsl").read_text(), megapixels=12.0)
    ops = [line.split()[1].split("(")[0] for line in result["optimized_ir"].splitlines()]
    assert ops == ["LOAD", "RESIZE", "VIGNETTE", "SAVE"]

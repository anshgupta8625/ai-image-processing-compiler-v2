"""Optimiser tests.

Two things are asserted throughout: the rewrite happened, and the result is
still a legal program. A pass that produces a cheaper but wrong pipeline is
worse than no pass at all.
"""

import pytest

from compiler.ir import lower
from compiler.lexer import tokenize
from compiler.optimizer import optimize
from compiler.parser import parse
from compiler.semantic import analyse


def ir_for(source):
    program = parse(tokenize(source))
    analyse(program)
    return lower(program)


def ops(ir):
    return [i.op for i in ir.instrs]


def run(source, megapixels=12.0):
    return optimize(ir_for(source), megapixels)


def test_opposite_rotations_cancel():
    opt, log, _ = run('LOAD "a.png"\nROTATE 90\nROTATE 270\nSAVE "b.png"')
    assert ops(opt) == ["LOAD", "SAVE"]
    assert any(r.pass_name == "constant-folding" for r in log)


def test_rotations_merge_into_one():
    opt, _, _ = run('LOAD "a.png"\nROTATE 90\nROTATE 90\nSAVE "b.png"')
    rotations = [i for i in opt.instrs if i.op == "ROTATE"]
    assert len(rotations) == 1 and rotations[0].args == [180]


def test_repeated_grayscale_collapsed():
    opt, _, _ = run('LOAD "a.png"\nGRAYSCALE\nGRAYSCALE\nGRAYSCALE\nSAVE "b.png"')
    assert ops(opt).count("GRAYSCALE") == 1


def test_shadowed_resize_dropped():
    opt, _, _ = run('LOAD "a.png"\nRESIZE 2000 2000\nRESIZE 400 400\nSAVE "b.png"')
    resizes = [i for i in opt.instrs if i.op == "RESIZE"]
    assert len(resizes) == 1 and resizes[0].args == [400, 400]


def test_adjacent_blurs_fuse_in_quadrature():
    opt, _, _ = run('LOAD "a.png"\nBLUR 3\nBLUR 4\nSAVE "b.png"')
    blurs = [i for i in opt.instrs if i.op == "BLUR"]
    assert len(blurs) == 1 and blurs[0].args == [5]   # hypot(3, 4)


def test_downscale_is_hoisted_above_expensive_filters():
    opt, log, stats = run('LOAD "big.png"\nBLUR 5\nEDGE\nRESIZE 200 200\nSAVE "b.png"')
    order = ops(opt)
    assert order.index("RESIZE") < order.index("BLUR")
    assert stats["estimated_saving_percent"] > 50
    assert any(r.pass_name == "strength-reduction" for r in log)


def test_upscale_is_not_hoisted():
    """Resizing up then filtering is a different image; the pass must refuse."""
    source = 'LOAD "small.png"\nBLUR 5\nRESIZE 4000 3000\nSAVE "b.png"'
    opt, _, _ = optimize(ir_for(source), megapixels=0.1)
    order = ops(opt)
    assert order.index("BLUR") < order.index("RESIZE")


def test_optimizer_is_idempotent():
    first, _, _ = run('LOAD "a.png"\nBLUR 3\nBLUR 4\nRESIZE 100 100\nSAVE "b.png"')
    second, log, _ = optimize(first, 12.0)
    assert ops(first) == ops(second)
    assert log == []


def test_already_optimal_program_is_left_alone():
    source = 'LOAD "a.png"\nRESIZE 400 400\nGRAYSCALE\nSAVE "b.png"'
    opt, log, stats = run(source)
    assert ops(opt) == ["LOAD", "RESIZE", "GRAYSCALE", "SAVE"]
    assert stats["estimated_saving_percent"] == 0.0


def test_cost_model_tracks_shrinking_raster():
    """Cost must fall after a downscale, or strength reduction has no signal."""
    from compiler.optimizer import Optimizer

    o = Optimizer(ir_for('LOAD "a.png"\nRESIZE 100 100\nBLUR 5\nSAVE "b.png"'), 12.0)
    sizes = o._sizes(o.ir.instrs)
    assert sizes[0] == 12.0 and sizes[2] == pytest.approx(0.01)

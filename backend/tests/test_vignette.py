"""VIGNETTE through every stage: security, front end, executor, optimiser."""

import numpy as np
import pytest

import security as sec
from compiler.errors import ParseError, SemanticError
from compiler.executor import Executor, _op_vignette
from compiler.ir import lower
from compiler.lexer import tokenize
from compiler.optimizer import optimize
from compiler.parser import parse
from compiler.semantic import analyse


def program(source):
    ast = parse(tokenize(source))
    analyse(ast)
    return ast


def wrap(body):
    return f'LOAD "a.png"\n{body}\nSAVE "b.png"'


# --- security ---------------------------------------------------------------

def test_vignette_is_whitelisted():
    assert "VIGNETTE" in sec.ALLOWED_COMMANDS
    assert sec.validate_command("vignette") == "VIGNETTE"


@pytest.mark.parametrize("value", [1, 50, 100])
def test_strength_inside_range_accepted(value):
    assert sec.validate_vignette(value) == value


@pytest.mark.parametrize("value", [0, -5, 101, 10_000])
def test_strength_outside_range_rejected(value):
    with pytest.raises(sec.SecurityError) as e:
        sec.validate_vignette(value)
    assert e.value.code == "INVALID_VIGNETTE"


# --- front end --------------------------------------------------------------

def test_lowercase_keyword_parses():
    cmd = program(wrap("vignette 40")).commands[1]
    assert (cmd.name, cmd.args) == ("VIGNETTE", [40])


def test_missing_argument_is_a_parse_error():
    with pytest.raises(ParseError):
        parse(tokenize(wrap("VIGNETTE")))


def test_two_arguments_is_a_parse_error():
    with pytest.raises(ParseError):
        parse(tokenize(wrap("VIGNETTE 10 20")))


@pytest.mark.parametrize("value", [0, 101])
def test_out_of_range_is_a_semantic_error(value):
    with pytest.raises(SemanticError) as e:
        program(wrap(f"VIGNETTE {value}"))
    assert "between 1 and 100" in e.value.message


def test_string_argument_is_rejected():
    with pytest.raises(SemanticError):
        program(wrap('VIGNETTE "strong"'))


# --- executor ---------------------------------------------------------------

def flat(h=200, w=300, value=200, channels=3):
    shape = (h, w, channels) if channels else (h, w)
    return np.full(shape, value, np.uint8)


def test_centre_is_untouched_and_corners_go_dark():
    out = _op_vignette(flat(201, 301), 100)
    assert (out[100, 150] == 200).all()
    assert out[0, 0].max() == 0 and out[-1, -1].max() == 0


def test_corner_brightness_follows_strength():
    out = _op_vignette(flat(), 50)
    # factor at a corner is 1 - strength/100
    assert abs(int(out[0, 0, 0]) - 100) <= 1


def test_stronger_strength_is_never_brighter():
    weak, strong = _op_vignette(flat(), 20), _op_vignette(flat(), 80)
    assert (strong <= weak).all()


def test_falloff_is_symmetric_about_the_centre():
    out = _op_vignette(flat(101, 101), 70)[:, :, 0].astype(int)
    assert np.abs(out - out[::-1, :]).max() <= 1
    assert np.abs(out - out[:, ::-1]).max() <= 1


def test_shape_and_dtype_preserved():
    out = _op_vignette(flat(37, 91), 60)
    assert out.shape == (37, 91, 3) and out.dtype == np.uint8


def test_single_channel_images_are_supported():
    out = _op_vignette(flat(40, 60, channels=0), 60)
    assert out.shape == (40, 60) and out[0, 0] < out[20, 30]


@pytest.mark.parametrize("shape", [(1, 1, 3), (1, 9, 3), (9, 1, 3)])
def test_degenerate_sizes_do_not_divide_by_zero(shape):
    out = _op_vignette(np.full(shape, 99, np.uint8), 80)
    assert out.shape == shape


def test_input_image_is_not_modified_in_place():
    image = flat()
    before = image.copy()
    _op_vignette(image, 90)
    assert (image == before).all()


# --- optimiser ---------------------------------------------------------------

def test_downscale_is_hoisted_above_vignette():
    ir = lower(program(wrap("VIGNETTE 60\nRESIZE 100 100")))
    opt, log, stats = optimize(ir, megapixels=12.0)
    assert [i.op for i in opt.instrs] == ["LOAD", "RESIZE", "VIGNETTE", "SAVE"]
    assert any(r.pass_name == "strength-reduction" for r in log)
    # LOAD and the RESIZE itself still touch every pixel, so the saving is the
    # vignette's share only; what matters is that the cost strictly drops.
    assert stats["estimated_cost_after"] < stats["estimated_cost_before"]


def test_upscale_is_not_hoisted_above_vignette():
    ir = lower(program(wrap("VIGNETTE 60\nRESIZE 4000 4000")))
    opt, _, _ = optimize(ir, megapixels=1.0)
    assert [i.op for i in opt.instrs] == ["LOAD", "VIGNETTE", "RESIZE", "SAVE"]


def test_hoisting_preserves_the_picture(tmp_path):
    """The reorder is only legal if the output is (nearly) the same image."""
    import cv2

    # A smooth image, so interpolation differences between the two orders stay tiny.
    ys, xs = np.mgrid[0:600, 0:800]
    image = np.stack([(xs * 255 // 800), (ys * 255 // 600), ((xs + ys) * 255 // 1400)],
                     axis=-1).astype(np.uint8)
    uploads, outputs = tmp_path / "up", tmp_path / "out"
    uploads.mkdir(); outputs.mkdir()
    cv2.imwrite(str(uploads / "in.png"), image)

    source = 'LOAD "in.png"\nVIGNETTE 70\nRESIZE 160 120\nSAVE "o.png"'
    unoptimised = lower(program(source))
    optimised, _, _ = optimize(unoptimised, megapixels=0.48)
    assert [i.op for i in optimised.instrs][1] == "RESIZE"   # it really was reordered

    executor = Executor(uploads, outputs)
    outs = []
    for ir in (unoptimised, optimised):
        name = executor.run(ir, "in.png")["output_file"]
        outs.append(cv2.imread(str(outputs / name)).astype(int))
    assert outs[0].shape == outs[1].shape == (120, 160, 3)
    assert np.abs(outs[0] - outs[1]).mean() < 2.0

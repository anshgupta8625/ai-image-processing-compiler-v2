"""Coverage for the eight additional image DSL operations."""

import cv2
import numpy as np
import pytest

import security as sec
from compiler.errors import ExecutionError, ParseError, SemanticError
from compiler.executor import (
    _op_brightness, _op_contrast, _op_crop, _op_flip, _op_median_blur,
    _op_saturation, _op_sharpen, _op_threshold,
)
from compiler.lexer import tokenize
from compiler.parser import parse
from compiler.semantic import analyse


def build(source):
    return parse(tokenize(source))


def test_all_new_commands_parse_and_semantically_validate():
    source = '''LOAD "input.png"
BRIGHTNESS -20
CONTRAST 1.5
SATURATION 1.4
FLIP HORIZONTAL
CROP 0 0 100 80
SHARPEN 1.2
THRESHOLD 128
MEDIAN_BLUR 5
SAVE "output.png"'''
    program = build(source)
    analyse(program)
    assert [c.name for c in program.commands[1:-1]] == [
        "BRIGHTNESS", "CONTRAST", "SATURATION", "FLIP", "CROP",
        "SHARPEN", "THRESHOLD", "MEDIAN_BLUR",
    ]
    assert program.commands[2].args == [1.5]
    assert program.commands[4].args == ["HORIZONTAL"]


@pytest.mark.parametrize("source", [
    'LOAD "i.png"\nBRIGHTNESS 101\nSAVE "o.png"',
    'LOAD "i.png"\nCONTRAST 4.0\nSAVE "o.png"',
    'LOAD "i.png"\nSATURATION -0.1\nSAVE "o.png"',
    'LOAD "i.png"\nFLIP DIAGONAL\nSAVE "o.png"',
    'LOAD "i.png"\nCROP -1 0 10 10\nSAVE "o.png"',
    'LOAD "i.png"\nSHARPEN 4.0\nSAVE "o.png"',
    'LOAD "i.png"\nTHRESHOLD 256\nSAVE "o.png"',
    'LOAD "i.png"\nMEDIAN_BLUR 4\nSAVE "o.png"',
])
def test_invalid_new_command_arguments_rejected(source):
    with pytest.raises((SemanticError, ParseError)):
        analyse(build(source))


def test_flip_requires_a_supported_direction():
    with pytest.raises(ParseError, match="expects"):
        build('LOAD "i.png"\nFLIP\nSAVE "o.png"')


def test_new_commands_are_in_security_whitelist():
    for name in ("BRIGHTNESS", "CONTRAST", "SATURATION", "FLIP", "CROP",
                 "SHARPEN", "THRESHOLD", "MEDIAN_BLUR"):
        assert sec.validate_command(name) == name


def test_brightness_can_darken_and_brighten_without_reflecting_values():
    image = np.array([[0, 10, 250]], dtype=np.uint8)
    assert _op_brightness(image, -20).tolist() == [[0, 0, 230]]
    assert _op_brightness(image, 20).tolist() == [[20, 30, 255]]


def test_contrast_factor_one_is_identity_approximately():
    image = np.arange(256, dtype=np.uint8).reshape(16, 16)
    out = _op_contrast(image, 1.0)
    assert np.abs(out.astype(int) - image.astype(int)).max() <= 1


def test_saturation_zero_removes_color():
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    image[:] = (20, 80, 200)
    out = _op_saturation(image, 0.0)
    assert np.all(out[:, :, 0] == out[:, :, 1])
    assert np.all(out[:, :, 1] == out[:, :, 2])


def test_flip_horizontal_and_vertical():
    image = np.array([[1, 2], [3, 4]], dtype=np.uint8)
    assert _op_flip(image, "HORIZONTAL").tolist() == [[2, 1], [4, 3]]
    assert _op_flip(image, "VERTICAL").tolist() == [[3, 4], [1, 2]]


def test_crop_returns_copy_and_checks_bounds():
    image = np.arange(100, dtype=np.uint8).reshape(10, 10)
    crop = _op_crop(image, 2, 3, 4, 5)
    assert crop.shape == (5, 4)
    crop[0, 0] = 255
    assert image[3, 2] != 255
    with pytest.raises(ExecutionError, match="outside the current image"):
        _op_crop(image, 8, 8, 4, 4)


def test_sharpen_strength_zero_returns_same_pixels():
    image = np.arange(100, dtype=np.uint8).reshape(10, 10)
    assert np.array_equal(_op_sharpen(image, 0), image)


def test_threshold_produces_binary_grayscale():
    image = np.array([[10, 128, 240]], dtype=np.uint8)
    out = _op_threshold(image, 128)
    assert out.tolist() == [[0, 0, 255]]
    assert set(np.unique(out)).issubset({0, 255})


def test_median_blur_keeps_shape():
    image = np.zeros((9, 9), dtype=np.uint8)
    image[4, 4] = 255
    out = _op_median_blur(image, 3)
    assert out.shape == image.shape


def test_all_new_commands_execute_as_one_pipeline(tmp_path):
    from compiler.executor import Executor
    from compiler.ir import lower
    from compiler.optimizer import optimize

    uploads = tmp_path / "uploads"
    outputs = tmp_path / "outputs"
    uploads.mkdir()
    outputs.mkdir()
    image = np.zeros((80, 100, 3), dtype=np.uint8)
    image[:, :50] = (20, 80, 200)
    image[:, 50:] = (220, 180, 40)
    assert cv2.imwrite(str(uploads / "input.png"), image)

    source = 'LOAD "input.png"\nBRIGHTNESS 10\nCONTRAST 1.2\nSATURATION 1.1\nFLIP HORIZONTAL\nCROP 0 0 80 60\nSHARPEN 0.5\nTHRESHOLD 128\nMEDIAN_BLUR 3\nSAVE "output.png"'
    program = build(source)
    analyse(program)
    unoptimized = lower(program)
    optimized, _, _ = optimize(unoptimized, megapixels=0.008)
    result = Executor(uploads, outputs).run(optimized, "input.png")
    saved = cv2.imread(str(outputs / result["output_file"]), cv2.IMREAD_UNCHANGED)
    assert saved is not None
    assert saved.shape == (60, 80)
    assert set(np.unique(saved)).issubset({0, 255})

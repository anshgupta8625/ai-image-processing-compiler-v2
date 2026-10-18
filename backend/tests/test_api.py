"""End-to-end tests against the HTTP API, including a real image round trip."""

import io

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app, raise_server_exceptions=False)


def make_png(width=600, height=400) -> bytes:
    image = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


@pytest.fixture
def uploaded():
    response = client.post(
        "/api/upload",
        files={"file": ("sample.png", io.BytesIO(make_png()), "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_limits_endpoint_exposes_the_whitelist():
    data = client.get("/api/limits").json()
    assert set(data["commands"]) == {
        "LOAD", "SAVE", "RESIZE", "GRAYSCALE", "BLUR", "ROTATE", "EDGE", "VIGNETTE"
    }


def test_upload_returns_dimensions_and_opaque_id(uploaded):
    assert (uploaded["width"], uploaded["height"]) == (600, 400)
    assert "sample" not in uploaded["image_id"]
    assert uploaded["security"]["passed"] is True


def test_upload_rejects_non_image():
    response = client.post(
        "/api/upload",
        files={"file": ("evil.png", io.BytesIO(b"<?php system($_GET['c']); ?>"),
                        "image/png")},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "CONTENT_MISMATCH"


def test_compile_returns_every_stage():
    response = client.post("/api/compile", json={
        "source": 'LOAD "a.png"\nRESIZE 200 200\nGRAYSCALE\nSAVE "b.png"',
        "width": 600, "height": 400,
    })
    body = response.json()
    assert response.status_code == 200
    for key in ("tokens", "ast", "ir", "optimized_ir", "optimizer_stats", "security"):
        assert key in body
    assert "Program" in body["ast"]


def test_compile_reports_the_failing_line():
    response = client.post("/api/compile", json={"source": 'LOAD "a.png"\nBLUR'})
    assert response.status_code == 400
    assert response.json()["line"] == 2


def test_run_produces_an_image_and_a_benchmark(uploaded):
    response = client.post("/api/run", json={
        "source": 'LOAD "in.png"\nBLUR 4\nEDGE\nRESIZE 150 150\nSAVE "out.png"',
        "image_id": uploaded["image_id"],
        "width": uploaded["width"], "height": uploaded["height"],
    })
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["benchmark"]["optimized_ms"] > 0
    assert body["benchmark"]["speedup"] is not None
    assert body["output_url"].startswith("/api/image/")

    image = client.get(body["output_url"])
    assert image.status_code == 200
    decoded = cv2.imdecode(np.frombuffer(image.content, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (150, 150)


def test_optimized_and_unoptimized_agree_on_output_shape(uploaded):
    """The optimiser must not change what the program means."""
    body = client.post("/api/run", json={
        "source": 'LOAD "in.png"\nROTATE 90\nROTATE 270\nRESIZE 120 90\nSAVE "o.png"',
        "image_id": uploaded["image_id"],
        "width": uploaded["width"], "height": uploaded["height"],
    }).json()
    final = body["execution"]["steps"][-2]["shape"]
    assert final == [90, 120]


def test_run_rejects_traversal_in_image_id(uploaded):
    response = client.post("/api/run", json={
        "source": 'LOAD "a.png"\nSAVE "b.png"',
        "image_id": "../../etc/passwd",
    })
    assert response.status_code == 400
    assert response.json()["message"] == "Invalid file path."


def test_injection_blocked_before_any_work(uploaded):
    response = client.post("/api/run", json={
        "source": 'LOAD "a.png"\nos.system("rm -rf /")\nSAVE "b.png"',
        "image_id": uploaded["image_id"],
    })
    assert response.status_code == 400
    assert response.json()["code"] == "INJECTION_BLOCKED"


def test_error_response_never_leaks_paths():
    response = client.post("/api/run", json={
        "source": 'LOAD "../../secret.png"\nSAVE "b.png"',
        "image_id": "nonexistent.png",
    })
    assert "/" not in response.json().get("message", "")


def test_benchmark_reports_spread_and_significance(uploaded):
    """A speed-up smaller than the run-to-run noise must not be claimed."""
    body = client.post("/api/run", json={
        "source": 'LOAD "in.png"\nBLUR 5\nEDGE\nRESIZE 100 100\nSAVE "o.png"',
        "image_id": uploaded["image_id"],
        "width": uploaded["width"], "height": uploaded["height"],
    }).json()

    mark = body["benchmark"]
    assert mark["repeats"] == 5
    low, high = mark["optimized_range_ms"]
    assert low <= mark["optimized_ms"] <= high
    assert isinstance(mark["significant"], bool)
    # This program does 30x less work after hoisting; it should clear the noise.
    assert mark["significant"] is True


def test_benchmark_repeats_leave_only_one_output(uploaded):
    import config

    before = set(config.OUTPUT_DIR.iterdir())
    body = client.post("/api/run", json={
        "source": 'LOAD "in.png"\nGRAYSCALE\nSAVE "o.png"',
        "image_id": uploaded["image_id"],
        "width": uploaded["width"], "height": uploaded["height"],
    }).json()
    after = set(config.OUTPUT_DIR.iterdir())

    assert len(after - before) == 1
    assert body["output_file"] in {p.name for p in after - before}


# --- per-line trace -----------------------------------------------------------

def test_compile_returns_a_trace_without_execution_data():
    body = client.post("/api/compile", json={
        "source": 'LOAD "a.png"\nBLUR 3\nRESIZE 100 100\nSAVE "b.png"',
        "width": 4000, "height": 3000,
    }).json()
    assert [t["command"] for t in body["trace"]] == ["LOAD", "BLUR", "RESIZE", "SAVE"]
    assert all(t["execution"] is None for t in body["trace"])


def test_run_trace_carries_measured_time_and_size(uploaded):
    body = client.post("/api/run", json={
        "source": 'LOAD "in.png"\nROTATE 90\nROTATE 270\nVIGNETTE 50\nRESIZE 150 100\nSAVE "o.png"',
        "image_id": uploaded["image_id"],
        "width": uploaded["width"], "height": uploaded["height"],
    }).json()
    trace = {t["line"]: t for t in body["trace"]}

    # the cancelled rotations never ran
    assert trace[2]["execution"]["ran"] is False and trace[3]["execution"]["ran"] is False
    resize = trace[5]["execution"]
    assert resize["ran"] and (resize["width"], resize["height"]) == (150, 100)
    assert all(t["execution"]["ms"] >= 0 for t in trace.values() if t["execution"]["ran"])


# --- vignette end to end ----------------------------------------------------------

def test_vignette_run_darkens_the_corners_and_keeps_the_centre(uploaded):
    flat = np.full((400, 600, 3), 180, np.uint8)
    ok, buf = cv2.imencode(".png", flat)
    up = client.post("/api/upload", files={
        "file": ("flat.png", io.BytesIO(buf.tobytes()), "image/png")}).json()

    body = client.post("/api/run", json={
        "source": 'LOAD "in.png"\nVIGNETTE 80\nSAVE "o.png"',
        "image_id": up["image_id"], "width": 600, "height": 400, "benchmark": False,
    }).json()
    out = cv2.imdecode(np.frombuffer(client.get(body["output_url"]).content, np.uint8),
                       cv2.IMREAD_COLOR)
    assert out.shape == (400, 600, 3)
    assert int(out[200, 300, 0]) >= 178              # centre barely touched
    assert int(out[0, 0, 0]) < 60                    # corner clearly darker


# --- rejections carry the gate that fired -----------------------------------------------

@pytest.mark.parametrize("source, gate", [
    ('LOAD "../../etc/passwd"\nSAVE "b.png"',          "Path validation"),
    ('LOAD "a.png"\nBLUR 999\nSAVE "b.png"',           "Resource limits"),
    ('LOAD "a.png"\nVIGNETTE 0\nSAVE "b.png"',         "Resource limits"),
    ('LOAD "a.png"\nDELETE 3\nSAVE "b.png"',           "Safe execution"),
    ('LOAD "a.png"\nos.system("x")\nSAVE "b.png"',     "Command validation"),
])
def test_rejection_names_the_failing_gate(source, gate):
    response = client.post("/api/compile", json={"source": source})
    assert response.status_code == 400
    checks = response.json()["security"]["checks"]
    failed = [c["name"] for c in checks if not c["passed"] and c["message"] != "Not reached."]
    assert failed == [gate]


def test_ordinary_syntax_errors_carry_no_security_report():
    response = client.post("/api/compile", json={"source": 'LOAD "a.png"\nBLUR\nSAVE "b.png"'})
    assert response.status_code == 400
    assert "security" not in response.json()
    assert response.json()["stage"] == "parser"


def test_traversal_rejection_still_leaks_no_path():
    body = client.post("/api/compile", json={
        "source": 'LOAD "../../etc/passwd"\nSAVE "b.png"'}).json()
    assert body["message"] == "Invalid file path."
    text = str(body)
    # the attacker's path is not reflected, and no server location appears
    for needle in ("passwd", "etc/", "storage", "/home"):
        assert needle not in text


def test_limits_expose_the_vignette_range():
    assert client.get("/api/limits").json()["vignette_range"] == [1, 100]


def test_trace_times_are_the_benchmarks_warm_medians(uploaded):
    body = client.post("/api/run", json={
        "source": 'LOAD "in.png"\nBLUR 3\nRESIZE 150 100\nSAVE "o.png"',
        "image_id": uploaded["image_id"],
        "width": uploaded["width"], "height": uploaded["height"],
    }).json()
    medians = body["benchmark"]["optimized_step_ms"]
    for t in body["trace"]:
        e = t["execution"]
        assert e["basis"] == "median of 5 warm runs"
        assert e["ms"] == medians[str(t["line"])]


def test_without_the_benchmark_trace_times_say_they_are_one_run(uploaded):
    body = client.post("/api/run", json={
        "source": 'LOAD "in.png"\nRESIZE 150 100\nSAVE "o.png"',
        "image_id": uploaded["image_id"], "width": uploaded["width"],
        "height": uploaded["height"], "benchmark": False,
    }).json()
    assert all("single run" in t["execution"]["basis"] for t in body["trace"])

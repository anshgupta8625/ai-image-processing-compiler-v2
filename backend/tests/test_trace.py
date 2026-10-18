"""The per-line trace must agree with the compiler, because it only reports on it."""

import json

import pytest

from compiler.optimizer import Optimizer
from compiler.pipeline import compile_program
from compiler.trace import attach_execution

SOURCE = '''# demo
LOAD "photo.jpg"
rotate 90
ROTATE 270
BLUR 3
BLUR 4
VIGNETTE 60
EDGE
RESIZE 400 300
SAVE "out.png"
'''


@pytest.fixture(scope="module")
def compiled():
    return compile_program(SOURCE, megapixels=12.0)


def by_line(compiled):
    return {t["line"]: t for t in compiled["trace"]}


def test_one_entry_per_command_in_source_order(compiled):
    assert [t["line"] for t in compiled["trace"]] == [2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert [t["command"] for t in compiled["trace"]] == [
        "LOAD", "ROTATE", "ROTATE", "BLUR", "BLUR", "VIGNETTE", "EDGE", "RESIZE", "SAVE"]


def test_comments_and_blank_lines_get_no_entry(compiled):
    assert 1 not in by_line(compiled)          # the "# demo" comment


def test_source_text_is_reported(compiled):
    assert by_line(compiled)[3]["source"] == "rotate 90"


# --- optimiser attribution ---------------------------------------------------

def test_cancelled_rotations_are_both_removed(compiled):
    t = by_line(compiled)
    for line in (3, 4):
        assert t[line]["status"] == "removed"
        assert t[line]["optimizer"]["final_instr"] is None
        assert t[line]["optimizer"]["events"][0]["pass"] == "constant-folding"


def test_fused_blur_is_rewritten_and_its_partner_removed(compiled):
    t = by_line(compiled)
    assert t[5]["status"] == "rewritten"
    assert t[5]["optimizer"]["final_instr"] == "BLUR(5)"
    assert "blur-fusion" in t[5]["optimizer"]["summary"]
    rewrite = [e for e in t[5]["optimizer"]["events"] if e["effect"] == "rewritten"]
    assert len(rewrite) == 1 and "fused" in rewrite[0]["note"]
    assert t[6]["status"] == "removed"


def test_hoisted_resize_is_the_moved_line(compiled):
    t = by_line(compiled)[9]
    assert t["status"] == "moved"
    assert t["optimizer"]["final_index"] < t["optimizer"]["original_index"]


def test_filters_pushed_down_are_kept_but_run_on_fewer_pixels(compiled):
    for line in (8, 7):                        # EDGE, VIGNETTE
        o = by_line(compiled)[line]["optimizer"]
        assert by_line(compiled)[line]["status"] == "kept"
        assert o["megapixels_after"] < o["megapixels_before"]
        assert "instead of" in o["summary"]


def test_untouched_lines_say_so(compiled):
    assert by_line(compiled)[2]["optimizer"]["summary"].startswith("No rewrite")


def test_rewrite_is_credited_to_the_pass_that_rewrote_it_not_a_later_shift(compiled):
    # BLUR 3 is rewritten by blur-fusion and then shifted by strength-reduction.
    summary = by_line(compiled)[5]["optimizer"]["summary"]
    assert "by blur-fusion" in summary and "strength-reduction" not in summary


# --- consistency with the cost model ----------------------------------------

def test_line_costs_sum_to_the_optimisers_totals(compiled):
    stats = compiled["optimizer_stats"]
    before = sum(t["optimizer"]["cost_before"] for t in compiled["trace"])
    after = sum(t["optimizer"]["cost_after"] for t in compiled["trace"])
    assert before == pytest.approx(stats["estimated_cost_before"], abs=0.01)
    assert after == pytest.approx(stats["estimated_cost_after"], abs=0.01)


def test_removed_lines_cost_nothing_afterwards(compiled):
    for t in compiled["trace"]:
        if t["status"] == "removed":
            assert t["optimizer"]["cost_after"] == 0.0


# --- stage content -----------------------------------------------------------

def test_lexer_stage_lists_this_lines_tokens(compiled):
    lex = by_line(compiled)[5]["lexer"]
    assert [t["type"] for t in lex["tokens"]] == ["COMMAND", "NUMBER"]
    assert lex["terminator"] == "NEWLINE"


def test_lowercase_keyword_is_called_out(compiled):
    assert any("case-insensitive" in n for n in by_line(compiled)[3]["lexer"]["notes"])


def test_parser_stage_reports_arity(compiled):
    assert "takes 2" in by_line(compiled)[9]["parser"]["arity"]
    assert by_line(compiled)[9]["parser"]["args"] == [400, 300]


def test_semantic_stage_uses_the_real_limits(compiled):
    checks = by_line(compiled)[5]["semantic"]["checks"]
    assert any("1 ≤ 3 ≤ 25" in c["detail"] for c in checks)
    assert any("7 × 7" in c["detail"] for c in checks)       # kernel 2r+1


def test_edge_defaults_are_explained(compiled):
    checks = by_line(compiled)[8]["semantic"]["checks"]
    assert checks[0]["rule"] == "Defaults" and "low=100" in checks[0]["detail"]


def test_negative_rotation_normalisation_is_explained():
    c = compile_program('LOAD "a.png"\nROTATE -90\nSAVE "b.png"', 1.0)
    detail = [x for x in c["trace"][1]["semantic"]["checks"] if x["rule"] == "Normalisation"]
    assert detail and "270" in detail[0]["detail"]


def test_ir_stage_shows_the_cost_formula(compiled):
    ir = by_line(compiled)[5]["ir"]
    assert ir["instr"] == "BLUR(3)" and "(1 + 3/5)" in ir["formula"]


# --- execution merge ---------------------------------------------------------

def fake_steps(compiled):
    return [{"line": t["optimizer"] and t["line"], "op": t["command"], "args": [],
             "ms": 1.5, "shape": [30, 40]}
            for t in compiled["trace"] if t["status"] != "removed"]


def test_warm_medians_replace_the_cold_single_run_when_supplied(compiled):
    steps = fake_steps(compiled)
    merged = attach_execution(compiled["trace"], steps,
                              step_ms={t["line"]: 0.25 for t in compiled["trace"]}, repeats=5)
    ran = [t["execution"] for t in merged if t["execution"]["ran"]]
    assert all(e["ms"] == 0.25 and e["basis"] == "median of 5 warm runs" for e in ran)


def test_single_run_is_labelled_as_such(compiled):
    merged = attach_execution(compiled["trace"], fake_steps(compiled))
    ran = [t["execution"] for t in merged if t["execution"]["ran"]]
    assert all(e["ms"] == 1.5 and "single run" in e["basis"] for e in ran)


def test_execution_data_is_merged_by_line(compiled):
    merged = attach_execution(compiled["trace"], fake_steps(compiled))
    ran = [t for t in merged if t["execution"]["ran"]]
    skipped = [t for t in merged if not t["execution"]["ran"]]
    assert {t["line"] for t in skipped} == {3, 4, 6}
    assert all(t["execution"]["width"] == 40 and t["execution"]["ms"] == 1.5 for t in ran)


def test_attaching_execution_does_not_mutate_the_compile_trace(compiled):
    attach_execution(compiled["trace"], fake_steps(compiled))
    assert all(t["execution"] is None for t in compiled["trace"])


def test_trace_is_json_serialisable_and_leaks_no_paths(compiled):
    text = json.dumps(compiled["trace"])
    for needle in ("/home", "/srv", "storage", "Traceback", "C:\\"):
        assert needle not in text


def test_optimizer_events_exist_only_for_accepted_rewrites():
    from compiler.ir import lower
    from compiler.lexer import tokenize
    from compiler.parser import parse
    from compiler.semantic import analyse

    ast = parse(tokenize('LOAD "a.png"\nGRAYSCALE\nSAVE "b.png"'))
    analyse(ast)
    opt = Optimizer(lower(ast), 1.0)
    opt.run()
    assert opt.line_events == {}


def test_a_line_that_only_changed_position_has_no_events(compiled):
    # EDGE and VIGNETTE were pushed down by the hoisted RESIZE; nothing happened to them.
    for line in (7, 8):
        assert by_line(compiled)[line]["optimizer"]["events"] == []

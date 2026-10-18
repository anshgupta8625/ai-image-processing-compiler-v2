"""End-to-end driver.

Wires the stages together and collects, at every step, the artefact the
frontend visualises: token list, AST dump, IR listing, optimiser log, optimised
IR listing, execution timings and the benchmark comparison.

The benchmark runs the program twice — once from the unoptimised IR and once
from the optimised IR — so the speed-up reported to the user is measured, not
predicted. The cost model's prediction is reported alongside it, which is more
honest and also more interesting: where the two disagree, the cost model is
wrong, and that is worth seeing.
"""

from __future__ import annotations

import security as sec

from . import ir as ir_mod
from .errors import CompilerError
from .executor import Executor
from .lexer import tokenize
from .optimizer import Optimizer
from .parser import parse
from .semantic import analyse
from .trace import attach_execution, build_trace


def compile_program(source: str, megapixels: float = 1.0) -> dict:
    """Run the front end and middle end. No image is touched here."""
    sec.scan_source(source)

    tokens = tokenize(source)
    ast = parse(tokens)
    info = analyse(ast)

    unoptimized = ir_mod.lower(ast)
    optimizer = Optimizer(unoptimized, megapixels)
    optimized, rewrites, stats = optimizer.run()
    trace = build_trace(source, tokens, ast, unoptimized, optimized,
                        optimizer.line_events, megapixels)

    return {
        "tokens": [
            {"type": t.type.name, "value": t.value, "line": t.line, "column": t.column}
            for t in tokens
        ],
        "ast": ast.pretty(),
        "semantics": info,
        "ir": unoptimized.listing(),
        "optimized_ir": optimized.listing(),
        "optimizations": [
            {
                "pass": r.pass_name,
                "description": r.description,
                "instructions_before": r.before,
                "instructions_after": r.after,
            }
            for r in rewrites
        ],
        "optimizer_stats": stats,
        "trace": trace,
        "_unoptimized": unoptimized,
        "_optimized": optimized,
    }


def execute(compiled: dict, stored_input: str, executor: Executor,
            benchmark: bool = True) -> dict:
    """Run the optimised program, and the unoptimised one for comparison."""
    optimized_run = executor.run(compiled["_optimized"], stored_input)

    result = {
        "output_file": optimized_run["output_file"],
        "execution": optimized_run,
    }

    bench = None
    if benchmark:
        bench = result["benchmark"] = _benchmark(compiled, stored_input, executor)

    # The compile-time trace, now with each line's measured time and size. When
    # the benchmark ran, per-line times are its warm medians: the single run
    # above is cold and pays one-time OpenCV setup, so it would overstate them.
    result["trace"] = attach_execution(
        compiled["trace"], optimized_run["steps"],
        step_ms=bench["optimized_step_ms"] if bench else None,
        repeats=bench["repeats"] if bench else None,
    )
    return result


def _benchmark(compiled: dict, stored_input: str, executor: Executor,
               repeats: int = 5) -> dict:
    """Time both pipelines several times and compare medians.

    A single sample is not a measurement. OpenCV timings on a warm cache vary
    by tens of percent run to run, which is the same order as some of the
    savings being claimed, so one run of each could easily report a speed-up
    that is pure noise.

    Median rather than mean, because the distribution is right-skewed: a run
    can be arbitrarily slow if the scheduler preempts it, but never faster than
    the work takes. The mean chases those outliers; the median ignores them.
    The spread is reported alongside so the reader can judge whether the gap
    between the two medians is larger than the noise.
    """
    def runs(ir) -> list[dict]:
        # One discarded warm-up run: the first pass pays for page faults and
        # OpenCV's lazy kernel setup, which are not what we are measuring.
        executor.run(ir, stored_input, persist=False)
        return [executor.run(ir, stored_input, persist=False) for _ in range(repeats)]

    def median(values: list[float]) -> float:
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2

    slow_runs = runs(compiled["_unoptimized"])
    fast_runs = runs(compiled["_optimized"])
    slow_samples = [r["total_ms"] for r in slow_runs]
    fast_samples = [r["total_ms"] for r in fast_runs]

    # Median time of each instruction of the optimised pipeline, keyed by source
    # line. Every run executes the same instructions in the same order, so
    # step i of one run corresponds to step i of the others.
    step_ms = {
        step["line"]: round(median([r["steps"][i]["ms"] for r in fast_runs]), 3)
        for i, step in enumerate(fast_runs[0]["steps"])
    }

    slow, fast = median(slow_samples), median(fast_samples)
    spread = max(
        max(slow_samples) - min(slow_samples),
        max(fast_samples) - min(fast_samples),
    )

    return {
        "repeats": repeats,
        "optimized_step_ms": step_ms,
        "unoptimized_ms": round(slow, 3),
        "optimized_ms": round(fast, 3),
        "unoptimized_range_ms": [round(min(slow_samples), 3),
                                 round(max(slow_samples), 3)],
        "optimized_range_ms": [round(min(fast_samples), 3),
                               round(max(fast_samples), 3)],
        "speedup": round(slow / fast, 2) if fast > 0 else None,
        "measured_saving_percent": (
            round(100 * (slow - fast) / slow, 1) if slow > 0 else 0.0
        ),
        "predicted_saving_percent":
            compiled["optimizer_stats"]["estimated_saving_percent"],
        # If the two medians differ by less than the observed noise, the
        # speed-up is not distinguishable from measurement error.
        "significant": abs(slow - fast) > spread,
    }


__all__ = ["compile_program", "execute", "CompilerError"]

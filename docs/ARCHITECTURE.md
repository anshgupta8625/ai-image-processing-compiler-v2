# Architecture

## Pipeline

```
                        USER
                          │
                          ▼
                  REACT FRONTEND
                          │
                          ▼
                ┌──────────────────┐
                │ SECURITY LAYER   │
                │ Input validation │
                │ File validation  │
                │ Path validation  │
                │ Resource limits  │
                │ Command whitelist│
                └────────┬─────────┘
                         │
                         ▼
                       LEXER          compiler/lexer.py
                         │
                         ▼
                      PARSER          compiler/parser.py
                         │
                         ▼
                        AST           compiler/ast_nodes.py
                         │
                         ▼
                SEMANTIC ANALYSIS     compiler/semantic.py
                         │
                         ▼
                         IR           compiler/ir.py
                         │
                         ▼
              COST-GUIDED OPTIMIZER   compiler/optimizer.py
                         │
                         ▼
                   OPTIMIZED IR
                         │
                         ▼
                  SAFE EXECUTION      compiler/executor.py
                         │
                         ▼
                      OpenCV
                         │
                         ▼
                   OUTPUT IMAGE
                         │
                         ▼
                    BENCHMARK         compiler/pipeline.py
```

## Why these stage boundaries

**Lexer / parser split.** The grammar is regular, so one hand-written scanner
could in principle produce the AST directly. Keeping them separate costs very
little and buys exact error positions: the lexer knows the column a bad
character sits in, and the parser knows which command it was reading when the
arity check failed.

**Why an AST *and* an IR.** The lowering is close to one-to-one, which makes
the IR look redundant. It earns its place for two reasons. The AST carries
source positions and argument sugar (`EDGE` with defaulted thresholds), so
optimiser passes would otherwise have to keep asking "was this argument written
or inferred?". And keeping the AST immutable lets the frontend display the
original tree beside the rewritten IR, which is the point of the visualisation.

**Semantic analysis delegates limits to the security layer.** `semantic.py`
calls `security.validate_blur()` rather than re-checking `1 <= r <= 25`, so
there is exactly one definition of every limit. The two modules speak different
error languages, so there is a small translation function at the boundary that
carries the user-safe message across and drops the internal detail.

## The optimiser

Six passes, run to a fixpoint (capped at 8 rounds):

| Pass | Rewrite |
|---|---|
| constant-folding | merge adjacent `ROTATE`, drop no-ops |
| idempotence | collapse repeated `GRAYSCALE` |
| redundant-resize | keep only the last `RESIZE` in a run |
| blur-fusion | two Gaussians → one, radius `√(a²+b²)` |
| strength-reduction | hoist a *shrinking* `RESIZE` above `BLUR`, `EDGE`, `GRAYSCALE`, `VIGNETTE` |
| dead-code | remove operations after `SAVE` |

**On the word "AI".** This is heuristic search guided by a cost model — AI in
the classical symbolic sense. There is no trained model and no learned policy,
and the documentation does not pretend otherwise. What distinguishes it from a
fixed pipeline is that every rewrite is *proposed* and then accepted only if
the cost model says the program got cheaper. A pass can therefore decline its
own transformation, which is what stops `blur-fusion` from firing when fusion
would push the radius past its ceiling.

**Strength reduction is the pass that matters.** Blurring a 4000×3000 image and
*then* shrinking it to 320×240 does twelve megapixels of expensive work to
produce 0.08 megapixels of output. Hoisting the resize typically cuts runtime
by 80–95% on large inputs. The pass refuses to move an *up*scale, because
enlarging and then filtering is genuinely a different image.

**Cost model.** Each opcode has a cost per megapixel, calibrated by timing
OpenCV on a 1000×1000 image. `BLUR` is scaled by radius rather than by area,
because OpenCV separates the Gaussian kernel into two 1-D passes. The absolute
units are meaningless; only the ratios matter, and only the sign of the
difference is ever used.

## Measuring instead of trusting

`pipeline.execute()` times both pipelines and reports the measured speed-up
beside the cost model's prediction. Where the two disagree, the cost model is
wrong, and that disagreement is shown in the UI rather than hidden.

Each figure is the **median of five runs after a discarded warm-up**. One
sample per pipeline is not a measurement: OpenCV timings vary run to run by the
same order as some of the savings being claimed, so a single pair of runs can
report a speed-up that is pure noise. The warm-up run is thrown away because
the first pass pays for page faults and OpenCV's lazy kernel setup, which are
not what is being measured. Median rather than mean, because the distribution
is right-skewed — a run can be arbitrarily slow if the scheduler preempts it,
but never faster than the work actually takes, so the mean chases outliers the
median ignores.

The min-max spread is reported alongside, and a gap between the two medians
smaller than that spread is flagged as not significant rather than presented as
a win. Benchmark repeats run with `persist=False`, which still encodes and
writes the output so `SAVE` is timed honestly, then deletes it.

## The per-line trace

The stage tabs each show one stage for the whole program. `compiler/trace.py`
turns that around: for every source line it reports what each stage did with it,
from the lexer to the executor. It makes no decisions of its own. Every fact is
read from an artefact another stage already produced (tokens, AST, IR, the
optimiser's event log, the executor's timings), so it cannot disagree with the
compiler.

Two details matter:

- **Attribution.** The optimiser records, for every *accepted* rewrite, which
  source lines it removed, rewrote or moved (`Optimizer.line_events`). A line
  that only changed position because something else moved is deliberately not an
  event; the trace reports the part that matters, the pixel count it now runs
  on, from the same cost profile (`ir.profile`) the optimiser uses. Per-line
  costs therefore sum exactly to the optimiser's totals, and a test asserts it.
- **Timing basis.** A single run is cold: it pays one-time OpenCV setup and can
  be several times slower than steady state. When the benchmark ran, per-line
  times are the median of its warm runs, and each figure says which basis it
  uses. Otherwise the single run is used and labelled as such.

## Backend layout

```
backend/
  app.py              FastAPI routes, error handlers, body-size middleware
  config.py           paths, CORS origins, TTLs
  security.py         the whole validation surface
  compiler/
    tokens.py         Token, TokenType
    lexer.py          source -> tokens
    ast_nodes.py      Program, Command
    parser.py         tokens -> AST, arity checks
    semantic.py       AST validation, range checks, filename safety
    ir.py             AST -> IR, cost model constants
    optimizer.py      six passes, fixpoint driver, cost model
    executor.py       IR -> OpenCV, static dispatch table
    trace.py          per-line trace: what every stage did with each source line
    pipeline.py       stage orchestration, benchmark
    errors.py         LexError / ParseError / SemanticError / ExecutionError
  tests/              196 tests
```

## Frontend

Three columns: editor with quick effects and the security shield, compilation
stages as tabs (the first being the per-line trace), and output with the
benchmark. Compilation is debounced at 400 ms and runs on every
edit, so the token stream and IR update as you type without touching an image.
Execution only happens when you press the button.

## Known weaknesses

- The cost model is calibrated on one machine and one OpenCV build. It gets
  the *ordering* of operations right, which is all the optimiser needs, but the
  predicted percentages drift from the measured ones on different hardware.
- `strength-reduction` moves at most one resize per round. Programs with
  several interleaved resizes converge over multiple rounds rather than in one
  pass, which is correct but not minimal.
- Execution is single-process and synchronous. Concurrent runs contend, and
  there is no work queue.

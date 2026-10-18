py --version# Image DSL Compiler

A compiler for a small domain-specific language that describes image-processing
pipelines. Programs are lexed, parsed, semantically checked, lowered to an
intermediate representation, optimised by a cost-model-guided rewriter, and
executed on OpenCV. The React frontend shows every stage.

```
LOAD "photo.jpg"
BLUR 3
EDGE 80 160
RESIZE 400 300
SAVE "edges.png"
```

Written naively, that program blurs and edge-detects twelve megapixels in order
to produce a 0.12 megapixel result. The optimiser hoists the `RESIZE` above both
filters, and the benchmark reports the measured difference.

## Running it

**Backend** (Python 3.10+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r ../requirements.txt
uvicorn app:app --reload --port 8000
```

**Frontend** (Node 18+), in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend, so the browser
sees a single origin in development.

**Tests:**

```bash
cd backend && pytest -q       # 196 tests
cd frontend && npm test       # 14 tests
```

## The language

Eight commands, no variables, no expressions, and no loops:

| | |
|---|---|
| `LOAD "file"` | load the uploaded image (first, exactly once) |
| `RESIZE w h` | scale to `w × h` |
| `GRAYSCALE` | convert to single channel |
| `BLUR r` | Gaussian blur, kernel `2r+1` |
| `ROTATE a` | rotate by a multiple of 90° |
| `EDGE [low high]` | Canny edge detection, defaults `100 200` |
| `VIGNETTE s` | darken smoothly towards the corners; `s` is the % lost at the corners (1-100) |
| `SAVE "file"` | write the result (last) |

Full grammar and ranges in [docs/DSL_REFERENCE.md](docs/DSL_REFERENCE.md).

The absence of loops is deliberate. A language with no iteration construct
cannot be made to run forever, which removes a whole class of denial-of-service
concern without needing a watchdog to catch it.

## Compilation stages

| Stage | Module | What it does |
|---|---|---|
| Security | `security.py` | injection scan, upload and path validation, resource limits |
| Lexer | `compiler/lexer.py` | source → tokens, with exact positions |
| Parser | `compiler/parser.py` | tokens → AST, arity checking |
| Semantics | `compiler/semantic.py` | ordering rules, types, ranges, filename safety |
| Lowering | `compiler/ir.py` | AST → flat IR with cost annotations |
| Optimiser | `compiler/optimizer.py` | six passes to a fixpoint |
| Executor | `compiler/executor.py` | IR → OpenCV via a static dispatch table |

Design rationale — including why there is both an AST and an IR, when the
lowering is nearly one-to-one — is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## The optimiser

Six passes: constant folding of rotations, `GRAYSCALE` idempotence, redundant
resize elimination, blur fusion (`√(a²+b²)`), strength reduction, and dead code
elimination. They run repeatedly until nothing changes. Strength reduction moves
a shrinking `RESIZE` above `BLUR`, `EDGE`, `GRAYSCALE` and `VIGNETTE`; all four
either commute with a downscale or are defined in resolution-independent
coordinates, which is what makes the reorder legal.

Each rewrite is proposed and then **accepted only if a cost model says the
program got cheaper**, so a pass can decline its own transformation. On the
word "AI": this is heuristic search guided by a cost function, in the classical
symbolic sense. There is no trained model here.

The frontend reports the cost model's *predicted* saving next to the *measured*
saving: the median of five timed runs of each pipeline, after a discarded
warm-up, with the min-max spread shown underneath. Where prediction and
measurement disagree, the cost model is wrong, and that is shown rather than
hidden. If the gap between the two medians is smaller than the run-to-run
spread, the UI says the difference is not distinguishable from noise instead of
claiming a speed-up.

## The interface

- **Line by line.** After a run, the *Line by line* tab follows each source line
  through every stage: its tokens, the AST node, the semantic checks it passed,
  its IR instruction and cost, what the optimiser did to it (kept, moved,
  rewritten or removed, and which pass did it), and its measured execution time.
  Per-line times are the median of the benchmark's warm runs, not a single cold
  run, and each is labelled with its basis.
- **Command guide (ⓘ, top right).** Every command, its parameters and ranges
  (read live from `/api/limits`, so they cannot drift from the backend), and what
  the optimiser does with it.
- **Profile (top right).** Team, course and stack.
- **Vignette.** A slider that writes a `VIGNETTE` line into the program. The
  editor stays the single source of truth; the slider only types for you.
- **Security shield.** See below.

## Security

Every input crosses `security.py` before reaching a compiler stage: a command
whitelist, filename rejection (not sanitisation) for path traversal, four-gate
upload validation including magic-byte agreement, and resource ceilings on
image size, program length and blur radius. Execution dispatches through a
static dictionary of Python functions — no `eval`, no `getattr` on user text.

Errors carry two payloads: a generic message for the user and full detail for
the server log, so a traversal attempt returns `"Invalid file path."` and never
a server path.

The **Security & Validation** panel is the visible face of this. Every program
crosses five gates, each described in plain English in the UI: command
validation, file validation, path validation, resource limits and safe
execution. When a program is rejected the panel names the exact gate that fired,
shows its code and line, marks every later gate *not reached*, and explains why
that class of input is dangerous. Four one-click demos (*Try an attack*) load a
harmless but hostile program (path traversal, code injection, resource abuse, an
unknown command) so the shield can be watched working.

The five gates are real checks on the raw program text, not decorations, and a
fuzz test asserts the converse that matters: wherever the compiler accepts a
program, every gate passes too, so the shield can never show a false alarm.

This is an **academic security layer**, not an audited one. The
[limitations section](docs/SECURITY.md#11-limitations) lists what it does not
protect against: no authentication, no rate limiting, no OS-level sandbox, and
a dependency on OpenCV's own memory safety.

## Layout

```
backend/     FastAPI app, security layer, compiler package, 196 tests
frontend/    React + Vite explorer UI, 14 tests
docs/        SECURITY.md, ARCHITECTURE.md, DSL_REFERENCE.md
examples/    sample programs, including ones that exercise each optimiser pass
```

## Known weaknesses

- The cost model is calibrated on one machine; predicted percentages drift on
  different hardware, though the ordering it produces stays right.
- Execution is synchronous and single-process; concurrent runs contend.
- `strength-reduction` moves one resize per round, so programs with several
  interleaved resizes converge over multiple rounds rather than in one pass.

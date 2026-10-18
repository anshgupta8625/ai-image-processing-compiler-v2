# Security & Safe Execution Layer

> **Scope note.** This is an *academic* security layer built to demonstrate secure
> input validation and safe execution principles for a compiler-design project.
> It is **not** a claim that the application is completely secure, and it has not
> been audited or penetration-tested. See [Limitations](#11-limitations).

---

## 1. Why security is required

The application accepts two kinds of untrusted input from the browser:

1. **DSL source code**, written freely by the user and submitted for compilation.
2. **Image files**, uploaded to the server and read by OpenCV.

Both are classic injection surfaces. A compiler that dispatches on user-supplied
strings is one `getattr()` away from remote code execution, and an image pipeline
that trusts filenames is one `../` away from serving `/etc/passwd`. The security
layer exists so that neither is possible by construction, not by luck.

---

## 2. Threat model

**Assumed attacker.** An unauthenticated remote user who can send arbitrary HTTP
requests to the API: any DSL text, any file bytes, any parameter values.

| # | Threat | Mitigation |
|---|---|---|
| T1 | Arbitrary code execution via crafted DSL | Command whitelist + no dynamic dispatch (§3, §8) |
| T2 | Shell command injection through parameters | Typed parameter validation; no shell is ever invoked (§4) |
| T3 | Path traversal on `LOAD` / `SAVE` | Separator rejection + sandbox resolution (§6) |
| T4 | Malicious file disguised as an image | Extension + MIME + magic-byte agreement (§5) |
| T5 | Denial of service via huge images or programs | Resource ceilings (§7) |
| T6 | Decompression bomb (small file, enormous raster) | Pixel-count check after decode (§7) |
| T7 | Information disclosure through error messages | Two-channel errors: safe message, private log (§9) |
| T8 | Disk exhaustion from accumulated uploads | Scoped temp directories and cleanup (§10) |

**Explicitly out of scope:** authenticated multi-user access control, secrets
management, TLS termination, network-level DDoS, and supply-chain integrity of
OpenCV/NumPy.

---

## 3. DSL command whitelist

```python
ALLOWED_COMMANDS = frozenset({
    "LOAD", "SAVE", "RESIZE", "GRAYSCALE", "BLUR", "ROTATE", "EDGE",
})
```

The whitelist is a frozen set, evaluated at import time. `validate_command()`
uppercases the candidate, checks membership, and raises `SecurityError` on any
miss. There is no fallback branch, no "unknown command is treated as a no-op",
and no wildcard.

The lexer only emits tokens for characters in the DSL alphabet, the parser only
builds AST nodes for whitelisted commands, and the executor dispatches through a
**static dictionary of Python callables** — never through `getattr()`,
`globals()`, `eval()`, or an import based on user text.

---

## 4. Input validation

Validation happens in two passes.

**Pass 1 — `scan_source()`, before the lexer runs.** Rejects empty programs,
programs over 8,000 characters or 100 lines, and any line matching the injection
pattern set: `eval(`, `exec(`, `compile(`, `__import__`, `getattr`, `os.system`,
`subprocess`, `import `, shell metacharacters (`; | & \` $`), and template or
markup markers (`${`, `<?`, `<script`). Comments are stripped before scanning so
prose in a `#` comment cannot trigger a false rejection.

This pass is technically redundant — the whitelist would reject all of it anyway
— but it fails fast, produces a specific message with a line number, and gives
the server a clean signal to log.

**Pass 2 — per-parameter validation, after parsing.**

| Command | Rule |
|---|---|
| `RESIZE w h` | integers, `1 ≤ w,h ≤ 4096`, `w*h ≤ 16,777,216` |
| `BLUR r` | integer, `1 ≤ r ≤ 25` |
| `ROTATE a` | integer, multiple of 90, `-360 ≤ a ≤ 360` |
| `LOAD`/`SAVE` | safe filename, allowed extension |

Booleans, lists, dicts and `None` are rejected before coercion, so
`validate_blur(True)` fails rather than silently becoming `1`.

---

## 5. File upload validation

An upload must clear four independent gates:

1. **Size** — at most 10 MB, checked against the actual byte length, not the
   `Content-Length` header.
2. **Extension** — `.png`, `.jpg`, `.jpeg`, `.webp` only.
3. **Declared MIME** — must be in `{image/png, image/jpeg, image/webp}` when the
   client sends one. Treated as a hint, never as proof.
4. **Magic bytes** — the first 16 bytes must carry a real image signature
   (`\x89PNG…`, `\xFF\xD8\xFF`, `RIFF….WEBP`) **and** that signature must agree
   with the extension. A PHP web shell renamed to `avatar.png` dies here.

The user's filename is then **discarded**. Files are stored as
`{uuid4().hex}{ext}`, so no attacker-chosen string ever reaches the filesystem.

---

## 6. Path traversal protection

`LOAD` and `SAVE` do not take paths. They take *names*, and `safe_basename()`
rejects anything else outright:

- any `/` or `\` → rejected
- any `..` → rejected
- leading `.` (hidden files) → rejected
- null bytes → rejected
- Windows drive letters and UNC prefixes → rejected (caught by the separator rule)
- anything not matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` → rejected

Note the deliberate choice to **reject rather than sanitise**. Stripping
`uploads/../../key.png` down to `key.png` would be safe, but it silently grants a
request the DSL never intended to serve; rejecting it is clearer and leaves no
normalisation gap to probe.

`resolve_inside(base_dir, name)` then joins the validated name to the sandbox
directory, calls `.resolve()` (which follows symlinks), and asserts the result is
`is_relative_to(base)`. A symlink planted inside `uploads/` cannot escape.

Uploads live in `storage/uploads/`, results in `storage/outputs/`. Nothing else
on the filesystem is reachable from the DSL.

---

## 7. Resource limits

| Limit | Value |
|---|---|
| Max upload size | 10 MB |
| Max request body | 12 MB |
| Max image dimensions | 4096 × 4096 |
| Max pixel count | 16,777,216 |
| Max DSL lines | 100 |
| Max DSL characters | 8,000 |
| Max operations / pipeline length | 50 |
| Max blur radius | 25 |
| Vignette strength | 1 to 100 |
| Max resize dimension | 4096 |
| Max execution time | 10 s |

Dimensions are re-checked **after** decode, which is what catches decompression
bombs: a 40 KB PNG that expands to 30,000 × 30,000 passes the size gate and fails
the pixel gate.

The DSL has **no loop or jump construct**, so a program cannot fail to terminate.
Execution time is bounded by `operations × per-operation cost`, both of which are
capped. The timeout is a backstop, not the primary defence.

---

## 8. Safe execution model

The core invariant:

> **No user-supplied string is ever executed, imported, or used to look up a
> Python attribute.**

Concretely, the codebase contains no `eval`, `exec`, `compile`, `__import__`,
`os.system`, `os.popen`, `subprocess`, or `getattr` with a non-literal name in
the request path. The IR interpreter is a `match` over a closed set of node types
whose handlers are ordinary functions bound at module load.

---

## 9. Error handling

`SecurityError` carries two payloads:

- `message` — shown to the user. Generic, actionable, path-free.
- `detail` — written to the server log only, with the reason code.

So a traversal attempt produces, on the wire:

```json
{ "error": "Security Error", "code": "INVALID_PATH",
  "message": "Invalid file path.", "line": 3 }
```

and never `/home/server/project/uploads/../../secret.txt`. Stack traces,
environment variables and internal module names are never serialised. In
production the framework's debug mode is off so unhandled exceptions return a
generic 500.

---

## 10. Temporary file handling

- Intermediate rasters stay in memory as NumPy arrays; nothing intermediate is
  written to disk.
- When a temp file is genuinely needed, it is created with `tempfile.mkdtemp()`
  inside the storage root and removed in a `finally` block.
- Uploads are deleted once the pipeline finishes and the result has been
  returned. A scheduled sweep removes anything older than one hour, so a crashed
  request cannot leak a file permanently.
- Output images are served by ID, not by path.

---

## 11. Limitations

Stated plainly, because a security document that only lists strengths is not a
security document:

- **Not audited.** No penetration test, no fuzzing campaign, no formal review.
- **No authentication or rate limiting.** Any client can submit unlimited
  requests; the per-request limits do not bound aggregate load.
- **Regex pre-scan is heuristic.** It is a fail-fast convenience. The whitelist,
  not the regex, is the actual boundary — do not treat the pattern list as
  exhaustive.
- **Trusts OpenCV and NumPy.** A memory-safety bug in an image decoder sits below
  this layer and is not mitigated by it.
- **No OS-level sandbox.** Execution is in-process; there is no seccomp profile,
  container isolation, or dropped-privilege worker.
- **Timeouts are cooperative** where the platform lacks reliable signal-based
  interruption.
- **No CSRF protection**, since there are no authenticated state-changing
  operations to protect.

---

## 12. Future security improvements

1. Run the executor in a separate process with a hard CPU/memory rlimit, or in a
   container with a seccomp profile.
2. Per-IP rate limiting and a request quota.
3. Optional API keys for deployed instances.
4. Structured audit logging of every rejection, with alerting on repeated
   traversal or injection attempts from one source.
5. Fuzz the lexer and parser (e.g. Atheris) to find crashes the test suite misses.
6. Content Security Policy headers and Subresource Integrity on the frontend.
7. Automated dependency scanning in CI.

---

## Security workflow

```
                        USER INPUT
                            │
                            ▼
                    INPUT VALIDATION
              (size, encoding, injection scan)
                            │
                            ▼
                  DSL COMMAND WHITELIST
                            │
                            ▼
                     PATH VALIDATION
              (separator + sandbox resolution)
                            │
                            ▼
                  RESOURCE LIMIT CHECK
                            │
                            ▼
                          LEXER
                            │
                            ▼
                         PARSER
                            │
                            ▼
                    SEMANTIC ANALYSIS
                            │
                            ▼
                      OPTIMIZATION
                            │
                            ▼
                  SAFE IMAGE EXECUTION
                  (static dispatch only)
                            │
                            ▼
                         OUTPUT

   Any stage may raise SecurityError ──▶ safe message to user
                                     └─▶ full detail to server log
```

---

## API surface

| Function | Purpose |
|---|---|
| `scan_source(source)` | Pre-lexer injection and size scan |
| `validate_command(name)` | Whitelist check, returns canonical name |
| `validate_operation_count(n)` | Pipeline length ceiling |
| `validate_resize(w, h)` | Typed, bounded resize parameters |
| `validate_blur(r)` | Typed, bounded blur radius |
| `validate_rotate(a)` | Typed, bounded rotation angle |
| `validate_vignette(s)` | Typed, bounded vignette strength |
| `check_paths(source)` | Every quoted filename must be a safe basename |
| `check_resource_limits(source)` | Operation count and numeric parameters, on the raw text |
| `check_whitelist(source)` | First word of every statement must be whitelisted |
| `safe_basename(path)` | Filename validation, traversal rejection |
| `resolve_inside(base, name)` | Sandbox-confined path resolution |
| `validate_upload(name, data, mime)` | Four-gate upload check, returns stored name |
| `validate_image_dimensions(w, h)` | Post-decode raster limits |
| `validate_request_size(length)` | Request body ceiling |
| `run_checklist(source, upload)` | Builds the frontend security panel |

`run_checklist()` returns the structure the **Security & Validation** panel
renders: the five checks in order, each with a pass/fail, a safe message, a
plain-English `what` description, and, on failure, the rejection `code` and
`line`. Checks after the first failure are `"Not reached."`.

The five gates are genuine checks on the raw program: command validation
(`scan_source`), file validation (`validate_upload`), path validation
(`check_paths`), resource limits (`check_resource_limits`) and safe execution
(`check_whitelist`). They reuse the same validators the compiler uses, so there
is still exactly one definition of every limit.

When `/api/compile` or `/api/run` rejects a program, the failing checklist is
attached to the error response, so the UI can show which gate fired. It is only
attached when a gate actually failed; an ordinary syntax error carries no
security report. The attacker's input is never echoed back in the response.

**No false alarms.** A red shield on a program that compiles would be a lie, so
`test_checklist_never_rejects_what_the_compiler_accepts` generates 600 random
programs and asserts that wherever the compiler accepts one, every gate passes.

---

## Tests

`cd backend && pytest -q` — 196 tests, of which the security suite covers all ten required attack cases:
unknown commands, invalid extensions, oversized uploads, path traversal, invalid
resize dimensions, excessive blur, excessive operation counts, invalid parameter
types, malformed DSL, and arbitrary code injection. Two further tests assert that
error responses leak no server paths and expose no internal fields.

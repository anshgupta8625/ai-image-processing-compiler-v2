"""Cost-model-guided optimiser.

On the word "AI": this is heuristic search over a rewrite space, guided by a
cost model — AI in the classical, symbolic sense, not machine learning. There
is no trained model here and the documentation says so plainly. What makes it
more than a fixed pipeline is that passes are applied *iteratively to a
fixpoint* and each rewrite is accepted only if the cost model says the program
got cheaper, so the optimiser can decline its own transformations.

Passes:

  P1  constant folding      - merge adjacent ROTATE, drop no-op rotations
  P2  idempotence           - collapse repeated GRAYSCALE
  P3  redundant resize      - only the last RESIZE in a run survives
  P4  blur fusion           - two Gaussians compose to one of radius sqrt(a^2+b^2)
  P5  strength reduction    - hoist a shrinking RESIZE above expensive filters
                              (BLUR, EDGE, GRAYSCALE, VIGNETTE)
  P6  dead code elimination - operations that cannot affect the output

P5 is the one that actually matters. Blurring a 4000x3000 image and *then*
shrinking it to 800x600 does the expensive work on 12 megapixels instead of
0.5. Reordering is only legal when the resize shrinks; enlarging first and
filtering after is not the same image, so the pass refuses it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .ir import IRProgram, Instr, profile

# Filters that commute with a downscale closely enough for our purposes.
# VIGNETTE qualifies because its falloff is defined in normalised coordinates,
# so it looks the same at any resolution.
# ROTATE is excluded: rotating then resizing is not the same as resizing then
# rotating unless the angle is a multiple of 180, and the bookkeeping is not
# worth the saving.
_HOISTABLE_OVER = {"BLUR", "EDGE", "GRAYSCALE", "VIGNETTE"}


@dataclass
class Rewrite:
    pass_name: str
    description: str
    before: int
    after: int


class Optimizer:
    def __init__(self, ir: IRProgram, megapixels: float = 1.0, max_rounds: int = 8):
        self.ir = ir.clone()
        self.megapixels = megapixels
        self.max_rounds = max_rounds
        self.log: list[Rewrite] = []
        # source line -> what each accepted rewrite did to that line's
        # instruction. The per-line trace in the frontend reads this.
        self.line_events: dict[int, list[dict]] = {}

    # -- cost model ---------------------------------------------------------

    def cost_of(self, instrs: list[Instr]) -> float:
        """Estimated cost, tracking how the raster size changes down the pipeline."""
        return round(sum(cost for _, cost in profile(instrs, self.megapixels)), 3)

    # -- driver -------------------------------------------------------------

    def run(self) -> tuple[IRProgram, list[Rewrite], dict]:
        original = self.ir.clone()
        before_cost = self.cost_of(original.instrs)

        passes = (
            ("constant-folding", self._fold_rotations),
            ("idempotence", self._collapse_grayscale),
            ("redundant-resize", self._drop_shadowed_resizes),
            ("blur-fusion", self._fuse_blurs),
            ("strength-reduction", self._hoist_downscale),
            ("dead-code", self._eliminate_dead_code),
        )

        for _ in range(self.max_rounds):
            changed = False
            for name, transform in passes:
                candidate = [Instr(i.op, list(i.args), i.line, i.origin)
                             for i in self.ir.instrs]
                note = transform(candidate)
                if note is None:
                    continue
                # Accept only if the cost model agrees this was an improvement.
                old, new = self.cost_of(self.ir.instrs), self.cost_of(candidate)
                if new < old - 1e-9:
                    self.log.append(Rewrite(name, note, len(self.ir.instrs), len(candidate)))
                    self._record_events(name, note, self.ir.instrs, candidate)
                    self.ir.instrs = candidate
                    changed = True
            if not changed:
                break

        after_cost = self.cost_of(self.ir.instrs)
        stats = {
            "estimated_cost_before": before_cost,
            "estimated_cost_after": after_cost,
            "estimated_saving_percent": (
                round(100 * (before_cost - after_cost) / before_cost, 1)
                if before_cost else 0.0
            ),
            "instructions_before": len(original.instrs),
            "instructions_after": len(self.ir.instrs),
            "rounds": len(self.log),
        }
        return self.ir, self.log, stats

    def _record_events(self, name: str, note: str,
                       old: list[Instr], new: list[Instr]) -> None:
        """Note what an accepted rewrite did to each source line.

        Effects: removed (the instruction is gone), rewritten (same line, new
        operation or arguments), moved (the instruction the pass relocated).
        An instruction that merely changed position because something else was
        removed or moved is not an event: nothing happened to it, and the
        per-line trace reports the part that matters (the pixel count it now
        runs on) from the cost profile instead.
        """
        old_by_line = {i.line: (n, i) for n, i in enumerate(old)}
        new_by_line = {i.line: (n, i) for n, i in enumerate(new)}

        for line, (_, old_instr) in old_by_line.items():
            if line not in new_by_line:
                effect = "removed"
            else:
                _, new_instr = new_by_line[line]
                if (old_instr.op, old_instr.args) != (new_instr.op, new_instr.args):
                    effect = "rewritten"
                elif new_instr.origin == name and old_instr.origin != name:
                    effect = "moved"
                else:
                    continue
            self.line_events.setdefault(line, []).append(
                {"pass": name, "effect": effect, "note": note}
            )

    # -- passes -------------------------------------------------------------

    def _fold_rotations(self, instrs: list[Instr]) -> str | None:
        i, note = 0, None
        while i < len(instrs) - 1:
            a, b = instrs[i], instrs[i + 1]
            if a.op == b.op == "ROTATE":
                merged = (a.args[0] + b.args[0]) % 360
                del instrs[i + 1]
                if merged == 0:
                    del instrs[i]
                    note = "two rotations cancelled out"
                else:
                    instrs[i] = Instr("ROTATE", [merged], a.line, "constant-folding")
                    note = f"merged rotations into ROTATE({merged})"
                continue
            if a.op == "ROTATE" and a.args[0] % 360 == 0:
                del instrs[i]
                note = "removed a 0-degree rotation"
                continue
            i += 1
        return note

    def _collapse_grayscale(self, instrs: list[Instr]) -> str | None:
        note, seen = None, False
        out = []
        for instr in instrs:
            if instr.op == "GRAYSCALE":
                if seen:
                    note = "removed a repeated GRAYSCALE"
                    continue
                seen = True
            elif instr.op in ("RESIZE", "ROTATE", "BLUR", "EDGE"):
                pass  # these preserve the single-channel property
            instr_out = instr
            out.append(instr_out)
        if note:
            instrs[:] = out
        return note

    def _drop_shadowed_resizes(self, instrs: list[Instr]) -> str | None:
        note = None
        i = 0
        while i < len(instrs) - 1:
            if instrs[i].op == "RESIZE" and instrs[i + 1].op == "RESIZE":
                del instrs[i]
                note = "dropped a resize immediately overwritten by another"
                continue
            i += 1
        return note

    def _fuse_blurs(self, instrs: list[Instr]) -> str | None:
        import security as sec

        note = None
        i = 0
        while i < len(instrs) - 1:
            a, b = instrs[i], instrs[i + 1]
            if a.op == b.op == "BLUR":
                # Composing two Gaussians gives a Gaussian whose sigma is the
                # quadrature sum. Radius tracks sigma linearly here.
                fused = int(round(math.hypot(a.args[0], b.args[0])))
                fused = max(1, min(fused, sec.Limits.MAX_BLUR_RADIUS))
                instrs[i] = Instr("BLUR", [fused], a.line, "blur-fusion")
                del instrs[i + 1]
                note = f"fused two blurs into BLUR({fused})"
                continue
            i += 1
        return note

    def _hoist_downscale(self, instrs: list[Instr]) -> str | None:
        """Move a shrinking RESIZE earlier, past filters it commutes with."""
        mp_at = self._sizes(instrs)
        for i, instr in enumerate(instrs):
            if instr.op != "RESIZE":
                continue
            target_mp = (instr.args[0] * instr.args[1]) / 1_000_000
            if target_mp >= mp_at[i]:
                continue  # not a downscale; reordering would change the result

            j = i
            while j - 1 > 0 and instrs[j - 1].op in _HOISTABLE_OVER:
                j -= 1
            if j == i:
                continue
            moved = instrs.pop(i)
            moved.origin = "strength-reduction"
            instrs.insert(j, moved)
            return f"moved RESIZE before {i - j} filter(s) so they run on fewer pixels"
        return None

    def _eliminate_dead_code(self, instrs: list[Instr]) -> str | None:
        """Drop work whose result is discarded.

        A GRAYSCALE immediately before an EDGE is not dead (EDGE needs it), but
        a BLUR whose output is overwritten by a LOAD would be — the grammar
        makes that unreachable, so the pass currently only removes operations
        sitting after the final SAVE, which the semantic analyser already
        rejects. It is kept because it costs nothing and documents intent.
        """
        for i, instr in enumerate(instrs):
            if instr.op == "SAVE" and i < len(instrs) - 1:
                removed = len(instrs) - i - 1
                del instrs[i + 1:]
                return f"removed {removed} operation(s) after SAVE"
        return None

    def _sizes(self, instrs: list[Instr]) -> list[float]:
        """Megapixel count entering each instruction."""
        mp, sizes = self.megapixels, []
        for instr in instrs:
            sizes.append(mp)
            if instr.op == "RESIZE":
                mp = (instr.args[0] * instr.args[1]) / 1_000_000
        return sizes


def optimize(ir: IRProgram, megapixels: float = 1.0):
    return Optimizer(ir, megapixels).run()

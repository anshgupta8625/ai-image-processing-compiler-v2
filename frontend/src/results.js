// How a compile-as-you-type response is folded into what is already on screen.
//
// A run response and a compile response both carry a `trace`, but only the
// run's has measured timings. A compile can resolve after a run (the debounce
// timer fires, or a request was already in flight), so a plain merge would wipe
// the timings of a program that has not changed. The rule: keep the run's
// trace while the program text is still the text that was run.

export function mergeCompile(previous, compiled, requestedSource) {
  const merged = { ...previous, ...compiled }
  if (previous?.trace && previous.ranSource === requestedSource) {
    merged.trace = previous.trace
  }
  return merged
}

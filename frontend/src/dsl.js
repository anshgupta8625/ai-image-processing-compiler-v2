// Small text helpers for the quick-effects bar. They edit the program source
// directly, so the editor stays the single source of truth: the slider is just
// a convenient way to type the line.

// A VIGNETTE statement, optionally indented, optionally followed by a comment.
const VIGNETTE_LINE = /^([ \t]*)VIGNETTE[ \t]+(-?\d+)([ \t]*(?:#.*)?)$/im

export function getVignette(source) {
  const match = source.match(VIGNETTE_LINE)
  return match ? Number(match[2]) : null
}

export function setVignette(source, value) {
  if (VIGNETTE_LINE.test(source)) {
    return source.replace(VIGNETTE_LINE, (_, indent, _old, tail) => `${indent}VIGNETTE ${value}${tail}`)
  }
  // No vignette yet: insert it just before the final SAVE, so it is applied to
  // the finished image. With no SAVE, append.
  const lines = source.split('\n')
  let save = -1
  lines.forEach((line, i) => { if (/^\s*SAVE\b/i.test(line)) save = i })
  if (save === -1) lines.push(`VIGNETTE ${value}`)
  else lines.splice(save, 0, `VIGNETTE ${value}`)
  return lines.join('\n')
}

export function removeVignette(source) {
  return source
    .split('\n')
    .filter((line) => !/^[ \t]*VIGNETTE[ \t]+-?\d+[ \t]*(?:#.*)?$/i.test(line))
    .join('\n')
}

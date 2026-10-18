import { getVignette, removeVignette, setVignette } from '../dsl'

// Quick effects write ordinary DSL into the editor, so the program text is
// still the single source of truth. Dragging the slider edits the VIGNETTE
// line; it never bypasses the compiler.
export default function QuickEffects({ source, onChange, range = [1, 100] }) {
  const [min, max] = range
  const current = getVignette(source)
  const value = current ?? 40
  // EDGE leaves thin white lines on black, so darkening its corners shows
  // almost nothing. Say so rather than let the slider look broken.
  const afterEdge = /^[ \t]*EDGE\b/im.test(source)

  return (
    <div className="effects">
      <div className="effects-head">
        <label htmlFor="vignette-range">Vignette</label>
        <span className="effects-value">{current === null ? 'off' : `${value}%`}</span>
      </div>

      <div className="effects-row">
        <input
          id="vignette-range"
          type="range"
          min={min}
          max={max}
          value={Math.min(Math.max(value, min), max)}
          onChange={(e) => onChange(setVignette(source, Number(e.target.value)))}
          aria-describedby="vignette-help"
        />
        {current === null ? (
          <button type="button" onClick={() => onChange(setVignette(source, value))}>Add</button>
        ) : (
          <button type="button" onClick={() => onChange(removeVignette(source))}>Remove</button>
        )}
      </div>

      {afterEdge && (
        <p className="effects-warn">
          This program uses <code>EDGE</code>, which outputs thin white lines on black, so a vignette
          after it is hard to see. Try it on a colour pipeline.
        </p>
      )}

      <p id="vignette-help" className="effects-help">
        Darkens towards the corners. Adds a <code>VIGNETTE</code> line before <code>SAVE</code>; the
        optimiser moves any shrinking <code>RESIZE</code> above it.
      </p>
    </div>
  )
}

import { useState } from 'react'

const STATUS = {
  kept: { label: 'Kept', icon: '=' },
  moved: { label: 'Moved', icon: '↑' },
  rewritten: { label: 'Rewritten', icon: '✎' },
  removed: { label: 'Removed', icon: '✕' },
}

function StatusPill({ status }) {
  const info = STATUS[status] ?? STATUS.kept
  return (
    <span className={`status-pill ${status}`}>
      <span aria-hidden="true">{info.icon}</span> {info.label}
    </span>
  )
}

function Step({ index, title, children }) {
  return (
    <li className="step">
      <span className="step-dot" aria-hidden="true">{index}</span>
      <div className="step-body">
        <h4>{title}</h4>
        {children}
      </div>
    </li>
  )
}

const fmt = (n, digits = 2) => (typeof n === 'number' ? n.toFixed(digits) : '–')

function CostBar({ label, value, max }) {
  const width = max > 0 ? Math.max((value / max) * 100, value > 0 ? 2 : 0) : 0
  return (
    <div className="cost-row">
      <span>{label}</span>
      <div className="bar" aria-hidden="true"><span style={{ width: `${width}%` }} /></div>
      <code>{fmt(value, 1)}</code>
    </div>
  )
}

function LineDetail({ t, maxCost }) {
  const o = t.optimizer
  return (
    <ol className="timeline">
      <Step index="1" title="Lexer · source to tokens">
        <div className="tokens compact">
          {t.lexer.tokens.map((tok, i) => (
            <span key={i} className={`token t-${tok.type.toLowerCase()}`} title={`column ${tok.column}`}>
              {tok.value}
            </span>
          ))}
          <span className="token t-newline" title="line terminator">
            {t.lexer.terminator === 'NEWLINE' ? '⏎' : 'EOF'}
          </span>
        </div>
        <p>{t.lexer.summary}</p>
        {t.lexer.notes.map((note) => <p className="note-line" key={note}>{note}</p>)}
      </Step>

      <Step index="2" title="Parser · tokens to AST">
        <p><code>{t.parser.rule}</code></p>
        <p>{t.parser.summary} {t.parser.arity}</p>
        <p className="note-line">Expected shape: <code>{t.parser.shape}</code></p>
      </Step>

      <Step index="3" title="Semantic analysis · is it meaningful?">
        <ul className="checks">
          {t.semantic.checks.map((c) => (
            <li key={c.rule}><span className="tick" aria-hidden="true">✓</span><strong>{c.rule}</strong> {c.detail}</li>
          ))}
        </ul>
      </Step>

      <Step index="4" title="IR lowering · cost annotated">
        <p><code>{t.ir.instr}</code> at position {t.ir.index}, entering with {fmt(t.ir.megapixels_in, 3)} MP.</p>
        <p className="note-line">Cost = {t.ir.formula} = <strong>{fmt(t.ir.cost, 1)}</strong> units</p>
      </Step>

      <Step index="5" title="Optimiser · cost-model guided">
        <p><StatusPill status={t.status} /> {o.summary}</p>
        {o.events.length > 0 && (
          <ul className="events">
            {o.events.map((e, i) => (
              <li key={i}><code>{e.pass}</code> {e.note}</li>
            ))}
          </ul>
        )}
        <div className="cost-bars">
          <CostBar label="Before" value={o.cost_before} max={maxCost} />
          <CostBar label="After" value={o.cost_after} max={maxCost} />
        </div>
        {o.final_instr && (
          <p className="note-line">
            Final form <code>{o.final_instr}</code> at position {o.final_index}
            {o.megapixels_after != null && <>, on {fmt(o.megapixels_after, 3)} MP</>}.
          </p>
        )}
      </Step>

      <Step index="6" title="Execution · OpenCV">
        {t.execution?.ran && (
          <>
            <p>
              <code>{t.execution.instr}</code> took <strong>{fmt(t.execution.ms, 3)} ms</strong>{' '}
              <span className="basis">({t.execution.basis})</span> and left the image at{' '}
              <strong>{t.execution.width} × {t.execution.height}</strong>.
            </p>
            <p className="note-line">{t.execution.summary}</p>
          </>
        )}
        {t.execution && !t.execution.ran && <p>{t.execution.summary}</p>}
        {!t.execution && <p className="placeholder">Run the program to measure this line.</p>}
      </Step>
    </ol>
  )
}

export default function LineByLine({ trace, stale }) {
  const [openLine, setOpenLine] = useState(null)

  if (!trace || trace.length === 0) {
    return <p className="placeholder">Start typing a valid program to see how each line is compiled.</p>
  }

  // Open the first line the optimiser did something to, so the view starts on
  // an interesting example; fall back to the first line.
  // openLine: null = nothing chosen yet (use the fallback), -1 = the reader
  // collapsed everything, otherwise the chosen line number.
  const fallback = trace.find((t) => t.status !== 'kept') ?? trace[0]
  const activeLine =
    openLine === -1 ? -1 : trace.some((t) => t.line === openLine) ? openLine : fallback.line
  const activeIndex = trace.findIndex((t) => t.line === activeLine)

  const counts = trace.reduce((acc, t) => ({ ...acc, [t.status]: (acc[t.status] ?? 0) + 1 }), {})
  const before = trace.reduce((sum, t) => sum + t.optimizer.cost_before, 0)
  const after = trace.reduce((sum, t) => sum + t.optimizer.cost_after, 0)
  const saving = before > 0 ? Math.round((100 * (before - after)) / before) : 0
  const maxCost = Math.max(...trace.map((t) => t.optimizer.cost_before), 1)

  const step = (delta) => {
    const from = activeIndex === -1 ? (delta > 0 ? -1 : trace.length) : activeIndex
    setOpenLine(trace[Math.min(Math.max(from + delta, 0), trace.length - 1)].line)
  }

  return (
    <div className="lbl">
      {stale && (
        <p className="stale">The program has an error, so this is the last version that compiled.</p>
      )}

      <div className="lbl-summary">
        <div>
          <strong>{trace.length}</strong> lines
          {Object.entries(STATUS).filter(([k]) => counts[k]).map(([k, v]) => (
            <span key={k} className={`count ${k}`}>{counts[k]} {v.label.toLowerCase()}</span>
          ))}
        </div>
        <div className="lbl-cost">
          Estimated cost <code>{fmt(before, 1)}</code> → <code>{fmt(after, 1)}</code>
          {saving > 0 && <span className="saving"> (−{saving}%)</span>}
        </div>
      </div>

      <div className="lbl-nav">
        <button type="button" onClick={() => step(-1)} disabled={activeIndex === 0}>◀ Previous</button>
        <span>
          {activeIndex === -1
            ? 'Choose a line'
            : `Line ${trace[activeIndex].line} · ${activeIndex + 1} of ${trace.length}`}
        </span>
        <button type="button" onClick={() => step(1)} disabled={activeIndex === trace.length - 1}>Next ▶</button>
      </div>

      <ul className="lbl-list">
        {trace.map((t) => {
          const open = t.line === activeLine
          return (
            <li key={t.line} className={`lbl-item ${open ? 'open' : ''} ${t.status}`}>
              <button type="button" className="lbl-head" aria-expanded={open}
                      onClick={() => setOpenLine(open ? -1 : t.line)}>
                <span className="lbl-line">L{t.line}</span>
                <code className="lbl-src">{t.source}</code>
                <StatusPill status={t.status} />
                <span className="lbl-chev" aria-hidden="true">{open ? '▾' : '▸'}</span>
              </button>
              {open && <LineDetail t={t} maxCost={maxCost} />}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

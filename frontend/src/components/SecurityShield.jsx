import { ATTACKS, CODE_EXPLAIN } from '../data/attacks'

const NOT_REACHED = 'Not reached.'

function ShieldIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none"
         stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
  )
}

// The checklist is the visible face of security.py. Each row says what the gate
// does, and when a program is rejected the row that fired is marked and
// explained, with every later gate shown as "not reached".
export default function SecurityShield({ report, stashed, onAttack, onRestore }) {
  if (!report) return null

  const failing = report.checks.find((c) => !c.passed && c.message !== NOT_REACHED)
  const passedCount = report.checks.filter((c) => c.passed).length
  const state = failing ? 'blocked' : 'ok'

  return (
    <section className={`shield ${state}`} aria-label="Security and validation">
      <header className="shield-head">
        <h3><ShieldIcon /> Security &amp; Validation</h3>
        <span className={`shield-pill ${state}`} role="status">
          {failing ? `Blocked at ${failing.name}` : `${passedCount} of ${report.checks.length} gates passed`}
        </span>
      </header>

      <p className="shield-lead">
        Every program crosses five gates before any image work starts. Nothing the user types is ever
        evaluated as code.
      </p>

      {failing && (
        <div className="shield-blocked">
          <strong>
            {failing.code ?? 'REJECTED'}{failing.line ? ` · line ${failing.line}` : ''}
          </strong>
          <p>{failing.message}</p>
          {CODE_EXPLAIN[failing.code] && <p className="why">{CODE_EXPLAIN[failing.code]}</p>}
          <p className="why">
            The user sees only this safe message. Full detail goes to the server log, never to the browser.
          </p>
        </div>
      )}

      <ul className="gates">
        {report.checks.map((check) => {
          const skipped = !check.passed && check.message === NOT_REACHED
          const status = check.passed ? 'pass' : skipped ? 'skip' : 'fail'
          return (
            <li key={check.name} className={status}>
              <span className="mark" aria-hidden="true">{check.passed ? '✓' : skipped ? '–' : '✗'}</span>
              <div>
                <strong>{check.name}</strong>
                <span className="sr-only">{check.passed ? ' passed' : skipped ? ' not reached' : ' failed'}</span>
                {check.what && <small>{check.what}</small>}
              </div>
            </li>
          )
        })}
      </ul>

      <div className="attacks">
        <h4>Try an attack</h4>
        <div className="attack-chips">
          {ATTACKS.map((attack) => (
            <button key={attack.id} type="button" className="chip" title={attack.hint}
                    onClick={() => onAttack(attack)}>
              {attack.label}
            </button>
          ))}
          {stashed !== null && (
            <button type="button" className="chip restore" onClick={onRestore}>
              ↩ Restore my program
            </button>
          )}
        </div>
        <p className="attack-note">
          Loads a harmless but hostile program into the editor so you can watch the gate that stops it.
        </p>
      </div>
    </section>
  )
}

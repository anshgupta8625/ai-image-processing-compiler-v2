import { useCallback, useEffect, useState } from 'react'
import { compileProgram, getLimits, runProgram, uploadImage } from './api'
import { mergeCompile } from './results'
import InfoModal from './components/InfoModal'
import LineByLine from './components/LineByLine'
import ProfileModal from './components/ProfileModal'
import QuickEffects from './components/QuickEffects'
import SecurityShield from './components/SecurityShield'

const SAMPLE = `# Downscale after filtering on purpose -
# watch the optimiser move the RESIZE up.
LOAD "input.png"
BLUR 4
VIGNETTE 45
RESIZE 320 240
SAVE "output.png"
`

const STAGES = ['Line by line', 'Tokens', 'AST', 'IR', 'Optimised IR', 'Passes']

export default function App() {
  const [source, setSource] = useState(SAMPLE)
  const [image, setImage] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [stage, setStage] = useState('Line by line')
  const [limits, setLimits] = useState(null)
  const [modal, setModal] = useState(null)      // 'info' | 'profile' | null
  const [stash, setStash] = useState(null)      // the user's program while an attack demo is loaded
  const closeModal = useCallback(() => setModal(null), [])

  useEffect(() => {
    getLimits().then(setLimits).catch(() => {})
  }, [])

  // Compile-as-you-type. Debounced, because every keystroke would otherwise
  // hit the backend; 400ms is long enough to finish a word.
  useEffect(() => {
    // `stale` guards against out-of-order responses: if the program changes
    // while a request is in flight, the old answer must not overwrite the new.
    let stale = false
    const timer = setTimeout(() => {
      compileProgram({
        source,
        width: image?.width ?? 1000,
        height: image?.height ?? 1000,
      })
        .then((data) => {
          if (stale) return
          setResult((prev) => mergeCompile(prev, data, source))
          setError(null)
        })
        .catch((err) => { if (!stale) setError(err) })
    }, 400)
    return () => { stale = true; clearTimeout(timer) }
  }, [source, image])

  async function handleUpload(event) {
    const file = event.target.files?.[0]
    if (!file) return
    setError(null)
    try {
      setImage(await uploadImage(file))
    } catch (err) {
      setError(err)
      setImage(null)
    }
  }

  async function handleRun() {
    if (!image) { setError(new Error('Upload an image first.')); return }
    setBusy(true)
    setError(null)
    try {
      const ran = await runProgram({
        source,
        image_id: image.image_id,
        width: image.width,
        height: image.height,
        benchmark: true,
      })
      // Remember which program text produced these timings (see results.js).
      setResult({ ...ran, ranSource: source })
      // Once there is a result, the most useful thing to look at is how each
      // line was compiled and executed.
      setStage('Line by line')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  function tryAttack(attack) {
    setStash((saved) => saved ?? source)   // remember the first program only
    setSource(attack.code)
  }

  function restoreProgram() {
    if (stash === null) return
    setSource(stash)
    setStash(null)
  }

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>Image DSL Compiler</h1>
          <p className="subtitle">
            A small domain-specific language for image pipelines, compiled through
            lexer, parser, semantic analysis and a cost-guided optimiser.
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="icon-btn" onClick={() => setModal('info')}
                  aria-label="Command guide" title="Command guide">
            <span aria-hidden="true">ⓘ</span>
          </button>
          <button type="button" className="profile-btn" onClick={() => setModal('profile')}
                  aria-label="Project profile" title="Project profile">
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none"
                 stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="8" r="3.5" />
              <path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" />
            </svg>
            <span>Profile</span>
          </button>
        </div>
      </header>

      {modal === 'info' && <InfoModal limits={limits} onClose={closeModal} />}
      {modal === 'profile' && <ProfileModal onClose={closeModal} />}

      <div className="columns">
        <section className="panel editor">
          <h2>Program</h2>
          <textarea
            value={source}
            spellCheck={false}
            onChange={(e) => setSource(e.target.value)}
          />

          <div className="controls">
            <label className="file-button">
              Choose image
              <input type="file" accept="image/*" onChange={handleUpload} hidden />
            </label>
            <button onClick={handleRun} disabled={busy || !image}>
              {busy ? 'Running…' : 'Compile & Run'}
            </button>
          </div>

          {image && (
            <p className="meta">
              {image.width} × {image.height} ({image.megapixels} MP)
            </p>
          )}

          <QuickEffects source={source} onChange={setSource} range={limits?.vignette_range} />

          {error && (
            <div className="error">
              <strong>{error.stage ? `${error.stage} error` : 'Error'}</strong>
              {error.line ? ` on line ${error.line}` : ''}
              <p>{error.message}</p>
            </div>
          )}

          <SecurityShield
            report={error?.security ?? result?.security}
            stashed={stash}
            onAttack={tryAttack}
            onRestore={restoreProgram}
          />
          {limits && <Reference limits={limits} />}
        </section>

        <section className="panel stages">
          <h2>Compilation</h2>
          <nav className="tabs">
            {STAGES.map((name) => (
              <button
                key={name}
                className={stage === name ? 'tab active' : 'tab'}
                onClick={() => setStage(name)}
              >
                {name}
              </button>
            ))}
          </nav>
          {error && stage !== 'Line by line' && result && (
            <p className="stale">The program has an error, so this is the last version that compiled.</p>
          )}
          <StageView stage={stage} result={result} stale={Boolean(error)} />
        </section>

        <section className="panel output">
          <h2>Output</h2>
          {result?.output_url ? (
            <img className="result" src={result.output_url} alt="Pipeline result" />
          ) : (
            <p className="placeholder">Run the program to see the result.</p>
          )}
          <Benchmark data={result?.benchmark} stats={result?.optimizer_stats} />
        </section>
      </div>
    </div>
  )
}

function StageView({ stage, result, stale }) {
  if (!result) return <p className="placeholder">Start typing to compile.</p>

  if (stage === 'Line by line') return <LineByLine trace={result.trace} stale={stale} />

  if (stage === 'Tokens') {
    return (
      <div className="tokens">
        {result.tokens?.map((t, i) => (
          <span key={i} className={`token t-${t.type.toLowerCase()}`} title={`line ${t.line}`}>
            {t.type === 'NEWLINE' ? '⏎' : t.value || t.type}
          </span>
        ))}
      </div>
    )
  }

  if (stage === 'Passes') {
    const passes = result.optimizations ?? []
    if (passes.length === 0) {
      return <p className="placeholder">No rewrites applied — the program is already optimal.</p>
    }
    return (
      <ol className="passes">
        {passes.map((p, i) => (
          <li key={i}>
            <code>{p.pass}</code>
            <span>{p.description}</span>
            <em>{p.instructions_before} → {p.instructions_after} instructions</em>
          </li>
        ))}
      </ol>
    )
  }

  const content = {
    AST: result.ast,
    IR: result.ir,
    'Optimised IR': result.optimized_ir,
  }[stage]

  return <pre className="dump">{content || '—'}</pre>
}

function Benchmark({ data, stats }) {
  if (!stats) return null
  return (
    <div className="benchmark">
      <h3>Benchmark</h3>
      <dl>
        <dt>Predicted saving</dt>
        <dd>{stats.estimated_saving_percent}%</dd>
        {data && (
          <>
            <dt>Measured saving</dt>
            <dd>{data.measured_saving_percent}%</dd>
            <dt>Unoptimised</dt>
            <dd>
              {data.unoptimized_ms} ms
              <small>{data.unoptimized_range_ms.join('–')}</small>
            </dd>
            <dt>Optimised</dt>
            <dd>
              {data.optimized_ms} ms
              <small>{data.optimized_range_ms.join('–')}</small>
            </dd>
            <dt>Speed-up</dt>
            <dd>{data.speedup}×</dd>
          </>
        )}
      </dl>
      {data && (
        <>
          <p className={data.significant ? 'note' : 'note warn'}>
            {data.significant
              ? `Median of ${data.repeats} runs each, after a discarded warm-up.
                 The gap exceeds the run-to-run spread, so the speed-up is real.`
              : `Median of ${data.repeats} runs each. The gap is smaller than the
                 spread between runs, so this difference is not distinguishable
                 from measurement noise — treat it as no change.`}
          </p>
          <p className="note">
            Predicted comes from the optimiser's cost model; measured comes from
            running both pipelines. Where they disagree, the cost model is wrong.
          </p>
        </>
      )}
    </div>
  )
}

function Reference({ limits }) {
  return (
    <details className="reference">
      <summary>Command reference &amp; limits</summary>
      <p className="commands">{limits.commands.join(' · ')}</p>
      <ul>
        <li>Formats: {limits.extensions.join(', ')}</li>
        <li>Max upload: {limits.max_upload_mb} MB</li>
        <li>Max dimensions: {limits.max_dimensions.join(' × ')}</li>
        <li>Max lines: {limits.max_lines}, max operations: {limits.max_operations}</li>
        <li>Max blur radius: {limits.max_blur_radius}</li>
        {limits.vignette_range && (
          <li>Vignette strength: {limits.vignette_range.join('–')}</li>
        )}
      </ul>
    </details>
  )
}

import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeCompile } from './results.js'

const compileTrace = [{ line: 2, execution: null }]
const runTrace = [{ line: 2, execution: { ran: true, ms: 1.2 } }]

test('a compile for the same program does not wipe the run timings', () => {
  const previous = { trace: runTrace, ranSource: 'PROGRAM', output_url: '/api/image/x.png' }
  const merged = mergeCompile(previous, { trace: compileTrace, tokens: [1] }, 'PROGRAM')
  assert.equal(merged.trace, runTrace)
  assert.deepEqual(merged.tokens, [1])                 // other fields still refresh
  assert.equal(merged.output_url, '/api/image/x.png')  // and the output image stays
})

test('editing the program discards timings that no longer apply', () => {
  const previous = { trace: runTrace, ranSource: 'PROGRAM' }
  const merged = mergeCompile(previous, { trace: compileTrace }, 'PROGRAM EDITED')
  assert.equal(merged.trace, compileTrace)
})

test('before any run the compile trace is used', () => {
  assert.equal(mergeCompile(null, { trace: compileTrace }, 'PROGRAM').trace, compileTrace)
  assert.equal(mergeCompile({ trace: compileTrace }, { trace: compileTrace }, 'PROGRAM').trace, compileTrace)
})

test('a previous result without a trace does not resurrect one', () => {
  const merged = mergeCompile({ ranSource: 'PROGRAM' }, { trace: compileTrace }, 'PROGRAM')
  assert.equal(merged.trace, compileTrace)
})

// Thin wrapper over the backend. Every call funnels through request() so the
// error shape is handled in one place: the backend always returns a `message`
// field that is safe to show, so we surface that rather than the status code.

const BASE = '/api'

async function request(path, options = {}) {
  const response = await fetch(BASE + path, options)
  const body = await response.json().catch(() => ({}))

  if (!response.ok) {
    const error = new Error(body.message || 'Request failed.')
    error.code = body.code
    error.stage = body.stage
    error.line = body.line
    // When a gate in security.py stopped the program, the backend attaches the
    // checklist so the UI can show which gate fired.
    error.security = body.security
    throw error
  }
  return body
}

export const getLimits = () => request('/limits')

export function uploadImage(file) {
  const form = new FormData()
  form.append('file', file)
  return request('/upload', { method: 'POST', body: form })
}

const json = (payload) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
})

export const compileProgram = (payload) => request('/compile', json(payload))
export const runProgram = (payload) => request('/run', json(payload))

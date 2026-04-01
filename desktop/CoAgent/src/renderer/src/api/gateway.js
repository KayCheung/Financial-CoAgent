const baseUrl = import.meta.env.VITE_GATEWAY_URL || 'http://127.0.0.1:8000'
const apiV1 = `${baseUrl}/api/v1`

async function parseJson(res) {
  const text = await res.text()
  if (!res.ok) {
    let detail = text
    try {
      const j = JSON.parse(text)
      detail = j.detail ?? text
    } catch {
      /* keep text */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return text ? JSON.parse(text) : {}
}

export async function devLogin() {
  const res = await fetch(`${apiV1}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grant_type: 'client_credentials', client_id: 'desktop' })
  })
  return parseJson(res)
}

export async function listSessions(token, { limit = 50, offset = 0 } = {}) {
  const q = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const res = await fetch(`${apiV1}/sessions?${q}`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  return parseJson(res)
}

export async function createSession(token, { title = null, session_type = 'chat' } = {}) {
  const res = await fetch(`${apiV1}/sessions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ title, session_type })
  })
  return parseJson(res)
}

export async function usageSummary(token) {
  const res = await fetch(`${apiV1}/usage/summary`, {
    headers: { Authorization: `Bearer ${token}` }
  })
  return parseJson(res)
}

export async function chatStream(token, { sessionId, message }, onSseData) {
  const res = await fetch(`${apiV1}/chat/stream`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    body: JSON.stringify({ session_id: sessionId, message })
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  await consumeSse(res, onSseData)
}

export async function chatResume(token, { sessionId, resumeToken }, onSseData) {
  const res = await fetch(`${apiV1}/chat/resume`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'text/event-stream'
    },
    body: JSON.stringify({ session_id: sessionId, resume_token: resumeToken })
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  await consumeSse(res, onSseData)
}

export async function chatInterrupt(token, sessionId) {
  const res = await fetch(`${apiV1}/chat/interrupt`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ session_id: sessionId })
  })
  return parseJson(res)
}

async function consumeSse(response, onEvent) {
  const reader = response.body?.getReader()
  if (!reader) return
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let sep
    while ((sep = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      for (const line of block.split('\n')) {
        if (line.startsWith('data:')) {
          const raw = line.slice(5).trim()
          try {
            onEvent(JSON.parse(raw))
          } catch {
            /* ignore bad chunk */
          }
        }
      }
    }
  }
}

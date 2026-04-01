import { defineStore } from 'pinia'

function createEmptyRun(sessionId, threadId, runId = null, traceId = null) {
  return {
    session_id: sessionId,
    thread_id: threadId,
    run_id: runId,
    status: 'running',
    trace_id: traceId,
    stages: [],
    last_event_id: null,
    final_answer: '',
    updated_at: null
  }
}

function stageSort(a, b) {
  const t1 = a.started_at || ''
  const t2 = b.started_at || ''
  if (t1 < t2) return -1
  if (t1 > t2) return 1
  return a.stage_key.localeCompare(b.stage_key)
}

export const useStageStore = defineStore('stage', {
  state: () => ({
    runsByThread: {},
    seenEventIds: {}
  }),
  actions: {
    threadKey(sessionId, threadId) {
      return `${sessionId}::${threadId || sessionId}`
    },
    runFor(sessionId, threadId) {
      return this.runsByThread[this.threadKey(sessionId, threadId)] || null
    },
    upsertRun(sessionId, threadId, runId, traceId) {
      const key = this.threadKey(sessionId, threadId)
      let run = this.runsByThread[key]
      if (!run) {
        run = createEmptyRun(sessionId, threadId, runId, traceId)
      }
      if (runId) run.run_id = runId
      if (traceId) run.trace_id = traceId
      this.runsByThread[key] = run
      return run
    },
    _upsertStage(run, patch) {
      const idx = run.stages.findIndex((s) => s.stage_key === patch.stage_key)
      if (idx < 0) {
        run.stages.push({
          stage_key: patch.stage_key,
          stage_label: patch.stage_label || patch.stage_key,
          status: patch.status || 'pending',
          started_at: patch.started_at || null,
          ended_at: patch.ended_at || null,
          duration_ms: patch.duration_ms || null,
          tool_name: patch.tool_name || null,
          summary: patch.summary || '',
          error: patch.error_message || patch.error || null,
          error_code: patch.error_code || null,
          retryable: patch.retryable ?? null,
          percent: patch.percent ?? null,
          approval_payload: patch.approval_payload || null
        })
      } else {
        run.stages[idx] = {
          ...run.stages[idx],
          ...patch,
          error: patch.error_message || patch.error || run.stages[idx].error || null,
          error_code: patch.error_code || run.stages[idx].error_code || null,
          retryable: patch.retryable ?? run.stages[idx].retryable ?? null
        }
      }
      run.stages.sort(stageSort)
    },
    applyEvent(ev) {
      const eventType = ev.event_type || ev.type
      const payload = ev.payload || ev
      const sessionId = ev.session_id
      const threadId = ev.thread_id || sessionId
      if (!eventType || !sessionId) return

      if (ev.event_id) {
        if (this.seenEventIds[ev.event_id]) return
        this.seenEventIds[ev.event_id] = true
      }

      const run = this.upsertRun(sessionId, threadId, ev.run_id || null, ev.trace_id || null)
      run.updated_at = ev.server_ts || new Date().toISOString()
      if (ev.event_id) run.last_event_id = ev.event_id

      if (eventType === 'stage_started') {
        this._upsertStage(run, {
          stage_key: payload.stage_key,
          stage_label: payload.stage_label,
          status: 'running',
          started_at: payload.started_at || ev.server_ts || null
        })
      } else if (eventType === 'stage_progress') {
        this._upsertStage(run, {
          stage_key: payload.stage_key,
          summary: payload.summary,
          percent: payload.percent ?? null,
          status: 'running'
        })
      } else if (eventType === 'stage_waiting_human') {
        this._upsertStage(run, {
          stage_key: payload.stage_key,
          stage_label: payload.stage_label,
          status: 'waiting_human',
          approval_payload: payload.approval_payload || null
        })
        run.status = 'waiting_human'
      } else if (eventType === 'stage_completed') {
        this._upsertStage(run, {
          stage_key: payload.stage_key,
          status: 'completed',
          ended_at: payload.ended_at || ev.server_ts || null,
          duration_ms: payload.duration_ms ?? null,
          tool_name: payload.tool_name || null,
          summary: payload.summary || ''
        })
      } else if (eventType === 'stage_failed') {
        this._upsertStage(run, {
          stage_key: payload.stage_key,
          status: 'failed',
          error_message: payload.error_message || payload.error || '',
          error_code: payload.error_code || null,
          retryable: payload.retryable ?? null,
          summary: payload.summary || ''
        })
        run.status = 'failed'
      } else if (eventType === 'completed') {
        run.status = payload.status || 'completed'
        run.final_answer = payload.final_answer || ''
      } else if (eventType === 'error') {
        run.status = 'failed'
      }
    },
    clearSession(sessionId) {
      const keys = Object.keys(this.runsByThread)
      for (const k of keys) {
        if (k.startsWith(`${sessionId}::`)) {
          delete this.runsByThread[k]
        }
      }
    },
    setSnapshot(run) {
      if (!run || !run.session_id) return
      const sessionId = run.session_id
      const threadId = run.thread_id || sessionId
      const key = this.threadKey(sessionId, threadId)
      this.runsByThread[key] = {
        session_id: sessionId,
        thread_id: threadId,
        run_id: run.run_id || null,
        status: run.status || 'running',
        trace_id: run.trace_id || null,
        stages: Array.isArray(run.stages) ? [...run.stages] : [],
        last_event_id: run.last_event_id || null,
        final_answer: run.final_answer || '',
        updated_at: run.updated_at || null
      }
    }
  }
})

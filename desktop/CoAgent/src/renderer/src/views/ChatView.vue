<script setup>
import { computed, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth.store'
import { useSessionStore } from '../stores/session.store'
import { useUsageStore } from '../stores/usage.store'
import { chatInterrupt, chatResume, chatStream } from '../api/gateway'

const auth = useAuthStore()
const sessions = useSessionStore()
const usage = useUsageStore()

const input = ref('')
const log = ref([])
const streamingText = ref('')
const streaming = ref(false)
const sending = ref(false)
const lastResumeToken = ref(null)

const currentId = computed(() => sessions.currentId)

function pushLine(text, kind = 'info') {
  log.value = [...log.value, { t: Date.now(), kind, text }]
}

async function ensureAuthAndSessions() {
  if (!auth.isAuthed) {
    await auth.loginDev()
  }
  await sessions.refresh()
  await usage.refresh()
}

watch(
  () => auth.isAuthed,
  (v) => {
    if (v) {
      sessions.refresh()
      usage.refresh()
    }
  }
)

async function onSend() {
  const msg = input.value.trim()
  try {
    if (!msg) return
    sending.value = true
    await ensureAuthAndSessions()
    if (!sessions.currentId) {
      await sessions.createNew('S1 会话')
    }
    input.value = ''
    lastResumeToken.value = null
    streaming.value = true
    streamingText.value = ''
    let assistantBuf = ''
    pushLine(`你：${msg}`, 'user')
    await chatStream(auth.accessToken, { sessionId: sessions.currentId, message: msg }, (ev) => {
      if (ev.type === 'token' && ev.text) {
        assistantBuf += ev.text
        streamingText.value = `助手：${assistantBuf}`
      } else if (ev.type === 'checkpoint' && ev.resume_token) {
        lastResumeToken.value = ev.resume_token
        pushLine(`检查点（可恢复）：${ev.resume_token}`, 'checkpoint')
      } else if (ev.type === 'cost_event') {
        pushLine(`用量：in=${ev.input_tokens} out=${ev.output_tokens} cost≈$${ev.cost_usd}`, 'cost')
      } else if (ev.type === 'done') {
        if (assistantBuf) {
          pushLine(`助手：${assistantBuf}`, 'assistant')
        }
        streamingText.value = ''
        pushLine(`完成：${ev.status}`, 'info')
      } else if (ev.type === 'error') {
        streamingText.value = ''
        pushLine(`错误：${ev.detail ?? JSON.stringify(ev)}`, 'error')
      }
    })
  } catch (e) {
    streamingText.value = ''
    pushLine(`请求失败：${e?.message ?? e}`, 'error')
  } finally {
    sending.value = false
    streaming.value = false
    streamingText.value = ''
    usage.refresh()
  }
}

async function onStop() {
  if (!currentId.value || !auth.accessToken) return
  try {
    const r = await chatInterrupt(auth.accessToken, currentId.value)
    pushLine(`中断请求：${JSON.stringify(r)}`, 'info')
  } catch (e) {
    pushLine(`中断失败：${e?.message ?? e}`, 'error')
  }
}

async function onResume() {
  if (!lastResumeToken.value || !currentId.value) return
  await ensureAuthAndSessions()
  streaming.value = true
  streamingText.value = ''
  let assistantBuf = ''
  pushLine('恢复生成…', 'info')
  try {
    await chatResume(
      auth.accessToken,
      { sessionId: currentId.value, resumeToken: lastResumeToken.value },
      (ev) => {
        if (ev.type === 'token' && ev.text) {
          assistantBuf += ev.text
          streamingText.value = `助手：${assistantBuf}`
        } else if (ev.type === 'checkpoint' && ev.resume_token) {
          lastResumeToken.value = ev.resume_token
        } else if (ev.type === 'cost_event') {
          pushLine(`用量：in=${ev.input_tokens} out=${ev.output_tokens} cost≈$${ev.cost_usd}`, 'cost')
        } else if (ev.type === 'done') {
          if (assistantBuf) {
            pushLine(`助手：${assistantBuf}`, 'assistant')
          }
          streamingText.value = ''
          pushLine(`完成：${ev.status}`, 'info')
        } else if (ev.type === 'error') {
          streamingText.value = ''
          pushLine(`错误：${ev.detail ?? JSON.stringify(ev)}`, 'error')
        }
      }
    )
  } catch (e) {
    streamingText.value = ''
    pushLine(`恢复失败：${e?.message ?? e}`, 'error')
  } finally {
    streaming.value = false
    streamingText.value = ''
    lastResumeToken.value = null
    usage.refresh()
  }
}

async function onNewSession() {
  await ensureAuthAndSessions()
  await sessions.createNew('S1 会话')
}

function onSelect(e) {
  sessions.select(e.target.value)
}
</script>

<template>
  <div class="wrap">
    <header class="bar">
      <div class="title">Financial-CoAgent · S1</div>
      <div class="actions">
        <button v-if="!auth.isAuthed" type="button" @click="ensureAuthAndSessions">登录（开发）</button>
        <button v-else type="button" @click="auth.logout">退出</button>
        <button type="button" :disabled="!auth.isAuthed" @click="onNewSession">新会话</button>
        <button type="button" :disabled="!streaming" @click="onStop">中断流</button>
        <button type="button" :disabled="!lastResumeToken || streaming" @click="onResume">从检查点恢复</button>
      </div>
      <div v-if="usage.totals" class="usage">
        用量累计：USD {{ Number(usage.totals.cost_usd ?? 0).toFixed(6) }} · tokens
        {{ usage.totals.input_tokens ?? 0 }}/{{ usage.totals.output_tokens ?? 0 }}
      </div>
    </header>

    <div class="main">
      <aside class="side">
        <label>
          当前会话
          <select :value="currentId || ''" @change="onSelect">
            <option v-for="s in sessions.items" :key="s.id" :value="s.id">{{ s.title }} · {{ s.id.slice(0, 8) }}</option>
          </select>
        </label>
        <p v-if="sessions.error" class="err">{{ sessions.error }}</p>
      </aside>

      <section class="chat">
        <div class="stream">
          <div v-for="(line, i) in log" :key="i" :class="['line', line.kind]">{{ line.text }}</div>
          <div v-if="streamingText" class="line assistant">{{ streamingText }}</div>
        </div>
        <div class="composer">
          <textarea v-model="input" rows="3" placeholder="输入消息，回车发送" @keydown.enter.exact.prevent="onSend" />
          <button type="button" :disabled="streaming || sending" @click="onSend">{{ sending ? '发送中...' : '发送（SSE）' }}</button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; height: 100vh; font-family: system-ui, sans-serif; color: #e8eaed; background: #0f1115; }
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid #2a2f3a; background: #151821; }
.title { font-weight: 600; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.usage { margin-left: auto; font-size: 12px; opacity: 0.85; }
.main { display: grid; grid-template-columns: 260px 1fr; flex: 1; min-height: 0; }
.side { border-right: 1px solid #2a2f3a; padding: 12px; font-size: 13px; }
.side select { width: 100%; margin-top: 6px; }
.chat { display: flex; flex-direction: column; min-width: 0; }
.stream { flex: 1; overflow: auto; padding: 12px 14px; font-size: 13px; line-height: 1.45; }
.line { margin-bottom: 6px; white-space: pre-wrap; word-break: break-word; }
.line.user { color: #9bd7ff; }
.line.assistant { color: #c7f0c2; }
.line.cost { color: #ffd27a; }
.line.checkpoint { color: #b0a9ff; }
.line.error { color: #ff8b8b; }
.composer { display: flex; gap: 10px; padding: 10px 12px; border-top: 1px solid #2a2f3a; background: #151821; }
.composer textarea { flex: 1; resize: vertical; background: #0f1115; color: #e8eaed; border: 1px solid #2a2f3a; border-radius: 6px; padding: 8px; }
.err { color: #ff8b8b; margin-top: 8px; }
</style>

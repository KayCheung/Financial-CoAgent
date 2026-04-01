<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { useAuthStore } from '../stores/auth.store'
import { useSessionStore } from '../stores/session.store'
import { useUsageStore } from '../stores/usage.store'
import { useStageStore } from '../stores/stage.store'
import {
  chatInterrupt,
  chatResume,
  chatStream,
  getSessionStages,
  listSessionMessages,
  uploadAttachment
} from '../api/gateway'

const auth = useAuthStore()
const sessions = useSessionStore()
const usage = useUsageStore()
const stages = useStageStore()

const input = ref('')
const messages = ref([])
const streamingText = ref('')
const streaming = ref(false)
const sending = ref(false)
const lastResumeToken = ref(null)
const lastCost = ref(null)
const streamArea = ref(null)
const composerRef = ref(null)
const imageInputRef = ref(null)
const uploadedImages = ref([])
const loadingMoreHistory = ref(false)
const historyCursor = ref(null)
const hasMoreHistory = ref(false)
const sendState = ref('idle')
const showScrollToBottom = ref(false)

const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const leftWidth = ref(260)
const rightWidth = ref(320)
const dragState = ref(null)
const isNarrowScreen = ref(false)
const rightDrawerOpen = ref(false)
const sessionSearch = ref('')
const openSessionMenuId = ref(null)
const isDev = import.meta.env.DEV

const currentId = computed(() => sessions.currentId)
const currentRun = computed(() => {
  if (!currentId.value) return null
  return stages.runFor(currentId.value, currentId.value)
})
const filteredSessions = computed(() => {
  return sessions.items || []
})
const groupedSessions = computed(() => {
  const today = []
  const yesterday = []
  const older = []
  const now = new Date()
  const y = new Date(now)
  y.setDate(now.getDate() - 1)
  for (const s of filteredSessions.value) {
    const d = new Date(s.updated_at || s.created_at || Date.now())
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    const todayKey = `${now.getFullYear()}-${now.getMonth()}-${now.getDate()}`
    const yKey = `${y.getFullYear()}-${y.getMonth()}-${y.getDate()}`
    if (key === todayKey) today.push(s)
    else if (key === yKey) yesterday.push(s)
    else older.push(s)
  }
  return { today, yesterday, older }
})
const sessionTokenBudget = 200000
const sessionUsed = computed(() => {
  const bySession = usage.totals?.by_session || {}
  const current = currentId.value ? bySession[currentId.value] : null
  const inTokens = Number(current?.input_tokens || 0)
  const outTokens = Number(current?.output_tokens || 0)
  return { inTokens, outTokens, total: inTokens + outTokens }
})
const sessionUsedPercent = computed(() => {
  const ratio = sessionUsed.value.total / sessionTokenBudget
  return Math.max(0, Math.min(1, ratio))
})

function pushLine(text, kind = 'info') {
  messages.value = [
    ...messages.value,
    {
      id: `sys_${Date.now()}_${Math.random()}`,
      role: 'system',
      content: text,
      kind,
      isMarkdown: false,
      ts: Date.now()
    }
  ]
}

function renderMarkdown(raw) {
  const html = marked.parse(raw || '')
  return DOMPurify.sanitize(html)
}

function pushUser(text) {
  messages.value = [
    ...messages.value,
    { id: `u_${Date.now()}`, role: 'user', content: text, isMarkdown: false, ts: Date.now() }
  ]
}

function pushAssistant(text, meta = {}) {
  messages.value = [
    ...messages.value,
    {
      id: `a_${Date.now()}_${Math.random()}`,
      role: 'assistant',
      content: text,
      html: renderMarkdown(text),
      isMarkdown: true,
      ts: Date.now(),
      status: meta.status || 'completed',
      cost: meta.cost || null,
      inTokens: meta.inTokens ?? null,
      outTokens: meta.outTokens ?? null
    }
  ]
}

function scrollToBottom() {
  if (!streamArea.value) return
  requestAnimationFrame(() => {
    if (streamArea.value) streamArea.value.scrollTop = streamArea.value.scrollHeight
  })
}

function onStreamScroll() {
  const el = streamArea.value
  if (!el) return
  if (el.scrollTop <= 24) {
    loadMoreHistory()
  }
  const threshold = 32
  const hasScrollable = el.scrollHeight > el.clientHeight + 8
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight <= threshold
  showScrollToBottom.value = hasScrollable && !atBottom
}

function scrollToBottomSmooth() {
  const el = streamArea.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
}

function formatTime(ts) {
  const d = new Date(ts || Date.now())
  const now = new Date()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  if (sameDay) return `${hh}:${mm}`
  const yyyy = d.getFullYear()
  const mon = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mon}-${dd} ${hh}:${mm}`
}

function copyText(text) {
  navigator.clipboard?.writeText(text || '')
}

function retryFromAssistant(index) {
  for (let i = index - 1; i >= 0; i -= 1) {
    if (messages.value[i]?.role === 'user') {
      input.value = messages.value[i].content
      onSend()
      return
    }
  }
}

function editUserMessage(text) {
  input.value = text || ''
  requestAnimationFrame(() => {
    composerRef.value?.focus?.()
  })
}

async function retryUserMessage(text) {
  if (streaming.value || sending.value) return
  input.value = text || ''
  await onSend()
}

function openImagePicker() {
  imageInputRef.value?.click?.()
}

function onImageChange(event) {
  const files = Array.from(event?.target?.files || [])
  const mapped = files
    .filter((f) => f.type.startsWith('image/'))
    .map((f) => ({ name: f.name, size: f.size, file: f, uploading: false, uploaded: null }))
  uploadedImages.value = [...uploadedImages.value, ...mapped].slice(0, 6)
  event.target.value = ''
}

function removeImage(index) {
  uploadedImages.value = uploadedImages.value.filter((_, i) => i !== index)
}

function onPrimaryAction() {
  if (sendState.value === 'streaming') {
    onStop()
    return
  }
  onSend()
}

function startDrag(side, event) {
  dragState.value = { side, startX: event.clientX, startLeft: leftWidth.value, startRight: rightWidth.value }
  window.addEventListener('mousemove', onDrag)
  window.addEventListener('mouseup', stopDrag)
}

function onDrag(event) {
  if (!dragState.value) return
  if (dragState.value.side === 'left') {
    const delta = event.clientX - dragState.value.startX
    leftWidth.value = Math.max(180, Math.min(460, dragState.value.startLeft + delta))
  } else {
    const delta = dragState.value.startX - event.clientX
    rightWidth.value = Math.max(220, Math.min(520, dragState.value.startRight + delta))
  }
}

function stopDrag() {
  dragState.value = null
  window.removeEventListener('mousemove', onDrag)
  window.removeEventListener('mouseup', stopDrag)
}

function onResize() {
  isNarrowScreen.value = window.innerWidth <= 1024
  if (!isNarrowScreen.value) {
    rightDrawerOpen.value = false
  }
}

async function ensureAuthAndSessions() {
  if (!auth.isAuthed) {
    await auth.loginDev()
  }
  await sessions.refresh()
  await usage.refresh()
}

async function loadMessagesForSession(sessionId) {
  if (!sessionId || !auth.accessToken) return
  const data = await listSessionMessages(auth.accessToken, sessionId, { limit: 50, cursor: null })
  historyCursor.value = data.next_cursor || null
  hasMoreHistory.value = !!data.has_more
  messages.value = (data.items || []).map((m, idx) => {
    const ts = m.created_at ? new Date(m.created_at).getTime() : Date.now() + idx
    if (m.role === 'assistant') {
      return {
        id: m.id || `hist_a_${idx}_${ts}`,
        role: 'assistant',
        content: m.content,
        html: renderMarkdown(m.content),
        isMarkdown: true,
        ts,
        status: 'completed',
        cost: null,
        inTokens: m.token_usage?.input_tokens ?? null,
        outTokens: m.token_usage?.output_tokens ?? null
      }
    }
    return {
      id: m.id || `hist_${m.role}_${idx}_${ts}`,
      role: m.role,
      content: m.content,
      isMarkdown: false,
      ts,
      attachments: m.attachments || []
    }
  })
  scrollToBottom()
}

async function loadMoreHistory() {
  if (!currentId.value || !auth.accessToken || !hasMoreHistory.value || loadingMoreHistory.value) return
  loadingMoreHistory.value = true
  const beforeHeight = streamArea.value?.scrollHeight ?? 0
  try {
    const data = await listSessionMessages(auth.accessToken, currentId.value, { limit: 30, cursor: historyCursor.value })
    historyCursor.value = data.next_cursor || null
    hasMoreHistory.value = !!data.has_more
    const older = (data.items || []).map((m, idx) => {
      const ts = m.created_at ? new Date(m.created_at).getTime() : Date.now() + idx
      return {
        id: m.id || `older_${idx}_${ts}`,
        role: m.role,
        content: m.content,
        html: m.role === 'assistant' ? renderMarkdown(m.content) : null,
        isMarkdown: m.role === 'assistant',
        ts,
        attachments: m.attachments || [],
        inTokens: m.token_usage?.input_tokens ?? null,
        outTokens: m.token_usage?.output_tokens ?? null
      }
    })
    messages.value = [...older, ...messages.value]
    requestAnimationFrame(() => {
      const afterHeight = streamArea.value?.scrollHeight ?? 0
      if (streamArea.value) streamArea.value.scrollTop += afterHeight - beforeHeight
    })
  } finally {
    loadingMoreHistory.value = false
  }
}

async function loadStagesForSession(sessionId) {
  if (!sessionId || !auth.accessToken) return
  stages.clearSession(sessionId)
  const data = await getSessionStages(auth.accessToken, sessionId)
  if (data?.run) {
    stages.setSnapshot(data.run)
  }
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

let searchTimer = null
watch(
  () => sessionSearch.value,
  (v) => {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      sessions.searchQuery = (v || '').trim()
      sessions.refresh()
    }, 250)
  }
)

watch(
  () => sessions.currentId,
  async (id) => {
    if (!id) return
    try {
      await ensureAuthAndSessions()
      await loadMessagesForSession(id)
      await loadStagesForSession(id)
    } catch (e) {
      pushLine(`加载历史失败：${e?.message ?? e}`, 'error')
    }
  },
  { immediate: true }
)

async function onSend() {
  const msg = input.value.trim()
  try {
    if (!msg && uploadedImages.value.length === 0) return
    sending.value = true
    sendState.value = 'sending'
    await ensureAuthAndSessions()
    if (!sessions.currentId) {
      await sessions.createNew('S1 会话')
    }
    const uploaded = []
    for (const img of uploadedImages.value) {
      if (!img.file) continue
      img.uploading = true
      const r = await uploadAttachment(auth.accessToken, img.file)
      img.uploading = false
      img.uploaded = r
      uploaded.push(r)
    }
    const finalMsg = `${msg || '请结合我上传的图片进行分析。'}`
    input.value = ''
    lastResumeToken.value = null
    stages.clearSession(sessions.currentId)
    streaming.value = true
    sendState.value = 'streaming'
    streamingText.value = ''
    lastCost.value = null
    let assistantBuf = ''
    pushUser(finalMsg)
    uploadedImages.value = []
    await chatStream(
      auth.accessToken,
      {
        sessionId: sessions.currentId,
        message: finalMsg,
        attachments: uploaded,
        lastEventId: currentRun.value?.last_event_id || null
      },
      (ev) => {
      stages.applyEvent(ev)
      const eventType = ev.event_type || ev.type
      const payload = ev.payload || ev
      if (eventType === 'token' && payload.text) {
        assistantBuf += payload.text
        streamingText.value = assistantBuf
        scrollToBottom()
      } else if (eventType === 'checkpoint' && payload.resume_token) {
        lastResumeToken.value = payload.resume_token
        pushLine(`检查点（可恢复）：${payload.resume_token}`, 'checkpoint')
      } else if (eventType === 'cost_event') {
        const inTokens = payload.input_tokens ?? 0
        const outTokens = payload.output_tokens ?? 0
        const cost = payload.cost_usd ?? payload.total_cost ?? 0
        lastCost.value = { inTokens, outTokens, cost }
      } else if (eventType === 'done' || eventType === 'completed') {
        if (assistantBuf) {
          pushAssistant(assistantBuf, { status: payload.status ?? 'completed', ...lastCost.value })
        }
        if ((payload.status || '') === 'interrupted') {
          sendState.value = 'interrupted'
        } else {
          sendState.value = 'idle'
        }
        streamingText.value = ''
      } else if (eventType === 'error') {
        streamingText.value = ''
        pushLine(`错误：${payload.error_message ?? payload.detail ?? JSON.stringify(ev)}`, 'error')
      }
      }
    )
  } catch (e) {
    streamingText.value = ''
    pushLine(`请求失败：${e?.message ?? e}`, 'error')
  } finally {
    sending.value = false
    if (sendState.value !== 'interrupted') {
      streaming.value = false
    }
    if (sendState.value === 'streaming') {
      sendState.value = 'idle'
    }
    streamingText.value = ''
    usage.refresh()
  }
}

async function onStop() {
  if (!currentId.value || !auth.accessToken) return
  try {
    const r = await chatInterrupt(auth.accessToken, currentId.value)
    pushLine(`中断请求：${JSON.stringify(r)}`, 'info')
    sendState.value = 'interrupted'
    streaming.value = false
  } catch (e) {
    pushLine(`中断失败：${e?.message ?? e}`, 'error')
  }
}

async function onResume() {
  if (!lastResumeToken.value || !currentId.value) return
  await ensureAuthAndSessions()
  streaming.value = true
  sendState.value = 'streaming'
  streamingText.value = ''
  lastCost.value = null
  let assistantBuf = ''
  pushLine('恢复生成…', 'info')
  try {
    await chatResume(
      auth.accessToken,
      { sessionId: currentId.value, resumeToken: lastResumeToken.value },
      (ev) => {
        stages.applyEvent(ev)
        const eventType = ev.event_type || ev.type
        const payload = ev.payload || ev
        if (eventType === 'token' && payload.text) {
          assistantBuf += payload.text
          streamingText.value = assistantBuf
          scrollToBottom()
        } else if (eventType === 'checkpoint' && payload.resume_token) {
          lastResumeToken.value = payload.resume_token
        } else if (eventType === 'cost_event') {
          const inTokens = payload.input_tokens ?? 0
          const outTokens = payload.output_tokens ?? 0
          const cost = payload.cost_usd ?? payload.total_cost ?? 0
          lastCost.value = { inTokens, outTokens, cost }
        } else if (eventType === 'done' || eventType === 'completed') {
          if (assistantBuf) {
            pushAssistant(assistantBuf, { status: payload.status ?? 'completed', ...lastCost.value })
          }
          streamingText.value = ''
          sendState.value = payload.status === 'interrupted' ? 'interrupted' : 'idle'
        } else if (eventType === 'error') {
          streamingText.value = ''
          pushLine(`错误：${payload.error_message ?? payload.detail ?? JSON.stringify(ev)}`, 'error')
        }
      }
    )
  } catch (e) {
    streamingText.value = ''
    pushLine(`恢复失败：${e?.message ?? e}`, 'error')
  } finally {
    streaming.value = false
    if (sendState.value === 'streaming') sendState.value = 'idle'
    streamingText.value = ''
    lastResumeToken.value = null
    usage.refresh()
  }
}

async function onNewSession() {
  await ensureAuthAndSessions()
  await sessions.createNew('S1 会话')
}

function onSelectSession(id) {
  sessions.select(id)
}

async function onRenameSession(s) {
  const v = window.prompt('重命名会话', s.title || '')
  if (!v) return
  await sessions.rename(s.id, v)
}

async function onDeleteSession(s) {
  if (!window.confirm(`删除会话「${s.title}」？`)) return
  await sessions.remove(s.id)
}

async function onTogglePinSession(s) {
  await sessions.togglePin(s.id, !s.pinned)
}

function toggleSessionMenu(id) {
  openSessionMenuId.value = openSessionMenuId.value === id ? null : id
}

function closeSessionMenuOnOutsideClick(event) {
  const target = event?.target
  if (!(target instanceof Element)) return
  if (target.closest('.recent-menu') || target.closest('.recent-menu-trigger')) return
  openSessionMenuId.value = null
}

onBeforeUnmount(() => {
  stopDrag()
  window.removeEventListener('resize', onResize)
  document.removeEventListener('click', closeSessionMenuOnOutsideClick)
  streamArea.value?.removeEventListener?.('scroll', onStreamScroll)
})

onResize()
window.addEventListener('resize', onResize)
onMounted(() => {
  document.addEventListener('click', closeSessionMenuOnOutsideClick)
})
watch(
  () => streamArea.value,
  (el, oldEl) => {
    oldEl?.removeEventListener?.('scroll', onStreamScroll)
    el?.addEventListener?.('scroll', onStreamScroll, { passive: true })
    requestAnimationFrame(onStreamScroll)
  },
  { immediate: true }
)
watch(
  () => messages.value.length,
  () => requestAnimationFrame(onStreamScroll)
)
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
        <button type="button" @click="leftCollapsed = !leftCollapsed">{{ leftCollapsed ? '打开左栏' : '收起左栏' }}</button>
        <button type="button" @click="rightCollapsed = !rightCollapsed">{{ rightCollapsed ? '打开右栏' : '收起右栏' }}</button>
        <button v-if="isNarrowScreen && !rightCollapsed" type="button" @click="rightDrawerOpen = !rightDrawerOpen">
          {{ rightDrawerOpen ? '关闭阶段栏' : '打开阶段栏' }}
        </button>
      </div>
      <div v-if="usage.totals" class="usage">
        用量累计：USD {{ Number(usage.totals.cost_usd ?? 0).toFixed(6) }} · tokens
        {{ usage.totals.input_tokens ?? 0 }}/{{ usage.totals.output_tokens ?? 0 }}
      </div>
    </header>

    <div class="main">
      <aside v-if="!leftCollapsed" class="side" :style="{ width: `${leftWidth}px` }">
        <div class="brand">Financial-CoAgent</div>
        <div class="side-tools">
          <button type="button" class="tool-item" :disabled="!auth.isAuthed" @click="onNewSession">
            <span class="tool-icon">＋</span>
            <span>New chat</span>
          </button>
          <div class="tool-search">
            <span class="tool-icon">⌕</span>
            <input v-model="sessionSearch" class="search-input" placeholder="Search" />
            <span class="search-hotkey">Ctrl+K</span>
          </div>
        </div>
        <div class="side-divider" />
        <div class="recent-title">Recents</div>
        <div class="recent-list">
          <div class="recent-group-title">Today</div>
          <button v-for="s in groupedSessions.today" :key="s.id" type="button" :class="['recent-item', { active: currentId === s.id }]" @click="onSelectSession(s.id)">
            <div class="recent-main">{{ s.pinned ? '📌 ' : '' }}{{ s.title || '未命名会话' }}</div>
            <div v-if="isDev" class="recent-sub">{{ s.id.slice(0, 8) }}</div>
            <button type="button" class="recent-menu-trigger" @click.stop="toggleSessionMenu(s.id)" title="更多">⋯</button>
            <div v-if="openSessionMenuId === s.id" class="recent-menu">
              <button type="button" class="recent-action" @click.stop="onRenameSession(s)">重命名</button>
              <button type="button" class="recent-action" @click.stop="onTogglePinSession(s)">{{ s.pinned ? '取消置顶' : '置顶' }}</button>
              <button type="button" class="recent-action danger" @click.stop="onDeleteSession(s)">删除</button>
            </div>
          </button>
          <div class="recent-group-title">Yesterday</div>
          <button v-for="s in groupedSessions.yesterday" :key="s.id" type="button" :class="['recent-item', { active: currentId === s.id }]" @click="onSelectSession(s.id)">
            <div class="recent-main">{{ s.pinned ? '📌 ' : '' }}{{ s.title || '未命名会话' }}</div>
            <div v-if="isDev" class="recent-sub">{{ s.id.slice(0, 8) }}</div>
            <button type="button" class="recent-menu-trigger" @click.stop="toggleSessionMenu(s.id)" title="更多">⋯</button>
            <div v-if="openSessionMenuId === s.id" class="recent-menu">
              <button type="button" class="recent-action" @click.stop="onRenameSession(s)">重命名</button>
              <button type="button" class="recent-action" @click.stop="onTogglePinSession(s)">{{ s.pinned ? '取消置顶' : '置顶' }}</button>
              <button type="button" class="recent-action danger" @click.stop="onDeleteSession(s)">删除</button>
            </div>
          </button>
          <div class="recent-group-title">Older</div>
          <button v-for="s in groupedSessions.older" :key="s.id" type="button" :class="['recent-item', { active: currentId === s.id }]" @click="onSelectSession(s.id)">
            <div class="recent-main">{{ s.pinned ? '📌 ' : '' }}{{ s.title || '未命名会话' }}</div>
            <div v-if="isDev" class="recent-sub">{{ s.id.slice(0, 8) }}</div>
            <button type="button" class="recent-menu-trigger" @click.stop="toggleSessionMenu(s.id)" title="更多">⋯</button>
            <div v-if="openSessionMenuId === s.id" class="recent-menu">
              <button type="button" class="recent-action" @click.stop="onRenameSession(s)">重命名</button>
              <button type="button" class="recent-action" @click.stop="onTogglePinSession(s)">{{ s.pinned ? '取消置顶' : '置顶' }}</button>
              <button type="button" class="recent-action danger" @click.stop="onDeleteSession(s)">删除</button>
            </div>
          </button>
          <div v-if="!filteredSessions.length" class="recent-empty">暂无会话</div>
        </div>
        <p v-if="sessions.error" class="err">{{ sessions.error }}</p>
      </aside>
      <div v-if="!leftCollapsed" class="splitter" @mousedown="startDrag('left', $event)" />

      <section class="chat">
        <div ref="streamArea" class="stream">
          <div v-for="(m, i) in messages" :key="m.id" :class="['msg', m.role, m.kind || '']">
            <div v-if="m.role === 'assistant'" class="bubble assistant">
              <div class="md" v-html="m.html"></div>
              <div class="meta-icons minimal">
                <button type="button" class="icon-btn" title="复制" @click="copyText(m.content)">⧉</button>
                <button type="button" class="icon-btn" title="重试" @click="retryFromAssistant(i)">↻</button>
                <span v-if="m.inTokens != null || m.outTokens != null" class="meta-tail token-inline">
                  in {{ m.inTokens ?? 0 }} / out {{ m.outTokens ?? 0 }}
                </span>
                <span class="meta-tail" title="完成状态">已完成</span>
                <span v-if="m.cost != null" class="meta-tail" title="用量">
                  ${{ Number(m.cost).toFixed(6) }}
                </span>
              </div>
            </div>
            <div v-else-if="m.role === 'user'" class="user-wrap">
              <div class="bubble user">
                <div>{{ m.content }}</div>
              </div>
              <div class="meta-icons user-tools">
                <span class="meta-tail user-time">{{ formatTime(m.ts) }}</span>
                <button type="button" class="icon-btn" title="复制" @click="copyText(m.content)">⧉</button>
                <button type="button" class="icon-btn" title="编辑" @click="editUserMessage(m.content)">✎</button>
                <button type="button" class="icon-btn" title="重试" @click="retryUserMessage(m.content)">↻</button>
              </div>
            </div>
            <div v-else class="bubble">{{ m.content }}</div>
          </div>
          <div v-if="streamingText" class="msg assistant streaming">
            <div class="bubble assistant">
              <div class="md" v-html="renderMarkdown(streamingText)"></div>
            </div>
          </div>
        </div>
        <button v-if="showScrollToBottom" type="button" class="scroll-bottom-btn" @click="scrollToBottomSmooth" title="回到底部">
          ↓
        </button>
        <div class="composer">
          <input ref="imageInputRef" type="file" accept="image/*" multiple class="file-hidden" @change="onImageChange" />
          <div v-if="uploadedImages.length" class="upload-list">
            <div v-for="(img, idx) in uploadedImages" :key="`${img.name}_${idx}`" class="upload-chip">
              <span>{{ img.name }}</span>
              <button type="button" @click="removeImage(idx)">×</button>
            </div>
          </div>
          <textarea
            ref="composerRef"
            v-model="input"
            rows="3"
            placeholder="给 Financial-CoAgent 发送消息..."
            @keydown.enter.exact.prevent="onSend"
          />
          <div class="composer-footer right-only">
            <div class="composer-right">
              <button type="button" class="subtle-btn" @click="openImagePicker">图片上传</button>
              <div class="used-ring-wrap" :title="`used ${sessionUsed.total}/${sessionTokenBudget}`">
                <div class="used-ring" :style="{ '--used': `${sessionUsedPercent}` }">
                  <span>{{ Math.round(sessionUsedPercent * 100) }}%</span>
                </div>
                <div class="used-text">used {{ sessionUsed.total }}</div>
              </div>
              <span class="used tiny">in {{ sessionUsed.inTokens }} / out {{ sessionUsed.outTokens }}</span>
            </div>
            <button
              type="button"
              :class="['send-btn', sendState]"
              :disabled="sendState === 'sending'"
              @click="onPrimaryAction"
              :title="sendState === 'streaming' ? '处理中，点击中断' : sendState === 'sending' ? '发送中' : sendState === 'interrupted' ? '已中断，可重发' : '发送'"
            >
              <span v-if="sendState === 'streaming'" class="stop-square" />
              <span v-else-if="sendState === 'interrupted'">!</span>
              <span v-else>↑</span>
            </button>
          </div>
        </div>
      </section>
      <div v-if="!rightCollapsed && !isNarrowScreen" class="splitter" @mousedown="startDrag('right', $event)" />
      <aside
        v-if="!rightCollapsed"
        :class="['stage-panel', { drawer: isNarrowScreen, open: rightDrawerOpen }]"
        :style="{ width: `${rightWidth}px` }"
      >
        <div class="stage-head">
          <strong>执行阶段</strong>
          <span v-if="currentRun">状态：{{ currentRun.status }}</span>
        </div>
        <div v-if="currentRun?.trace_id" class="trace">trace: {{ currentRun.trace_id }}</div>
        <div v-if="!currentRun || !currentRun.stages.length" class="empty">暂无阶段事件</div>
        <div v-else class="stage-list">
          <div v-for="s in currentRun.stages" :key="s.stage_key" class="stage-item">
            <div class="stage-title">
              <span>{{ s.stage_label || s.stage_key }}</span>
              <span :class="['badge', s.status]">{{ s.status }}</span>
            </div>
            <div v-if="s.summary" class="stage-summary">{{ s.summary }}</div>
            <div v-if="s.duration_ms" class="stage-summary">耗时: {{ s.duration_ms }}ms</div>
            <div v-if="s.error" class="stage-error">{{ s.error }}</div>
            <div v-if="s.error_code" class="stage-error">错误码: {{ s.error_code }}</div>
            <div v-if="s.approval_payload?.question" class="stage-approval">
              等待确认：{{ s.approval_payload.question }}
            </div>
            <div class="recent-actions">
              <button v-if="s.retryable || s.status === 'failed'" type="button" class="recent-action" @click="onResume">重试</button>
              <button v-if="currentRun?.trace_id" type="button" class="recent-action" @click="copyText(currentRun.trace_id)">复制 trace</button>
            </div>
          </div>
        </div>
      </aside>
      <div v-if="!rightCollapsed && isNarrowScreen && rightDrawerOpen" class="drawer-mask" @click="rightDrawerOpen = false" />
    </div>
  </div>
</template>

<style scoped>
.wrap { display: flex; flex-direction: column; height: 100vh; font-family: system-ui, sans-serif; color: #e8eaed; background: #0f1115; }
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid #2a2f3a; background: #151821; }
.title { font-weight: 600; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.usage { margin-left: auto; font-size: 12px; opacity: 0.85; }
.main { display: flex; flex: 1; min-height: 0; }
.side { border-right: 1px solid #2a2f3a; padding: 10px 10px 12px; font-size: 13px; flex: 0 0 auto; min-width: 180px; max-width: 460px; overflow: auto; background: #11151d; color: #d1d5db; }
.brand { font-size: 24px; line-height: 1.1; margin: 2px 4px 10px; font-family: system-ui, -apple-system, sans-serif; color: #f3f4f6; font-weight: 700; }
.side-tools { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
.tool-item { border: 1px solid transparent; background: transparent; color: #e5e7eb; border-radius: 10px; padding: 8px 10px; text-align: left; cursor: pointer; display: flex; align-items: center; gap: 8px; }
.tool-item:hover { background: #1a2331; }
.tool-search { border: 1px solid #2f3642; background: #0f1724; color: #e5e7eb; border-radius: 10px; padding: 8px 10px; display: flex; align-items: center; gap: 8px; }
.tool-icon { font-size: 14px; opacity: 0.9; min-width: 16px; text-align: center; }
.search-input { width: 100%; background: transparent; color: #e5e7eb; border: none; outline: none; font-size: 14px; }
.search-hotkey { font-size: 11px; color: #9ca3af; white-space: nowrap; }
.side-divider { height: 1px; background: #2a2f3a; margin: 6px 2px 10px; }
.recent-title { font-size: 12px; color: #9ca3af; margin: 10px 0 8px; }
.recent-list { display: flex; flex-direction: column; gap: 6px; }
.recent-group-title { font-size: 11px; color: #94a3b8; margin: 8px 0 2px; }
.recent-item { border: 1px solid transparent; background: transparent; color: #d1d5db; border-radius: 8px; padding: 8px; text-align: left; cursor: pointer; }
.recent-item { position: relative; }
.recent-item:hover { background: #1a2331; }
.recent-item.active { background: #1d4ed8; border-color: #2563eb; color: #eff6ff; }
.recent-main { font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.recent-sub { font-size: 11px; color: #94a3b8; margin-top: 2px; }
.recent-actions { display: flex; gap: 4px; margin-top: 6px; }
.recent-action { border: 1px solid #334155; background: transparent; color: #cbd5e1; border-radius: 999px; font-size: 10px; padding: 1px 6px; }
.recent-action.danger { color: #fca5a5; border-color: #7f1d1d; }
.recent-menu-trigger {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 20px;
  height: 20px;
  padding: 0;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 700;
  line-height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-family: "Segoe UI", sans-serif;
  opacity: 0;
  pointer-events: none;
}
.recent-item:hover .recent-menu-trigger,
.recent-item.active .recent-menu-trigger,
.recent-menu-trigger:focus-visible {
  opacity: 1;
  pointer-events: auto;
}
.recent-menu-trigger:hover {
  background: #1f2937;
  color: #e2e8f0;
}
.recent-menu {
  position: absolute;
  top: 30px;
  right: 8px;
  z-index: 5;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px;
  border: 1px solid #334155;
  border-radius: 8px;
  background: #0f172a;
}
.recent-empty { font-size: 12px; color: #6b7280; padding: 6px 2px; }
.chat { display: flex; flex-direction: column; min-width: 0; flex: 1; position: relative; }
.stream { flex: 1; overflow: auto; padding: 12px 14px; font-size: 13px; line-height: 1.45; }
.msg { margin-bottom: 10px; display: flex; }
.msg.user { justify-content: flex-end; }
.msg.assistant, .msg.system { justify-content: flex-start; }
.user-wrap { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; max-width: min(82%, 920px); width: fit-content; }
.bubble { max-width: 82%; padding: 2px 0; white-space: pre-wrap; overflow-wrap: break-word; word-break: normal; background: transparent; border: none; border-radius: 0; }
.msg.user .bubble { color: #dbe1ea; background: #2a2f3a; border: 1px solid #3a4150; border-radius: 10px; padding: 8px 12px; max-width: 100%; }
.msg.system .bubble { color: #fecaca; }
.bubble.assistant {
  color: #d1fae5;
  font-size: 12px;
  line-height: 1.28;
}
.bubble.assistant .md :deep(p) { margin: 0 0 2px; }
.md :deep(p) { margin: 0 0 8px; }
.bubble.assistant .md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(p:last-child) { margin-bottom: 0; }
.bubble.assistant .md :deep(pre) { padding: 6px 8px; font-size: 11px; line-height: 1.35; }
.md :deep(pre) { background: #0f1115; padding: 8px; border-radius: 6px; overflow: auto; }
.bubble.assistant .md :deep(ul),
.bubble.assistant .md :deep(ol) { margin: 0 0 3px; padding-left: 1.15em; }
.bubble.assistant .md :deep(li) { margin: 0 0 1px; }
.meta-icons { margin-top: 8px; display: flex; align-items: center; gap: 8px; font-size: 11px; opacity: 0.9; }
.meta-icons.minimal { gap: 6px; }
.icon-btn { background: transparent; border: 1px solid #2f3642; color: #cbd5e1; border-radius: 999px; cursor: pointer; font-size: 12px; line-height: 1; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; }
.icon-btn:hover { border-color: #4b5563; color: #f3f4f6; }
.meta-tail { color: #9ca3af; font-size: 11px; }
.token-inline { opacity: 0.9; }
.user-tools { opacity: 0; pointer-events: none; transition: opacity 160ms ease; margin-right: 2px; }
.msg.user:hover .user-tools { opacity: 1; pointer-events: auto; }
.composer { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border-top: 1px solid #2a2f3a; background: #151821; }
.composer textarea { width: 100%; resize: none; background: #0f1115; color: #e8eaed; border: 1px solid #2a2f3a; border-radius: 10px; padding: 10px 12px; min-height: 88px; }
.composer-footer { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.composer-footer.right-only { justify-content: flex-end; }
.composer-right { display: flex; align-items: center; gap: 10px; min-width: 0; }
.subtle-btn { background: transparent; border: 1px solid #374151; color: #cbd5e1; border-radius: 999px; padding: 4px 10px; cursor: pointer; font-size: 12px; }
.subtle-btn:hover { border-color: #4b5563; color: #f3f4f6; }
.used { font-size: 12px; color: #9ca3af; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.used.tiny { font-size: 11px; }
.used-ring-wrap { display: inline-flex; align-items: center; gap: 8px; }
.used-ring {
  --used: 0;
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: conic-gradient(#60a5fa calc(var(--used) * 360deg), #374151 0deg);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
}
.used-ring::after {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  border-radius: 999px;
  background: #151821;
}
.used-ring span {
  position: relative;
  z-index: 1;
  font-size: 9px;
  color: #cbd5e1;
}
.used-text { font-size: 11px; color: #9ca3af; }
.send-btn { width: 30px; height: 30px; border-radius: 999px; border: 1px solid #3b82f6; background: #2563eb; color: #eff6ff; font-size: 16px; line-height: 1; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; transition: all 120ms ease; }
.send-btn.running { background: #334155; border-color: #64748b; }
.send-btn.sending { opacity: 0.7; }
.send-btn.streaming { background: #334155; border-color: #64748b; }
.send-btn.interrupted { background: #92400e; border-color: #d97706; }
.stop-square { width: 11px; height: 11px; background: #e5e7eb; border-radius: 2px; display: inline-block; }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.file-hidden { display: none; }
.upload-list { display: flex; flex-wrap: wrap; gap: 6px; }
.upload-chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; border: 1px solid #374151; border-radius: 999px; padding: 2px 8px; color: #cbd5e1; }
.upload-chip button { border: none; background: transparent; color: #9ca3af; cursor: pointer; }
.scroll-bottom-btn {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  bottom: 152px;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  border: 1px solid #475569;
  background: rgba(15, 23, 42, 0.92);
  color: #e2e8f0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);
  z-index: 8;
}
.scroll-bottom-btn:hover {
  border-color: #60a5fa;
  color: #bfdbfe;
}
.err { color: #ff8b8b; margin-top: 8px; }
.stage-panel { border-left: 1px solid #2a2f3a; padding: 12px; font-size: 12px; overflow: auto; flex: 0 0 auto; min-width: 220px; max-width: 520px; }
.stage-head { display: flex; justify-content: space-between; margin-bottom: 8px; }
.trace { font-size: 11px; opacity: 0.7; margin-bottom: 10px; word-break: break-all; }
.empty { opacity: 0.7; }
.stage-list { display: flex; flex-direction: column; gap: 8px; }
.stage-item { border: 1px solid #2a2f3a; border-radius: 8px; padding: 8px; background: #141821; }
.stage-title { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.badge { border-radius: 999px; padding: 0 8px; font-size: 11px; line-height: 18px; text-transform: lowercase; }
.badge.running { background: #1d4ed8; color: #dbeafe; }
.badge.completed { background: #065f46; color: #d1fae5; }
.badge.waiting_human { background: #92400e; color: #fef3c7; }
.badge.failed { background: #991b1b; color: #fee2e2; }
.badge.pending { background: #374151; color: #e5e7eb; }
.stage-summary { color: #d1d5db; white-space: pre-wrap; }
.stage-error { color: #fca5a5; margin-top: 4px; white-space: pre-wrap; }
.stage-approval { margin-top: 4px; color: #fde68a; white-space: pre-wrap; }
.splitter { width: 6px; cursor: col-resize; background: #111827; border-left: 1px solid #1f2937; border-right: 1px solid #1f2937; }
.splitter:hover { background: #1f2937; }
.drawer-mask { display: none; }

.stream::-webkit-scrollbar,
.stage-panel::-webkit-scrollbar,
.side::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}
.stream::-webkit-scrollbar-track,
.stage-panel::-webkit-scrollbar-track,
.side::-webkit-scrollbar-track {
  background: transparent;
}
.stream::-webkit-scrollbar-thumb,
.stage-panel::-webkit-scrollbar-thumb,
.side::-webkit-scrollbar-thumb {
  background: #374151;
  border-radius: 999px;
  border: 2px solid transparent;
  background-clip: content-box;
}
.stream::-webkit-scrollbar-thumb:hover,
.stage-panel::-webkit-scrollbar-thumb:hover,
.side::-webkit-scrollbar-thumb:hover {
  background: #4b5563;
  background-clip: content-box;
}

@media (max-width: 1280px) {
  .side { width: 220px !important; }
  .stage-panel { width: 280px !important; }
}

@media (max-width: 1024px) {
  .stage-panel.drawer {
    position: fixed;
    right: 0;
    top: 0;
    height: 100vh;
    z-index: 50;
    background: #0f1115;
    box-shadow: -10px 0 24px rgba(0, 0, 0, 0.35);
    transform: translateX(100%);
    transition: transform 220ms ease;
  }
  .stage-panel.drawer.open {
    transform: translateX(0);
  }
  .drawer-mask {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.35);
    z-index: 40;
  }
}

@media (max-width: 768px) {
  .side { display: none; }
  .splitter:first-of-type { display: none; }
  .bubble { max-width: 92%; }
}
</style>

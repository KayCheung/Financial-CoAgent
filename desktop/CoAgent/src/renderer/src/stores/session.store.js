import { defineStore } from 'pinia'
import { createSession, deleteSession, listSessions, updateSession } from '../api/gateway'
import { useAuthStore } from './auth.store'

export const useSessionStore = defineStore('session', {
  state: () => ({
    items: [],
    total: 0,
    currentId: null,
    searchQuery: '',
    loading: false,
    error: null
  }),
  actions: {
    async refresh() {
      const auth = useAuthStore()
      if (!auth.accessToken) return
      this.loading = true
      this.error = null
      try {
        const data = await listSessions(auth.accessToken, { q: this.searchQuery || '' })
        this.items = data.items ?? []
        this.total = data.total ?? 0
        if (!this.currentId && this.items.length) {
          this.currentId = this.items[0].id
        }
      } catch (e) {
        this.error = e?.message ?? String(e)
      } finally {
        this.loading = false
      }
    },
    async createNew(title) {
      const auth = useAuthStore()
      if (!auth.accessToken) return null
      this.error = null
      const row = await createSession(auth.accessToken, { title: title || '新会话' })
      this.items = [row, ...this.items.filter((x) => x.id !== row.id)]
      this.total = this.items.length
      this.currentId = row.id
      return row
    },
    select(id) {
      this.currentId = id
    },
    async rename(id, title) {
      const auth = useAuthStore()
      if (!auth.accessToken) return
      await updateSession(auth.accessToken, id, { title })
      await this.refresh()
    },
    async togglePin(id, pinned) {
      const auth = useAuthStore()
      if (!auth.accessToken) return
      await updateSession(auth.accessToken, id, { pinned })
      await this.refresh()
    },
    async remove(id) {
      const auth = useAuthStore()
      if (!auth.accessToken) return
      await deleteSession(auth.accessToken, id)
      if (this.currentId === id) {
        this.currentId = null
      }
      await this.refresh()
    }
  }
})

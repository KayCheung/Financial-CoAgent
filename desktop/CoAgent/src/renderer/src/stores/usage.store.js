import { defineStore } from 'pinia'
import { usageSummary } from '../api/gateway'
import { useAuthStore } from './auth.store'

export const useUsageStore = defineStore('usage', {
  state: () => ({
    totals: null,
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
        const data = await usageSummary(auth.accessToken)
        this.totals = data.totals ?? null
      } catch (e) {
        this.error = e?.message ?? String(e)
      } finally {
        this.loading = false
      }
    }
  }
})

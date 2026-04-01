import { defineStore } from 'pinia'
import { devLogin } from '../api/gateway'

const STORAGE_KEY = 'coagent_access_token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    accessToken: typeof sessionStorage !== 'undefined' ? sessionStorage.getItem(STORAGE_KEY) : null,
    error: null
  }),
  getters: {
    isAuthed: (s) => Boolean(s.accessToken)
  },
  actions: {
    async loginDev() {
      this.error = null
      try {
        const data = await devLogin()
        this.accessToken = data.access_token
        sessionStorage.setItem(STORAGE_KEY, this.accessToken)
      } catch (e) {
        this.error = e?.message ?? String(e)
        throw e
      }
    },
    logout() {
      this.accessToken = null
      sessionStorage.removeItem(STORAGE_KEY)
    }
  }
})

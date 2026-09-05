import { defineStore } from 'pinia'

export const useAppStore = defineStore('app', {
  state: () => ({
    message: 'Kombain Store',
  }),
  actions: {
    setMessage(newMessage: string) {
      this.message = newMessage
    },
  },
})

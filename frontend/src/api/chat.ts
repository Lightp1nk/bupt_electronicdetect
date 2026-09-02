import { request } from './client'
import type { ChatBindingCode, ChatIdentity } from '@/types/api'

export const getChatIdentity = () => request<ChatIdentity | null>('/chat/identity?platform=qq')
export const createChatBindingCode = () => request<ChatBindingCode>('/chat/identity/binding-code?platform=qq', { method: 'POST' })
export const deleteChatIdentity = () => request<void>('/chat/identity/qq', { method: 'DELETE' })

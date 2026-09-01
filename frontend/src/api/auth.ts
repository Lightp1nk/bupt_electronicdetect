import { request } from './client'
import type { SessionStatus } from '@/types/api'

export const login = (username: string, password: string) => request<SessionStatus>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
export const getStatus = () => request<SessionStatus>('/auth/status')
export const logout = () => request<SessionStatus>('/auth/logout', { method: 'POST' })

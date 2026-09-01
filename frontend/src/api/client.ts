import type { ApiResponse } from '@/types/api'

export class ApiError extends Error {
  constructor(public readonly code: string, message: string) { super(message) }
}

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${baseUrl}${path}`, { headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) }, ...init })
  } catch {
    throw new ApiError('NETWORK_ERROR', '无法连接本地服务，请确认后端已启动。')
  }
  let body: ApiResponse<T>
  try { body = await response.json() as ApiResponse<T> } catch { throw new ApiError('PARSE_ERROR', '服务返回了无法识别的数据。') }
  if (!response.ok || !body.success || body.data === null) throw new ApiError(body.code, body.message || '请求未完成。')
  return body.data
}

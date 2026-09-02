import { request } from './client'
import type { AlertEvent, AlertSettings, Building, CollectionState, ElectricityAnalysis, ElectricityRecord, Floor, NotificationBinding, NotificationStatus, QuerySaveResult, Room } from '@/types/api'

export type DashboardDataSource = 'real' | 'demo'

const params = (values: Record<string, string | number | undefined>) => `?${new URLSearchParams(Object.entries(values).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString()}`
export const getBuildings = (areaId: string) => request<Building[]>(`/electricity/buildings${params({ area_id: areaId })}`)
export const getFloors = (areaId: string, buildingId: string) => request<Floor[]>(`/electricity/floors${params({ area_id: areaId, building_id: buildingId })}`)
export const getRooms = (areaId: string, buildingId: string, floorId: string) => request<Room[]>(`/electricity/rooms${params({ area_id: areaId, building_id: buildingId, floor_id: floorId })}`)
export const queryElectricity = (payload: { area_id: string; building_id: string; floor_id: string; room_id: string; room_name?: string }) => request<QuerySaveResult>('/electricity/query', { method: 'POST', body: JSON.stringify(payload) })
export const getHistory = (areaId: string, roomId: string, limit = 90, source: DashboardDataSource = 'real') => request<ElectricityRecord[]>(`/electricity/history/${encodeURIComponent(roomId)}${params({ area_id: areaId, limit, source })}`)
export const getLatest = (areaId: string, roomId: string, source: DashboardDataSource = 'real') => request<ElectricityRecord>(`/electricity/latest/${encodeURIComponent(roomId)}${params({ area_id: areaId, source })}`)
export const getAnalysis = (areaId: string, roomId: string, source: DashboardDataSource = 'real') => request<ElectricityAnalysis>(`/electricity/analysis/${encodeURIComponent(roomId)}${params({ area_id: areaId, source })}`)
export const getCollectionSettings = () => request<CollectionState>('/electricity/collection/settings')
export const saveCollectionSettings = (payload: { area_id: string; area_name: string; building_id: string; building_name: string; floor_id: string; floor_name: string; room_id: string; room_name: string }) => request<CollectionState>('/electricity/collection/settings', { method: 'PUT', body: JSON.stringify(payload) })
export const clearCollectionSettings = () => request<CollectionState>('/electricity/collection/settings', { method: 'DELETE' })
export const runCollection = () => request<CollectionState>('/electricity/collection/run', { method: 'POST' })
export const getActiveAlerts = (areaId:string, roomId:string) => request<AlertEvent[]>(`/electricity/alerts/active${params({area_id:areaId,room_id:roomId})}`)
export const getAlertSettings = () => request<AlertSettings>('/electricity/alerts/settings')
export const saveAlertSettings = (payload: AlertSettings) => request<AlertSettings>('/electricity/alerts/settings', { method:'PUT', body:JSON.stringify(payload) })
export const getNotificationBindings = () => request<NotificationBinding[]>('/notification/bindings')
export const getNotificationStatus = () => request<NotificationStatus>('/notification/status')
export const setAstrBotNotificationEnabled = (enabled:boolean) => request<NotificationBinding>('/notification/bindings/astrbot/qq/enabled',{method:'PUT',body:JSON.stringify({ enabled })})

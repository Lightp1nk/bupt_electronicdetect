export type ErrorCode =
  | 'OK' | 'INVALID_ARGUMENT' | 'AUTH_REQUIRED' | 'AUTH_FAILED' | 'SESSION_EXPIRED'
  | 'NETWORK_ERROR' | 'TIMEOUT' | 'UPSTREAM_ERROR' | 'PARSE_ERROR' | 'NOT_FOUND'
  | 'BUSINESS_ERROR' | 'DATABASE_ERROR' | 'INTERNAL_ERROR'

export interface ApiResponse<T> {
  success: boolean
  code: ErrorCode
  message: string
  data: T | null
}

export interface SessionStatus { authenticated: boolean; state: 'AUTHENTICATED' | 'UNAUTHENTICATED' | 'SESSION_EXPIRED' }
export interface Building { id: string; name: string; area_id: string }
export interface Floor { id: string; name: string; building_id: string; area_id: string }
export interface Room { id: string; name: string; floor_id: string; building_id: string; area_id: string }

export interface ElectricityReading {
  area_id: string; building_id: string; building_name: string | null; floor_id: string; floor_name: string | null
  room_id: string; room_name: string | null; source_time: string | null; remaining_money: number | null
  remaining_kwh: number | null; remaining_energy_kwh: number | null; total_usage_kwh: number | null
  free_remaining_kwh: number | null; price_per_kwh: number | null; raw_data: Record<string, unknown>
}

export interface ElectricityRecord {
  id: number; area_id: string; building_id: string; building_name: string | null; floor_id: string; floor_name: string | null
  room_id: string; room_name: string | null; remaining_money: number | null; remaining_kwh: number | null
  remaining_energy_kwh: number | null; free_remaining_kwh: number | null; total_usage_kwh: number | null
  price_per_kwh: number | null; source_time: string | null; query_time: string; created_at: string; raw_data_json: Record<string, unknown>
}

export interface QuerySaveResult { reading: ElectricityReading; record: ElectricityRecord; saved: boolean; duplicate: boolean }
export type PredictionMaturity = 'insufficient' | 'preliminary' | 'stable'
export interface DailyUsage { date: string; usage_kwh: number }
export interface ElectricityAnalysis {
  area_id: string; room_id: string
  current: { remaining_money: number | null; remaining_kwh: number | null; remaining_energy_kwh: number | null; total_usage_kwh: number | null; source_time: string | null }
  statistics: { valid_daily_count: number; avg_3d_kwh: number | null; avg_7d_kwh: number | null }
  prediction: { estimated_remaining_days: number | null; average_daily_usage_kwh: number | null; window_days: number | null; maturity: PredictionMaturity }
  daily_usage: DailyUsage[]
}
export type CollectionStatus = 'never_run' | 'success' | 'no_room_configured' | 'not_authenticated' | 'session_expired' | 'upstream_not_updated' | 'failed' | 'already_running'
export interface CollectionState {
  enabled: boolean; scheduled_time: string; authenticated: boolean
  area_id: string | null; building_id: string | null; building_name: string | null
  floor_id: string | null; floor_name: string | null; room_id: string | null; room_name: string | null
  status: CollectionStatus; message: string | null
  last_attempt_time: string | null; last_success_time: string | null; last_source_time: string | null
}

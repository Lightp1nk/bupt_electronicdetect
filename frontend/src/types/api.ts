export type ErrorCode =
  | 'OK' | 'INVALID_ARGUMENT' | 'AUTH_REQUIRED' | 'AUTH_FAILED' | 'SESSION_EXPIRED' | 'REAUTH_REQUIRED'
  | 'NETWORK_ERROR' | 'TIMEOUT' | 'UPSTREAM_ERROR' | 'PARSE_ERROR' | 'NOT_FOUND'
  | 'BUSINESS_ERROR' | 'DATABASE_ERROR' | 'INTERNAL_ERROR'

export interface ApiResponse<T> {
  success: boolean
  code: ErrorCode
  message: string
  data: T | null
}

export interface CurrentUser { id: number; bupt_username: string; display_name: string | null }
export type UpstreamSessionStatus = 'UNKNOWN' | 'ACTIVE' | 'EXPIRED' | 'REAUTH_REQUIRED'
export interface SessionStatus { authenticated: boolean; state: 'AUTHENTICATED' | 'UNAUTHENTICATED' | 'SESSION_EXPIRED'; user: CurrentUser | null; upstream_status: UpstreamSessionStatus | null }
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
  area_id: string | null; area_name: string | null; building_id: string | null; building_name: string | null
  floor_id: string | null; floor_name: string | null; room_id: string | null; room_name: string | null
  status: CollectionStatus; message: string | null
  last_attempt_time: string | null; last_success_time: string | null; last_source_time: string | null
}
export type AlertType = 'low_balance' | 'low_remaining_days'; export type AlertLevel = 'warning' | 'critical'; export type AlertEventStatus = 'active' | 'resolved'
export interface AlertEvent { id:number; area_id:string; room_id:string; building_name:string|null; floor_name:string|null; room_name:string|null; alert_type:AlertType; level:AlertLevel; status:AlertEventStatus; title:string; message:string; trigger_value:number; threshold_value:number; source_time:string|null; first_triggered_at:string; last_seen_at:string; resolved_at:string|null; created_at:string; updated_at:string }
export interface AlertSettings { enabled:boolean; low_balance_enabled:boolean; balance_warning_threshold:number; balance_critical_threshold:number; low_remaining_days_enabled:boolean; remaining_days_warning_threshold:number; remaining_days_critical_threshold:number }

import type { ElectricityReading, ElectricityRecord } from '@/types/api'
import type { SavedDormitory } from '@/composables/useDormitorySettings'

const iso = (date: Date) => date.toISOString()
const start = new Date()
start.setDate(start.getDate() - 89)
start.setHours(9, 0, 0, 0)

export const demoDormitory: SavedDormitory = {
  areaId: '2',
  building: { id: 'demo-a', name: '沙河校区雁北园 A 楼' },
  floor: { id: '4', name: '4 层' },
  room: { id: '419', name: 'A 楼 419' },
}

const dailyUsage = Array.from({ length: 90 }, (_, index) => {
  const weekly = [1.7, 2.1, 1.5, 2.4, 2.8, 1.2, 0.8][index % 7]
  return Number((weekly + ((index * 17) % 9) / 10).toFixed(1))
})

let usage = 8118.6
let balance = 166.8
export const demoHistory: ElectricityRecord[] = dailyUsage.map((dayUsage, index) => {
  usage += dayUsage
  balance -= dayUsage * 0.5
  const date = new Date(start)
  date.setDate(start.getDate() + index)
  return {
    id: index + 1,
    area_id: demoDormitory.areaId,
    building_id: demoDormitory.building.id,
    building_name: demoDormitory.building.name,
    floor_id: demoDormitory.floor.id,
    floor_name: demoDormitory.floor.name,
    room_id: demoDormitory.room.id,
    room_name: demoDormitory.room.name,
    remaining_money: Number(balance.toFixed(2)),
    remaining_kwh: null,
    remaining_energy_kwh: null,
    free_remaining_kwh: null,
    total_usage_kwh: Number(usage.toFixed(2)),
    price_per_kwh: null,
    source_time: iso(date),
    query_time: iso(date),
    created_at: iso(date),
    raw_data_json: {},
  }
})

const latest = demoHistory[demoHistory.length - 1]
export const demoReading: ElectricityReading = {
  area_id: latest.area_id,
  building_id: latest.building_id,
  building_name: latest.building_name,
  floor_id: latest.floor_id,
  floor_name: latest.floor_name,
  room_id: latest.room_id,
  room_name: latest.room_name,
  source_time: latest.source_time,
  remaining_money: latest.remaining_money,
  remaining_kwh: null,
  remaining_energy_kwh: null,
  total_usage_kwh: latest.total_usage_kwh,
  free_remaining_kwh: null,
  price_per_kwh: null,
  raw_data: {},
}

export const demoDailyUsage = Object.fromEntries(demoHistory.map((record, index) => [
  (record.source_time ?? '').slice(0, 10),
  dailyUsage[index],
]))

import { computed, ref } from 'vue'
import type { RoomSelection } from '@/components/RoomSelector.vue'

export interface SavedDormitory {
  areaId: string
  areaName?: string
  building: { id: string; name: string }
  floor: { id: string; name: string }
  room: { id: string; name: string }
}

const storageKey = 'bupt-electricity-dormitory'
const selectedDormitory = ref<SavedDormitory | null>(load())

function load(): SavedDormitory | null {
  try {
    const value = localStorage.getItem(storageKey)
    return value ? JSON.parse(value) as SavedDormitory : null
  } catch { return null }
}

function save(selection: RoomSelection) {
  const value: SavedDormitory = {
    areaId: selection.areaId,
    areaName: selection.areaName,
    building: { id: selection.building.id, name: selection.building.name },
    floor: { id: selection.floor.id, name: selection.floor.name },
    room: { id: selection.room.id, name: selection.room.name },
  }
  selectedDormitory.value = value
  localStorage.setItem(storageKey, JSON.stringify(value))
}

function clear() {
  selectedDormitory.value = null
  localStorage.removeItem(storageKey)
}

export function useDormitorySettings() {
  return { selectedDormitory: computed(() => selectedDormitory.value), save, clear }
}

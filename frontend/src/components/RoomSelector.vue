<script setup lang="ts">
import { ref } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { ApiError } from '@/api/client'
import { getBuildings, getFloors, getRooms } from '@/api/electricity'
import type { Building, Floor, Room } from '@/types/api'

export interface RoomSelection { areaId: string; building: Building; floor: Floor; room: Room }
withDefaults(defineProps<{ actionLabel?: string }>(), { actionLabel: '刷新' })
const emit = defineEmits<{ query: [selection: RoomSelection]; error: [message: string] }>()
const areas = [{ id: '1', name: '西土城' }, { id: '2', name: '沙河' }]
const areaId = ref('')
const buildingId = ref('')
const floorId = ref('')
const roomId = ref('')
const buildings = ref<Building[]>([]); const floors = ref<Floor[]>([]); const rooms = ref<Room[]>([])
const loading = ref('')

function reset(level: 'building' | 'floor' | 'room') {
  if (level === 'building') { buildingId.value = ''; buildings.value = []; reset('floor') }
  if (level === 'floor') { floorId.value = ''; floors.value = []; reset('room') }
  if (level === 'room') { roomId.value = ''; rooms.value = [] }
}
function report(cause: unknown, fallback: string) { emit('error', cause instanceof ApiError ? cause.message : fallback) }
async function changeArea() {
  reset('building'); if (!areaId.value) return; loading.value = 'building'
  try { buildings.value = await getBuildings(areaId.value) } catch (cause) { report(cause, '获取楼栋失败，请重试。') } finally { loading.value = '' }
}
async function changeBuilding() {
  reset('floor'); if (!buildingId.value) return; loading.value = 'floor'
  try { floors.value = await getFloors(areaId.value, buildingId.value) } catch (cause) { report(cause, '获取楼层失败，请重试。') } finally { loading.value = '' }
}
async function changeFloor() {
  reset('room'); if (!floorId.value) return; loading.value = 'room'
  try { rooms.value = await getRooms(areaId.value, buildingId.value, floorId.value) } catch (cause) { report(cause, '获取宿舍失败，请重试。') } finally { loading.value = '' }
}
function refresh() {
  const building = buildings.value.find((item) => item.id === buildingId.value)
  const floor = floors.value.find((item) => item.id === floorId.value)
  const room = rooms.value.find((item) => item.id === roomId.value)
  if (areaId.value && building && floor && room) emit('query', { areaId: areaId.value, building, floor, room })
}
defineExpose({ refresh })
</script>

<template>
  <section class="room-selector" aria-label="宿舍选择">
    <label>校区<select v-model="areaId" @change="changeArea"><option value="">选择校区</option><option v-for="area in areas" :key="area.id" :value="area.id">{{ area.name }}</option></select></label>
    <label>楼栋<select v-model="buildingId" :disabled="!areaId || loading === 'building'" @change="changeBuilding"><option value="">{{ loading === 'building' ? '正在加载…' : '选择楼栋' }}</option><option v-for="item in buildings" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
    <label>楼层<select v-model="floorId" :disabled="!buildingId || loading === 'floor'" @change="changeFloor"><option value="">{{ loading === 'floor' ? '正在加载…' : '选择楼层' }}</option><option v-for="item in floors" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
    <label>宿舍<select v-model="roomId" :disabled="!floorId || loading === 'room'"><option value="">{{ loading === 'room' ? '正在加载…' : '选择宿舍' }}</option><option v-for="item in rooms" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
    <button class="icon-button refresh-button selector-action" :title="actionLabel" :disabled="!roomId" @click="refresh"><RefreshCw :size="16" /><span>{{ actionLabel }}</span></button>
  </section>
</template>

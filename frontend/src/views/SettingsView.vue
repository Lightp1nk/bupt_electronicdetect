<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, Check } from 'lucide-vue-next'
import RoomSelector, { type RoomSelection } from '@/components/RoomSelector.vue'
import { useDormitorySettings } from '@/composables/useDormitorySettings'
import { ApiError } from '@/api/client'
import { clearCollectionSettings, getAlertSettings, getCollectionSettings, runCollection, saveAlertSettings, saveCollectionSettings } from '@/api/electricity'
import type { AlertSettings, CollectionState } from '@/types/api'

const emit = defineEmits<{ back: []; saved: [] }>()
const { selectedDormitory, save, clear } = useDormitorySettings()
const error = ref('')
const collection = ref<CollectionState | null>(null)
const collectionLoading = ref(false)
const alertSettings = ref<AlertSettings | null>(null)
const statusText: Record<CollectionState['status'], string> = {
  never_run: '尚未运行', success: '运行成功', no_room_configured: '尚未配置宿舍', not_authenticated: '当前未登录',
  session_expired: '登录已过期', upstream_not_updated: '上游尚未更新', failed: '运行失败', already_running: '正在运行',
}
const displayTime = (value: string | null) => value ? value.replace('T', ' ').slice(0, 16) : '—'
async function loadCollection() { try { collection.value = await getCollectionSettings() } catch { collection.value = null } }
async function saveSelection(selection: RoomSelection) {
  error.value = ''
  try {
    collection.value = await saveCollectionSettings({ area_id: selection.areaId, building_id: selection.building.id, building_name: selection.building.name, floor_id: selection.floor.id, floor_name: selection.floor.name, room_id: selection.room.id, room_name: selection.room.name })
    save(selection); emit('saved')
  } catch (cause) { error.value = cause instanceof ApiError ? `自动采集配置保存失败：${cause.message}` : '自动采集配置保存失败，请重试。' }
}
async function clearSelection() {
  error.value = ''
  try { collection.value = await clearCollectionSettings(); clear() } catch (cause) { error.value = cause instanceof ApiError ? `自动采集配置保存失败：${cause.message}` : '自动采集配置保存失败，请重试。' }
}
async function testCollection() {
  collectionLoading.value = true; error.value = ''
  try { collection.value = await runCollection() } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '自动采集测试失败，请重试。' } finally { collectionLoading.value = false }
}
async function loadAlerts() { try { alertSettings.value = await getAlertSettings() } catch { alertSettings.value = null } }
async function saveAlerts() { if (!alertSettings.value) return; if (alertSettings.value.balance_critical_threshold >= alertSettings.value.balance_warning_threshold || alertSettings.value.remaining_days_critical_threshold >= alertSettings.value.remaining_days_warning_threshold) { error.value = '预警设置中，严重阈值必须小于警告阈值。'; return } try { alertSettings.value = await saveAlertSettings(alertSettings.value) } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '预警设置保存失败。' } }
onMounted(() => { loadCollection(); loadAlerts() })
</script>

<template>
  <section class="settings-page">
    <button class="back-button" @click="emit('back')"><ArrowLeft :size="16" />返回仪表板</button>
    <p class="eyebrow">SETTINGS</p><h1>宿舍设置</h1><p class="settings-description">选择用于面板展示和手动刷新的宿舍。仅保存宿舍标识与名称，不保存账号或密码。</p>
    <div class="settings-surface"><h2>当前宿舍</h2><p v-if="selectedDormitory" class="saved-dormitory">{{ selectedDormitory.building.name }} · {{ selectedDormitory.floor.name }} · {{ selectedDormitory.room.name }}</p><p v-else class="muted">尚未设置宿舍</p><button v-if="selectedDormitory" class="text-button" @click="clearSelection">清除当前设置</button><div class="settings-divider"></div><RoomSelector action-label="保存" @query="saveSelection" @error="error = $event" /><p v-if="error" class="inline-error query-error">{{ error }}</p><p class="setting-hint"><Check :size="14" />选择宿舍后即保存并返回仪表板。</p><div class="settings-divider"></div><div class="collection-settings"><h2>自动采集</h2><p class="muted">{{ collection?.enabled ? `每天 ${collection.scheduled_time}（北京时间）自动采集一次。` : '自动采集已在服务配置中关闭。' }}</p><p class="muted">监测宿舍：{{ collection?.room_id ? `${collection.building_name} · ${collection.floor_name} · ${collection.room_name}` : '尚未配置' }}</p><p class="collection-status">状态：{{ collection ? statusText[collection.status] : '暂时无法读取' }}</p><p class="muted">最近成功：{{ displayTime(collection?.last_success_time ?? null) }}</p><p v-if="collection && !collection.authenticated" class="inline-error">当前无法执行；需要重新登录后恢复自动采集。</p><button class="text-button" :disabled="collectionLoading" @click="testCollection">{{ collectionLoading ? '正在测试…' : '立即测试采集' }}</button></div><div class="settings-divider"></div><div v-if="alertSettings" class="collection-settings"><h2>预警设置</h2><label><input v-model="alertSettings.enabled" type="checkbox" />启用预警</label><label><input v-model="alertSettings.low_balance_enabled" type="checkbox" />余额预警</label><div class="thresholds"><label>警告（元）<input v-model.number="alertSettings.balance_warning_threshold" type="number" min="0.01" /></label><label>严重（元）<input v-model.number="alertSettings.balance_critical_threshold" type="number" min="0.01" /></label></div><label><input v-model="alertSettings.low_remaining_days_enabled" type="checkbox" />剩余天数预警</label><div class="thresholds"><label>警告（天）<input v-model.number="alertSettings.remaining_days_warning_threshold" type="number" min="0.01" /></label><label>严重（天）<input v-model.number="alertSettings.remaining_days_critical_threshold" type="number" min="0.01" /></label></div><button class="text-button" @click="saveAlerts">保存预警设置</button></div></div>
  </section>
</template>

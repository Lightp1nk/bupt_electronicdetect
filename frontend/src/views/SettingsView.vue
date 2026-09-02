<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, Check } from 'lucide-vue-next'
import RoomSelector, { type RoomSelection } from '@/components/RoomSelector.vue'
import { useDormitorySettings } from '@/composables/useDormitorySettings'
import { ApiError } from '@/api/client'
import { clearCollectionSettings, getAlertSettings, getCollectionSettings, getNotificationBindings, getNotificationStatus, runCollection, saveAlertSettings, saveCollectionSettings, setAstrBotNotificationEnabled } from '@/api/electricity'
import { createChatBindingCode, deleteChatIdentity, getChatIdentity } from '@/api/chat'
import type { AlertSettings, ChatBindingCode, ChatIdentity, CollectionState, NotificationBinding, NotificationStatus } from '@/types/api'

const emit = defineEmits<{ back: []; saved: [] }>()
const { selectedDormitory, save, clear } = useDormitorySettings()
const error = ref('')
const collection = ref<CollectionState | null>(null)
const collectionLoading = ref(false)
const alertSettings = ref<AlertSettings | null>(null); const alertSaving = ref(false); const alertSaved = ref('')
const notification = ref<NotificationBinding | null>(null); const notificationEnabled = ref(true); const notificationSaving = ref(false); const notificationSaved = ref('')
const notificationStatus = ref<NotificationStatus | null>(null)
const chatIdentity = ref<ChatIdentity | null>(null); const chatBindingCode = ref<ChatBindingCode | null>(null); const chatBindingLoading = ref(false); const chatIdentityLoading = ref(false)
const statusText: Record<CollectionState['status'], string> = {
  never_run: '尚未运行', success: '运行成功', no_room_configured: '尚未配置宿舍', not_authenticated: '当前未登录',
  session_expired: '登录已过期', upstream_not_updated: '上游尚未更新', failed: '运行失败', already_running: '正在运行',
}
const displayTime = (value: string | null) => value ? value.replace('T', ' ').slice(0, 16) : '—'
async function loadCollection() { try { collection.value = await getCollectionSettings() } catch { collection.value = null } }
async function saveSelection(selection: RoomSelection) {
  error.value = ''
  try {
    collection.value = await saveCollectionSettings({ area_id: selection.areaId, area_name: selection.areaName, building_id: selection.building.id, building_name: selection.building.name, floor_id: selection.floor.id, floor_name: selection.floor.name, room_id: selection.room.id, room_name: selection.room.name })
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
async function saveAlerts() {
  if (!alertSettings.value) return
  if (alertSettings.value.balance_critical_threshold >= alertSettings.value.balance_warning_threshold || alertSettings.value.remaining_days_critical_threshold >= alertSettings.value.remaining_days_warning_threshold) { error.value = '预警设置中，严重阈值必须小于警告阈值。'; return }
  error.value = ''; alertSaved.value = ''; alertSaving.value = true
  try { alertSettings.value = await saveAlertSettings(alertSettings.value); alertSaved.value = '预警设置已保存。' }
  catch (cause) { error.value = cause instanceof ApiError ? cause.message : '预警设置保存失败。' }
  finally { alertSaving.value = false }
}
async function loadNotification(){ try { notification.value=(await getNotificationBindings()).find(x=>x.provider==='astrbot'&&x.platform==='qq')??null; notificationStatus.value=await getNotificationStatus(); notificationEnabled.value=notification.value?.enabled??false }catch{ notification.value=null; notificationStatus.value=null } }
async function saveNotification(){
  error.value = ''; notificationSaved.value = ''; notificationSaving.value = true
  try {
    notification.value=await setAstrBotNotificationEnabled(notificationEnabled.value)
    notificationStatus.value=await getNotificationStatus()
    notificationSaved.value = notificationEnabled.value ? 'AstrBot 通知已启用。' : 'AstrBot 通知当前已关闭。'
  } catch(cause) { error.value=cause instanceof ApiError?cause.message:'通知设置保存失败。' }
  finally { notificationSaving.value = false }
}
async function loadChatIdentity(){ try { chatIdentity.value = await getChatIdentity() } catch { chatIdentity.value = null } }
async function createBindingCode(){
  error.value = ''; chatBindingLoading.value = true
  try { chatBindingCode.value = await createChatBindingCode() }
  catch(cause) { error.value = cause instanceof ApiError ? cause.message : '绑定码生成失败，请重试。' }
  finally { chatBindingLoading.value = false }
}
async function unbindChatIdentity(){
  error.value = ''; chatIdentityLoading.value = true
  try { await deleteChatIdentity(); chatIdentity.value = null; chatBindingCode.value = null; notification.value = null; notificationEnabled.value = false }
  catch(cause) { error.value = cause instanceof ApiError ? cause.message : 'QQ 解绑失败，请重试。' }
  finally { chatIdentityLoading.value = false }
}
onMounted(() => { loadCollection(); loadAlerts(); loadNotification(); loadChatIdentity() })
</script>

<template>
  <section class="settings-page">
    <button class="back-button" @click="emit('back')"><ArrowLeft :size="16" />返回仪表板</button>
    <p class="eyebrow">SETTINGS</p><h1>宿舍设置</h1><p class="settings-description">选择用于面板展示和手动刷新的宿舍。仅保存宿舍标识与名称，不保存账号或密码。</p>
    <div class="settings-surface"><h2>当前宿舍</h2><p v-if="selectedDormitory" class="saved-dormitory">{{ selectedDormitory.building.name }} · {{ selectedDormitory.floor.name }} · {{ selectedDormitory.room.name }}</p><p v-else class="muted">尚未设置宿舍</p><button v-if="selectedDormitory" class="text-button" @click="clearSelection">清除当前设置</button><div class="settings-divider"></div><RoomSelector action-label="保存" @query="saveSelection" @error="error = $event" /><p v-if="error" class="inline-error query-error">{{ error }}</p><p class="setting-hint"><Check :size="14" />选择宿舍后即保存并返回仪表板。</p><div class="settings-divider"></div><div class="collection-settings"><h2>自动采集</h2><p class="muted">{{ collection?.enabled ? `每天 ${collection.scheduled_time}（北京时间）自动采集一次。` : '自动采集已在服务配置中关闭。' }}</p><p class="muted">监测宿舍：{{ collection?.room_id ? `${collection.building_name} · ${collection.floor_name} · ${collection.room_name}` : '尚未配置' }}</p><p class="collection-status">状态：{{ collection ? statusText[collection.status] : '暂时无法读取' }}</p><p class="muted">最近成功：{{ displayTime(collection?.last_success_time ?? null) }}</p><p v-if="collection && !collection.authenticated" class="inline-error">当前无法执行；需要重新登录后恢复自动采集。</p><button class="text-button" :disabled="collectionLoading" @click="testCollection">{{ collectionLoading ? '正在测试…' : '立即测试采集' }}</button></div><div class="settings-divider"></div><div v-if="alertSettings" class="collection-settings"><h2>预警设置</h2><label><input v-model="alertSettings.enabled" type="checkbox" />启用预警</label><label><input v-model="alertSettings.low_balance_enabled" type="checkbox" />余额预警</label><div class="thresholds"><label>警告（元）<input v-model.number="alertSettings.balance_warning_threshold" type="number" min="0.01" /></label><label>严重（元）<input v-model.number="alertSettings.balance_critical_threshold" type="number" min="0.01" /></label></div><label><input v-model="alertSettings.low_remaining_days_enabled" type="checkbox" />剩余天数预警</label><div class="thresholds"><label>警告（天）<input v-model.number="alertSettings.remaining_days_warning_threshold" type="number" min="0.01" /></label><label>严重（天）<input v-model.number="alertSettings.remaining_days_critical_threshold" type="number" min="0.01" /></label></div><button class="primary-button alert-save-button" :disabled="alertSaving" @click="saveAlerts">{{ alertSaving ? '正在保存…' : '保存预警设置' }}</button><p v-if="alertSaved" class="notification-saved"><Check :size="15" />{{ alertSaved }}</p></div></div>
    <div class="settings-divider"></div><div class="collection-settings notification-settings"><h2>通知设置</h2><label><input v-model="notificationEnabled" :disabled="!chatIdentity" type="checkbox" />启用 AstrBot 通知</label><p v-if="chatIdentity" class="muted">已绑定 QQ：{{ chatIdentity.external_id }}。QQ 号由机器人绑定自动确认，不能在网页中手动修改。</p><p v-else class="muted">请先完成下方 QQ 机器人绑定；完成后会自动启用 AstrBot 通知。</p><p class="muted">最近投递：{{ notificationStatus?.last_delivery_status === 'success' ? '成功' : notificationStatus?.last_delivery_status === 'failed' ? '失败' : notificationStatus?.last_delivery_status === 'pending' ? '发送中' : '暂无记录' }}</p><button class="primary-button notification-save-button" :disabled="notificationSaving || !chatIdentity" @click="saveNotification">{{ notificationSaving ? '正在保存…' : '保存通知设置' }}</button><p v-if="notificationSaved" class="notification-saved"><Check :size="15" />{{ notificationSaved }}</p></div>
    <div class="settings-divider"></div><div class="collection-settings chat-identity-settings"><h2>QQ 机器人绑定</h2><p v-if="chatIdentity" class="muted">已绑定 QQ：{{ chatIdentity.external_id }}。该绑定同时用于 QQ 查询与预警通知。</p><p v-else class="muted">绑定后可使用 QQ 查询电费，并自动建立预警通知目标。</p><template v-if="chatBindingCode"><p class="binding-code">{{ chatBindingCode.code }}</p><p class="muted">请在 QQ 私聊机器人发送：<code>/绑定 {{ chatBindingCode.code }}</code></p><p class="muted">绑定码有效至：{{ displayTime(chatBindingCode.expires_at) }}</p></template><button v-if="!chatIdentity" class="primary-button notification-save-button" :disabled="chatBindingLoading" @click="createBindingCode">{{ chatBindingLoading ? '正在生成…' : '生成绑定码' }}</button><button v-else class="text-button" :disabled="chatIdentityLoading" @click="unbindChatIdentity">{{ chatIdentityLoading ? '正在解绑…' : '解绑 QQ' }}</button></div></section>
</template>

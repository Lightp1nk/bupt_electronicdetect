<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { LogOut, RefreshCw, Settings } from 'lucide-vue-next'
import { ApiError } from '@/api/client'
import { getActiveAlerts, getAlertSettings, getAnalysis, getHistory, getLatest, queryElectricity } from '@/api/electricity'
import type { AlertEvent, AlertSettings, ElectricityAnalysis, ElectricityReading, ElectricityRecord } from '@/types/api'
import Sidebar from '@/components/Sidebar.vue'
import MetricOverview from '@/components/MetricOverview.vue'
import ElectricityHeatmap from '@/components/ElectricityHeatmap.vue'
import StatisticsSummary from '@/components/StatisticsSummary.vue'
import UsageTrendChart from '@/components/UsageTrendChart.vue'
import SettingsView from '@/views/SettingsView.vue'
import AstrBotView from '@/views/AstrBotView.vue'
import { useDormitorySettings } from '@/composables/useDormitorySettings'

const props = defineProps<{ demo?: boolean }>()
const emit = defineEmits<{ logout: [] }>()
const active = ref('仪表板'); const reading = ref<ElectricityReading | null>(null); const history = ref<ElectricityRecord[]>([]); const analysis = ref<ElectricityAnalysis | null>(null); const alerts = ref<AlertEvent[]>([]); const alertSettings = ref<AlertSettings | null>(null)
const loading = ref(false); const error = ref(''); const { selectedDormitory } = useDormitorySettings()
const demoRoom = { areaId: 'demo-shahe', roomId: 'demo-419' }
const dashboardDormitory = computed(() => {
  if (props.demo) {
    if (!reading.value) return null
    return {
      areaId: reading.value.area_id,
      building: { id: reading.value.building_id, name: reading.value.building_name ?? '演示楼栋' },
      floor: { id: reading.value.floor_id, name: reading.value.floor_name ?? '演示楼层' },
      room: { id: reading.value.room_id, name: reading.value.room_name ?? '演示宿舍' },
    }
  }
  return selectedDormitory.value
})
const updatedAt = computed(() => reading.value?.source_time?.replace('T', ' ').slice(5, 16) ?? null)
const demoWarnings = computed(() => {
  if (!props.demo || !analysis.value) return []
  const values: { level: 'warning' | 'critical'; title: string; message: string }[] = []
  const balance = analysis.value.current.remaining_money
  const days = analysis.value.prediction.estimated_remaining_days
  if (days !== null && days <= 7) values.push({ level: days <= 3 ? 'critical' : 'warning', title: '预计可用时间较短', message: `演示预览：当前约 ${days.toFixed(1)} 天；不会创建真实预警或发送通知。` })
  if (balance !== null && balance <= 20) values.push({ level: balance <= 10 ? 'critical' : 'warning', title: '余额不足', message: `演示预览：当前 ${balance.toFixed(2)} 元；不会创建真实预警或发送通知。` })
  return values
})
const demoAnomalyDates = computed(() => history.value
  .filter((record) => record.raw_data_json?.scenario === 'high_usage_demo')
  .map((record) => (record.source_time ?? record.query_time).slice(0, 10)))
async function refreshReading() {
  if (props.demo) { await loadDemoDashboard(); return }
  const value = selectedDormitory.value
  if (!value) { active.value = '设置'; return }
  error.value = ''; loading.value = true
  try {
    const result = await queryElectricity({ area_id: value.areaId, building_id: value.building.id, floor_id: value.floor.id, room_id: value.room.id, room_name: value.room.name })
    reading.value = result.reading
    const [savedHistory, savedAnalysis, activeAlerts, settings] = await Promise.all([
      getHistory(value.areaId, value.room.id),
      getAnalysis(value.areaId, value.room.id), getActiveAlerts(value.areaId, value.room.id), getAlertSettings(),
    ])
    history.value = savedHistory; analysis.value = savedAnalysis; alerts.value = activeAlerts; alertSettings.value = settings
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '查询当前用电信息失败，请重试。' } finally { loading.value = false }
}
async function loadSavedDashboard() {
  if (props.demo) { await loadDemoDashboard(); return }
  const value = selectedDormitory.value
  if (!value) { active.value = '设置'; return }
  error.value = ''; loading.value = true
  try {
    const [latest, savedHistory, savedAnalysis, activeAlerts, settings] = await Promise.all([
      getLatest(value.areaId, value.room.id), getHistory(value.areaId, value.room.id), getAnalysis(value.areaId, value.room.id),
      getActiveAlerts(value.areaId, value.room.id), getAlertSettings(),
    ])
    reading.value = { ...latest, raw_data: latest.raw_data_json }; history.value = savedHistory; analysis.value = savedAnalysis; alerts.value = activeAlerts; alertSettings.value = settings
  } catch (cause) {
    if (cause instanceof ApiError && cause.code === 'NOT_FOUND') { alertSettings.value = await getAlertSettings(); return }
    error.value = cause instanceof ApiError ? cause.message : '读取已保存的用电数据失败，请重试。'
  } finally { loading.value = false }
}
async function loadDemoDashboard() {
  error.value = ''; loading.value = true
  try {
    const [latest, savedHistory, savedAnalysis] = await Promise.all([
      getLatest(demoRoom.areaId, demoRoom.roomId, 'demo'),
      getHistory(demoRoom.areaId, demoRoom.roomId, 365, 'demo'),
      getAnalysis(demoRoom.areaId, demoRoom.roomId, 'demo'),
    ])
    reading.value = { ...latest, raw_data: latest.raw_data_json }
    history.value = savedHistory; analysis.value = savedAnalysis; alerts.value = []; alertSettings.value = null
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '读取演示数据失败，请重试。' }
  finally { loading.value = false }
}
function returnToDashboard() { active.value = '仪表板' }
async function settingsSaved() { returnToDashboard(); await refreshReading() }
watch(
  () => selectedDormitory.value && `${selectedDormitory.value.areaId}:${selectedDormitory.value.room.id}`,
  (roomKey) => { if (!props.demo && roomKey) void loadSavedDashboard() },
  { immediate: true },
)

if (props.demo) void loadSavedDashboard()
</script>

<template>
  <div class="app-shell"><Sidebar :active="active" :connected="true" :updated-at="updatedAt" :demo="demo" @navigate="active = $event" />
    <main class="workspace"><header class="page-header"><div><h1>宿舍用电监测</h1><p v-if="dashboardDormitory">{{ dashboardDormitory.building.name }} · {{ dashboardDormitory.floor.name }} · {{ dashboardDormitory.room.name }}</p><p v-else>{{ demo ? '正在加载演示宿舍' : '请先在设置中选择宿舍' }}</p></div><div class="header-actions"><span v-if="demo" class="subtle-badge demo-badge">演示数据</span><button class="refresh-primary" :disabled="loading" @click="refreshReading"><RefreshCw :size="16" :class="{ spinning: loading }" />{{ loading ? '正在刷新' : '刷新' }}</button><button class="quiet-button" @click="emit('logout')"><LogOut :size="16" />退出登录</button></div></header>
      <template v-if="active === '仪表板'"><section v-if="demo" class="demo-mode-notice">🟡 演示数据模式：所有图表、预测和预警预览均来自后端静态数据集；不会查询北邮、写入数据库或发送通知。</section><section v-if="!dashboardDormitory && !demo" class="setup-empty"><Settings :size="22" /><div><h2>先设置你的宿舍</h2><p>完成校区、楼栋、楼层和宿舍选择后，面板将直接展示该宿舍的用电情况。</p></div><button class="primary-button" @click="active = '设置'">前往设置</button></section><template v-else><p v-if="error" class="inline-error query-error">{{ error }}</p><MetricOverview :reading="reading" :loading="loading" :demo="demo" /><section class="data-section alert-section"><header class="section-header"><div><h2>用电预警</h2><p>{{ demo ? '演示预警预览，不产生真实事件或通知' : '基于最近一次真实查询' }}</p></div></header><template v-if="demo"><p v-if="!demoWarnings.length" class="muted">演示数据当前未达到预览阈值。</p><div v-for="alert in demoWarnings" :key="alert.title" class="alert-item" :class="alert.level"><strong>{{ alert.title }}</strong><span>{{ alert.message }}</span></div></template><template v-else><p v-if="!alertSettings" class="muted">正在读取预警设置…</p><p v-else-if="!alertSettings.enabled" class="muted">预警功能当前已关闭</p><p v-else-if="!alerts.length" class="muted">当前用电状态正常</p><div v-for="alert in alertSettings?.enabled ? alerts : []" :key="alert.id" class="alert-item" :class="alert.level"><strong>{{ alert.title }}</strong><span>{{ alert.message }}</span></div></template></section><ElectricityHeatmap :daily-usage="Object.fromEntries((analysis?.daily_usage ?? []).map((item) => [item.date, item.usage_kwh]))" :demo="demo" :anomaly-dates="demoAnomalyDates" /><StatisticsSummary :analysis="analysis" /><div class="trends"><UsageTrendChart :records="history" field="total_usage_kwh" title="累计用电趋势" unit="kWh" :demo="demo" /><UsageTrendChart :records="history" field="remaining_money" title="余额趋势" unit="元" :demo="demo" /></div></template></template>
      <SettingsView v-else-if="active === '设置'" @back="returnToDashboard" @saved="settingsSaved" />
      <AstrBotView v-else-if="active === 'AstrBot 接入'" @back="returnToDashboard" @configure="active = '设置'" />
    </main>
  </div>
</template>

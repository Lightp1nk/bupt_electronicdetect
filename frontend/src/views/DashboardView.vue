<script setup lang="ts">
import { computed, ref } from 'vue'
import { LogOut, RefreshCw, Settings } from 'lucide-vue-next'
import { ApiError } from '@/api/client'
import { getAnalysis, getHistory, queryElectricity } from '@/api/electricity'
import type { ElectricityAnalysis, ElectricityReading, ElectricityRecord } from '@/types/api'
import Sidebar from '@/components/Sidebar.vue'
import MetricOverview from '@/components/MetricOverview.vue'
import ElectricityHeatmap from '@/components/ElectricityHeatmap.vue'
import StatisticsSummary from '@/components/StatisticsSummary.vue'
import UsageTrendChart from '@/components/UsageTrendChart.vue'
import SettingsView from '@/views/SettingsView.vue'
import AstrBotView from '@/views/AstrBotView.vue'
import { useDormitorySettings } from '@/composables/useDormitorySettings'
import { demoDailyUsage, demoDormitory, demoHistory, demoReading } from '@/mock/dashboard'

const props = defineProps<{ demo?: boolean }>()
const emit = defineEmits<{ logout: [] }>()
const active = ref('仪表板'); const reading = ref<ElectricityReading | null>(null); const history = ref<ElectricityRecord[]>([]); const analysis = ref<ElectricityAnalysis | null>(null)
const loading = ref(false); const error = ref(''); const { selectedDormitory } = useDormitorySettings()
const dashboardDormitory = computed(() => selectedDormitory.value ?? (props.demo ? demoDormitory : null))
const updatedAt = computed(() => reading.value?.source_time?.replace('T', ' ').slice(5, 16) ?? null)
async function refreshReading() {
  if (props.demo) { reading.value = demoReading; history.value = demoHistory; analysis.value = null; return }
  const value = selectedDormitory.value
  if (!value) { active.value = '设置'; return }
  error.value = ''; loading.value = true
  try {
    const result = await queryElectricity({ area_id: value.areaId, building_id: value.building.id, floor_id: value.floor.id, room_id: value.room.id, room_name: value.room.name })
    reading.value = result.reading
    const [savedHistory, savedAnalysis] = await Promise.all([
      getHistory(value.areaId, value.room.id),
      getAnalysis(value.areaId, value.room.id),
    ])
    history.value = savedHistory
    analysis.value = savedAnalysis
  } catch (cause) { error.value = cause instanceof ApiError ? cause.message : '查询当前用电信息失败，请重试。' } finally { loading.value = false }
}
function returnToDashboard() { active.value = '仪表板' }
async function settingsSaved() { returnToDashboard(); await refreshReading() }
if (props.demo) { refreshReading() }
</script>

<template>
  <div class="app-shell"><Sidebar :active="active" :connected="true" :updated-at="updatedAt" @navigate="active = $event" />
    <main class="workspace"><header class="page-header"><div><p class="eyebrow">OVERVIEW</p><h1>宿舍用电监测</h1><p v-if="dashboardDormitory">{{ dashboardDormitory.building.name }} · {{ dashboardDormitory.floor.name }} · {{ dashboardDormitory.room.name }}</p><p v-else>请先在设置中选择宿舍</p></div><div class="header-actions"><span v-if="demo" class="subtle-badge demo-badge">演示数据</span><button class="refresh-primary" :disabled="loading" @click="refreshReading"><RefreshCw :size="16" :class="{ spinning: loading }" />{{ loading ? '正在刷新' : '刷新' }}</button><button class="quiet-button" @click="emit('logout')"><LogOut :size="16" />退出登录</button></div></header>
      <template v-if="active === '仪表板'"><section v-if="!dashboardDormitory" class="setup-empty"><Settings :size="22" /><div><h2>先设置你的宿舍</h2><p>完成校区、楼栋、楼层和宿舍选择后，面板将直接展示该宿舍的用电情况。</p></div><button class="primary-button" @click="active = '设置'">前往设置</button></section><template v-else><p v-if="error" class="inline-error query-error">{{ error }}</p><MetricOverview :reading="reading" :loading="loading" /><ElectricityHeatmap :daily-usage="demo ? demoDailyUsage : Object.fromEntries((analysis?.daily_usage ?? []).map((item) => [item.date, item.usage_kwh]))" :demo="demo" /><StatisticsSummary :analysis="analysis" :daily-usage="demo ? demoDailyUsage : undefined" :demo="demo" /><div class="trends"><UsageTrendChart :records="history" field="total_usage_kwh" title="累计用电趋势" unit="kWh" /><UsageTrendChart :records="history" field="remaining_money" title="余额趋势" unit="元" /></div></template></template>
      <SettingsView v-else-if="active === '设置'" @back="returnToDashboard" @saved="settingsSaved" />
      <AstrBotView v-else-if="active === 'AstrBot 接入'" @back="returnToDashboard" />
    </main>
  </div>
</template>

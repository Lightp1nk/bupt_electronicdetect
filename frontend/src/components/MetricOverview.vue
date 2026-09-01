<script setup lang="ts">
import type { ElectricityReading } from '@/types/api'

defineProps<{ reading: ElectricityReading | null; loading: boolean }>()
const amount = (value: number | null | undefined, suffix = '') => value === null || value === undefined ? '—' : `${value.toFixed(2)}${suffix}`
</script>

<template>
  <section class="metric-overview" :class="{ loading }" aria-label="当前用电概览">
    <div class="metric"><span>当前余额</span><strong>{{ amount(reading?.remaining_money, ' 元') }}</strong><small>{{ reading?.remaining_money === null || reading?.remaining_money === undefined ? '—' : '实时查询结果' }}</small></div>
    <div class="metric"><span>累计用电量</span><strong>{{ amount(reading?.total_usage_kwh, ' kWh') }}</strong><small>{{ reading?.total_usage_kwh === null || reading?.total_usage_kwh === undefined ? '—' : '上游累计值' }}</small></div>
    <div class="metric"><span>最近更新</span><strong class="time-value">{{ reading?.source_time ? reading.source_time.replace('T', ' ').slice(5, 16) : '—' }}</strong><small>{{ reading?.source_time ? '来自电控系统' : '等待查询' }}</small></div>
  </section>
</template>

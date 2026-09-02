<script setup lang="ts">
import type { ElectricityAnalysis } from '@/types/api'

const props = defineProps<{ analysis?: ElectricityAnalysis | null }>()
const values = () => {
  if (props.analysis) {
    const { statistics, prediction } = props.analysis
    const display = (value: number | null, suffix: string) => value === null ? '数据积累中' : `${value.toFixed(2)} ${suffix}`
    const latestDaily = props.analysis.daily_usage[props.analysis.daily_usage.length - 1]
    return [
      latestDaily ? `${latestDaily.usage_kwh.toFixed(2)} kWh` : '数据积累中',
      display(statistics.avg_3d_kwh, 'kWh/天'),
      display(statistics.avg_7d_kwh, 'kWh/天'),
      prediction.estimated_remaining_days === null ? '数据积累中' : `约 ${prediction.estimated_remaining_days.toFixed(1)} 天`,
    ]
  }
  return ['数据积累中', '数据积累中', '数据积累中', '数据积累中']
}
const items = ['今日用电', '近 3 日平均', '近 7 日平均', '预计可用时间']
</script>

<template>
  <section class="statistics-summary" aria-label="统计摘要">
    <div v-for="(item, index) in items" :key="item" class="stat-item"><span>{{ item }}</span><strong>{{ values()[index] }}</strong></div>
  </section>
</template>

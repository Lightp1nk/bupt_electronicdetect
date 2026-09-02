<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ dailyUsage?: Record<string, number>; demo?: boolean }>(), { dailyUsage: () => ({}), demo: false })

const days = ['一', '二', '三', '四', '五', '六', '日']
const millisecondsPerDay = 86_400_000

const startOfLocalDay = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate())
const cells = computed(() => {
  const today = startOfLocalDay(new Date())
  // Start at a Monday, so the weekday labels always line up with the grid.
  const daysSinceMonday = (today.getDay() + 6) % 7
  const firstDay = new Date(today.getTime() - (52 * 7 + daysSinceMonday) * millisecondsPerDay)
  const totalDays = Math.floor((today.getTime() - firstDay.getTime()) / millisecondsPerDay) + 1
  return Array.from({ length: totalDays }, (_, index) => ({ index, date: new Date(firstDay.getTime() + index * millisecondsPerDay) }))
})
const monthLabels = computed(() => cells.value.filter((cell, index, values) => index === 0 || cell.date.getMonth() !== values[index - 1].date.getMonth()).map((cell) => ({ label: `${cell.date.getMonth() + 1}月`, index: cell.index })))
const displayDate = (date: Date) => `${date.getMonth() + 1}月${date.getDate()}日`
const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
const hasData = computed(() => Object.keys(props.dailyUsage).length > 0)
const usageOf = (date: Date) => props.dailyUsage[dateKey(date)]
const usageThresholds = computed(() => {
  const values = Object.values(props.dailyUsage).filter((value) => Number.isFinite(value)).sort((left, right) => left - right)
  if (values.length < 2 || values[0] === values[values.length - 1]) return []
  return [0.2, 0.4, 0.6, 0.8].map((quantile) => values[Math.floor((values.length - 1) * quantile)])
})
const weekCount = computed(() => Math.ceil(cells.value.length / 7))
const heatmapStyle = computed(() => ({ '--heatmap-width': `${weekCount.value * 24 - 4}px` }))
const heatLevel = (date: Date) => {
  const usage = usageOf(date)
  if (usage === undefined) return 'empty'
  const threshold = usageThresholds.value
  if (!threshold.length) return 'medium'
  if (usage <= threshold[0]) return 'lowest'
  if (usage <= threshold[1]) return 'low'
  if (usage <= threshold[2]) return 'medium'
  if (usage <= threshold[3]) return 'high'
  return 'highest'
}
</script>

<template>
  <section class="data-section heatmap-section">
    <header class="section-header"><div><h2>每日耗电量</h2><p>近一年 · 根据当前宿舍的用电分布动态分级</p></div><span class="subtle-badge">{{ demo ? '演示数据' : hasData ? '真实数据' : '数据积累中' }}</span></header>
    <div class="heatmap-scroll">
      <div class="heatmap-layout" :style="heatmapStyle">
        <div class="week-labels"><span v-for="day in days" :key="day">周{{ day }}</span></div>
        <div class="heatmap-main">
          <div class="month-labels"><span v-for="month in monthLabels" :key="month.index" :style="{ left: `${Math.floor(month.index / 7) * 24}px` }">{{ month.label }}</span></div>
          <div class="heatmap-grid">
            <span v-for="cell in cells" :key="cell.index" class="heatmap-cell" :class="`heat-${heatLevel(cell.date)}`" :title="usageOf(cell.date) === undefined ? `${displayDate(cell.date)}：暂无完整用电数据` : `${displayDate(cell.date)}：${usageOf(cell.date)} kWh`"></span>
          </div>
        </div>
      </div>
    </div>
    <div v-if="hasData" class="heatmap-legend" aria-label="热力图颜色说明"><span>较低</span><i class="heat-lowest"></i><i class="heat-low"></i><i class="heat-medium"></i><i class="heat-high"></i><i class="heat-highest"></i><span>较高</span></div>
    <p class="empty-note">{{ demo ? '示例数据仅用于检查布局与图表，不会写入本地数据库。' : hasData ? '仅显示由相邻 source_date 快照推导出的真实每日耗电量；颜色按当前可用数据的分位数动态细分，缺失日期保持空白。' : '正在积累每日用电数据。统计服务将在上游时间规律完成验证后接入。' }}</p>
  </section>
</template>

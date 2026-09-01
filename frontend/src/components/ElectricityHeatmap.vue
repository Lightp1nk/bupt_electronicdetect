<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ dailyUsage?: Record<string, number>; demo?: boolean }>(), { dailyUsage: () => ({}), demo: false })

const days = ['一', '二', '三', '四', '五', '六', '日']
const cells = computed(() => Array.from({ length: 91 }, (_, index) => ({ index, date: new Date(Date.now() - (90 - index) * 86400000) })))
const monthLabels = computed(() => cells.value.filter((cell, index, values) => index === 0 || cell.date.getMonth() !== values[index - 1].date.getMonth()).map((cell) => ({ label: `${cell.date.getMonth() + 1}月`, index: cell.index })))
const displayDate = (date: Date) => `${date.getMonth() + 1}月${date.getDate()}日`
const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
const hasData = computed(() => Object.keys(props.dailyUsage).length > 0)
const usageOf = (date: Date) => props.dailyUsage[dateKey(date)]
const heatLevel = (date: Date) => {
  const usage = usageOf(date)
  if (usage === undefined) return 'empty'
  if (usage < 1.2) return 'low'
  if (usage < 2) return 'medium'
  if (usage < 2.7) return 'high'
  return 'highest'
}
</script>

<template>
  <section class="data-section heatmap-section">
    <header class="section-header"><div><h2>每日耗电量</h2><p>最近 90 天</p></div><span class="subtle-badge">{{ demo ? '演示数据' : hasData ? '真实数据' : '数据积累中' }}</span></header>
    <div class="heatmap-scroll">
      <div class="heatmap-layout">
        <div class="week-labels"><span v-for="day in days" :key="day">周{{ day }}</span></div>
        <div class="heatmap-main">
          <div class="month-labels"><span v-for="month in monthLabels" :key="month.index" :style="{ left: `${Math.floor(month.index / 7) * 24}px` }">{{ month.label }}</span></div>
          <div class="heatmap-grid">
            <span v-for="cell in cells" :key="cell.index" class="heatmap-cell" :class="`heat-${heatLevel(cell.date)}`" :title="usageOf(cell.date) === undefined ? `${displayDate(cell.date)}：暂无完整用电数据` : `${displayDate(cell.date)}：${usageOf(cell.date)} kWh`"></span>
          </div>
        </div>
      </div>
    </div>
    <p class="empty-note">{{ demo ? '示例数据仅用于检查布局与图表，不会写入本地数据库。' : hasData ? '仅显示由相邻 source_date 快照推导出的真实每日耗电量；缺失日期保持空白。' : '正在积累每日用电数据。统计服务将在上游时间规律完成验证后接入。' }}</p>
  </section>
</template>

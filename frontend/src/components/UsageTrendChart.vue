<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { init, use, type ECharts } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ElectricityRecord } from '@/types/api'

const props = withDefaults(defineProps<{ records: ElectricityRecord[]; field: 'total_usage_kwh' | 'remaining_money'; title: string; unit: string; demo?: boolean }>(), { demo: false })
const container = ref<HTMLDivElement | null>(null)
let chart: ECharts | null = null
use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
const hasData = () => props.records.filter((record) => record[props.field] !== null).length >= 2

function render() {
  if (!container.value || !hasData()) return
  chart ??= init(container.value)
  const data = props.records.filter((record) => record[props.field] !== null)
  chart.setOption({
    animationDuration: 180, grid: { left: 42, right: 20, top: 20, bottom: 30 },
    tooltip: { trigger: 'axis', backgroundColor: '#202124', borderWidth: 0, textStyle: { color: '#fff' } },
    xAxis: { type: 'category', boundaryGap: false, data: data.map((record) => (record.source_time ?? record.query_time).slice(5, 16)), axisLine: { lineStyle: { color: '#e5e5e7' } }, axisTick: { show: false }, axisLabel: { color: '#8a8a91', fontSize: 11 } },
    yAxis: { type: 'value', axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: '#8a8a91', fontSize: 11, formatter: `{value} ${props.unit}` }, splitLine: { lineStyle: { color: '#efeff0' } } },
    series: [{ type: 'line', data: data.map((record) => record[props.field]), smooth: 0.18, symbol: 'none', lineStyle: { color: '#238636', width: 2 }, itemStyle: { color: '#238636' }, emphasis: { focus: 'series', itemStyle: { borderWidth: 2, borderColor: '#fff' } } }],
  }, { notMerge: true })
}
function resize() { chart?.resize() }
watch(() => props.records, async () => { await nextTick(); if (hasData()) render(); else { chart?.dispose(); chart = null } }, { deep: true })
onMounted(() => { render(); window.addEventListener('resize', resize) })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart?.dispose() })
</script>

<template>
  <section class="data-section trend-section"><header class="section-header"><div><h2>{{ title }}</h2><p>{{ demo ? '来自后端演示快照' : '来自本地历史快照' }}</p></div></header><div v-if="hasData()" ref="container" class="chart"></div><div v-else class="chart-empty">暂无足够的历史用电数据</div></section>
</template>

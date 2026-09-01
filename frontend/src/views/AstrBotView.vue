<script setup lang="ts">
import { ArrowLeft, Bot } from 'lucide-vue-next'
defineEmits<{ back: [] }>()
</script>

<template>
  <section class="settings-page"><button class="back-button" @click="$emit('back')"><ArrowLeft :size="16" />返回仪表板</button><p class="eyebrow">INTEGRATION</p><h1>AstrBot 接入</h1><p class="settings-description">用于后续接收用电状态与预警通知。</p><div class="integration-empty"><Bot :size="23" /><h2>接入功能准备中</h2><p>当前后端尚未提供 AstrBot 配置或通知 API，因此不会显示模拟配置项。</p></div></section>
</template>

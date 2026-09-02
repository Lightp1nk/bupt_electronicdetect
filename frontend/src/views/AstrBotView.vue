<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ArrowLeft, Bot, CheckCircle2, CircleAlert, RefreshCw } from 'lucide-vue-next'
import { getNotificationStatus } from '@/api/electricity'
import type { NotificationStatus } from '@/types/api'

const emit = defineEmits<{ back: []; configure: [] }>()
const status = ref<NotificationStatus | null>(null)
const loading = ref(false)

async function loadStatus() {
  loading.value = true
  try { status.value = await getNotificationStatus() } finally { loading.value = false }
}

onMounted(loadStatus)
</script>

<template>
  <section class="settings-page">
    <button class="back-button" @click="emit('back')"><ArrowLeft :size="16" />返回仪表板</button>
    <p class="eyebrow">INTEGRATION</p><h1>AstrBot 接入</h1>
    <p class="settings-description">将用电预警发送到已绑定的 QQ 私聊。QQ 号与 AstrBot 私聊身份由桥接插件安全关联。</p>
    <div class="integration-card">
      <div class="integration-card-heading"><Bot :size="23" /><div><h2>通知状态</h2><p>{{ status?.enabled ? 'AstrBot 通知已启用' : '尚未启用 AstrBot 通知' }}</p></div><button class="icon-button" aria-label="刷新通知状态" :disabled="loading" @click="loadStatus"><RefreshCw :size="16" :class="{ spinning: loading }" /></button></div>
      <p v-if="status?.last_delivery_status === 'success'" class="integration-status success"><CheckCircle2 :size="16" />最近一次投递成功</p>
      <p v-else-if="status?.last_delivery_status === 'failed'" class="integration-status warning"><CircleAlert :size="16" />最近一次投递失败，请检查 QQ 绑定</p>
      <p v-else class="muted">暂无投递记录</p>
    </div>
    <div class="integration-card integration-steps"><h2>绑定步骤</h2><ol><li>前往“设置”生成一次性 QQ 绑定码。</li><li>使用同一 QQ 号私聊机器人，发送 <code>/绑定 绑定码</code>。</li><li>机器人确认后，QQ 查询与预警通知会同时完成绑定。</li></ol><p class="muted">QQ 号由机器人自动确认，网页中无需填写。</p><button class="primary-button integration-action" @click="emit('configure')">前往设置</button></div>
  </section>
</template>

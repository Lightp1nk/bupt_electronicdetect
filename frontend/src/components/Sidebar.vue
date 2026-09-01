<script setup lang="ts">
import { Bot, Settings } from 'lucide-vue-next'

defineProps<{ active: string; connected: boolean; updatedAt: string | null }>()
const emit = defineEmits<{ navigate: [name: string] }>()
const items = [{ name: '设置', icon: Settings }, { name: 'AstrBot 接入', icon: Bot }]
</script>

<template>
  <aside class="sidebar">
    <button class="brand" type="button" aria-label="返回用电监测主页" @click="emit('navigate', '仪表板')"><span class="brand-mark">E</span><span>用电监测</span></button>
    <nav aria-label="主导航">
      <button v-for="item in items" :key="item.name" class="nav-item" :class="{ active: active === item.name }" @click="emit('navigate', item.name)">
        <component :is="item.icon" :size="17" />{{ item.name }}
      </button>
    </nav>
    <div class="sidebar-status">
      <span class="connection-dot" :class="{ online: connected }"></span>
      <span>{{ connected ? '认证连接正常' : '未连接' }}</span>
    </div>
  </aside>
</template>

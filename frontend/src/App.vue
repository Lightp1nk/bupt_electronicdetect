<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getStatus, logout } from '@/api/auth'
import LoginView from '@/components/LoginView.vue'
import DashboardView from '@/views/DashboardView.vue'

const authenticated = ref(false)
const ready = ref(false)
const demoMode = new URLSearchParams(window.location.search).get('demo') === '1'
async function checkStatus() { try { authenticated.value = (await getStatus()).authenticated } catch { authenticated.value = false } finally { ready.value = true } }
async function signOut() { try { await logout() } finally { authenticated.value = false } }
onMounted(() => {
  if (demoMode) { authenticated.value = true; ready.value = true; return }
  checkStatus()
})
</script>

<template>
  <div v-if="!ready" class="app-loading"><span></span></div>
  <LoginView v-else-if="!authenticated" @authenticated="authenticated = true" />
  <DashboardView v-else :demo="demoMode" @logout="signOut" />
</template>

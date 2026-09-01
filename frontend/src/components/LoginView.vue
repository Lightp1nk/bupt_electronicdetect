<script setup lang="ts">
import { ref } from 'vue'
import { ArrowRight } from 'lucide-vue-next'
import { ApiError } from '@/api/client'
import { login } from '@/api/auth'

const emit = defineEmits<{ authenticated: [] }>()
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await login(username.value, password.value)
    password.value = ''
    emit('authenticated')
  } catch (cause) {
    password.value = ''
    error.value = cause instanceof ApiError ? cause.message : '认证未完成，请重试。'
  } finally { loading.value = false }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <h1 id="login-title">巴普特电费查询系统</h1>
      <p class="login-description">使用北邮统一认证查询你的宿舍用电数据。</p>
      <form @submit.prevent="submit">
        <label>学号<input v-model.trim="username" autocomplete="username" inputmode="numeric" required /></label>
        <label>密码<input v-model="password" type="password" autocomplete="current-password" required /></label>
        <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
        <button class="primary-button login-button" :disabled="loading">
          <span>{{ loading ? '正在认证' : '登录' }}</span><ArrowRight v-if="!loading" :size="17" />
        </button>
      </form>
      <p class="security-note">账号信息仅用于本次认证，不在本地数据库保存。</p>
    </section>
  </main>
</template>

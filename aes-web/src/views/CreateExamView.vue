<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { examApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Card from 'primevue/card'
import Toast from 'primevue/toast'
import { useToast } from 'primevue/usetoast'

// Debug: Log saat komponen dimuat
onMounted(() => {
  console.log('CreateExamView mounted')
})

const router = useRouter()
const toast = useToast()

const title = ref('')
const description = ref('')
const loading = ref(false)
const errors = ref({
  title: '',
  description: ''
})

// Validasi form
const validateForm = () => {
  let isValid = true
  errors.value = {
    title: '',
    description: ''
  }

  if (!title.value.trim()) {
    errors.value.title = 'Judul ujian harus diisi'
    isValid = false
  } else if (title.value.trim().length < 3) {
    errors.value.title = 'Judul ujian minimal 3 karakter'
    isValid = false
  }

  return isValid
}

// Simpan ujian
const saveExam = async () => {
  if (!validateForm()) return

  try {
    loading.value = true
    const examData = {
      title: title.value.trim(),
      description: description.value.trim()
    }

    const response = await examApi.createExam(examData)
    
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Ujian berhasil dibuat',
      life: 3000
    })

    // Redirect ke halaman detail ujian
    router.push(`/exams/${response.data.id}`)
  } catch (error) {
    console.error('Error creating exam:', error)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal membuat ujian. Silakan coba lagi.',
      life: 5000
    })
  } finally {
    loading.value = false
  }
}

// Kembali ke halaman ujian
const cancelCreate = () => {
  router.push('/exams')
}
</script>

<template>
  <div class="create-exam-page">
    <Toast />
    
    <div class="page-header">
      <h1>Buat Ujian Baru</h1>
      <!-- Debug info -->
      <div class="debug-info" style="color: green; margin-bottom: 10px;">
        Halaman CreateExamView berhasil dimuat
      </div>
    </div>

    <Card class="card">
      <template #content>
        <form @submit.prevent="saveExam" class="exam-form">
          <div class="form-group">
            <label for="title">Judul Ujian <span class="required">*</span></label>
            <InputText id="title" v-model="title" :class="{ 'p-invalid': errors.title }" />
            <small class="error-text" v-if="errors.title">{{ errors.title }}</small>
          </div>

          <div class="form-group">
            <label for="description">Deskripsi</label>
            <Textarea id="description" v-model="description" rows="5" autoResize />
          </div>

          <div class="form-actions">
            <Button type="button" label="Batal" class="p-button-secondary" icon="pi pi-times" 
                   @click="cancelCreate" :disabled="loading" />
            <Button type="submit" label="Simpan" icon="pi pi-save" 
                   :loading="loading" />
          </div>
        </form>
      </template>
    </Card>
  </div>
</template>

<style scoped>
.create-exam-page {
  max-width: 800px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 1.5rem;
}

.exam-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  font-weight: 600;
}

.required {
  color: #EF4444;
}

.error-text {
  color: #EF4444;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: 1rem;
}
</style>

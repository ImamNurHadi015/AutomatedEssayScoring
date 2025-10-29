<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { questionApi, answerApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Card from 'primevue/card'
import ProgressSpinner from 'primevue/progressspinner'
import { useToast } from 'primevue/usetoast'

// Custom Components
import LoadingOverlay from '../components/LoadingOverlay.vue'

const props = defineProps({
  id: {
    type: String,
    required: true
  }
})

const router = useRouter()
const toast = useToast()

const question = ref(null)
const studentName = ref('')
const answerText = ref('')
const loading = ref(false)
const questionLoading = ref(false)
const error = ref(null)
const showLoadingOverlay = ref(false)
const loadingProgress = ref(0)
const errors = ref({
  studentName: '',
  answerText: ''
})

// Ambil data pertanyaan
const fetchQuestion = async () => {
  try {
    questionLoading.value = true
    error.value = null
    const response = await questionApi.getQuestion(props.id)
    question.value = response.data
  } catch (err) {
    console.error('Error fetching question:', err)
    error.value = 'Gagal mengambil data pertanyaan. Silakan coba lagi.'
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengambil data pertanyaan',
      life: 3000
    })
  } finally {
    questionLoading.value = false
  }
}

// Validasi form
const validateForm = () => {
  let isValid = true
  errors.value = {
    studentName: '',
    answerText: ''
  }

  if (!studentName.value.trim()) {
    errors.value.studentName = 'Nama siswa harus diisi'
    isValid = false
  }

  if (!answerText.value.trim()) {
    errors.value.answerText = 'Jawaban harus diisi'
    isValid = false
  }

  return isValid
}

// Simpan jawaban
const submitAnswer = async () => {
  if (!validateForm()) return

  try {
    loading.value = true
    showLoadingOverlay.value = true
    
    // Simulasi progress untuk UX
    const progressInterval = setInterval(() => {
      if (loadingProgress.value < 90) {
        loadingProgress.value += 5
      } else {
        clearInterval(progressInterval)
      }
    }, 500)
    
    const answerData = {
      student_name: studentName.value.trim(),
      answer_text: answerText.value.trim()
    }

    const response = await answerApi.submitAnswer(props.id, answerData)
    
    // Set progress to 100% when done
    loadingProgress.value = 100
    
    // Delay to show 100% completion
    setTimeout(() => {
      showLoadingOverlay.value = false
      
      toast.add({
        severity: 'success',
        summary: 'Berhasil',
        detail: 'Jawaban berhasil dikirim dan dinilai',
        life: 3000
      })
      
      // Redirect ke halaman detail jawaban
      router.push(`/answers/${response.data.id}`)
    }, 500)
  } catch (error) {
    showLoadingOverlay.value = false
    console.error('Error submitting answer:', error)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengirim jawaban. Silakan coba lagi.',
      life: 5000
    })
  } finally {
    loading.value = false
  }
}

// Kembali ke halaman detail pertanyaan
const cancelSubmit = () => {
  router.push(`/questions/${props.id}`)
}

// Load data saat komponen dimount
onMounted(() => {
  fetchQuestion()
})
</script>

<template>
  <div class="answer-question-page">
    <LoadingOverlay 
      :visible="showLoadingOverlay" 
      title="Sedang Menilai Jawaban"
      message="Sistem sedang menganalisis dan menilai jawaban Anda menggunakan LLM dan RAG"
      :progress="loadingProgress"
      :indeterminate="false"
    />
    
    <div class="page-header">
      <Button icon="pi pi-arrow-left" text @click="cancelSubmit" />
      <h1>Jawab Pertanyaan</h1>
    </div>

    <div v-if="questionLoading" class="loading-container">
      <ProgressSpinner />
      <p>Memuat data pertanyaan...</p>
    </div>
    
    <div v-else-if="error" class="error-container">
      <p class="error-message">{{ error }}</p>
      <Button label="Coba Lagi" icon="pi pi-refresh" @click="fetchQuestion" />
    </div>
    
    <template v-else-if="question">
      <Card class="card mb-4">
        <template #title>
          <div class="card-title">Pertanyaan</div>
        </template>
        <template #content>
          <div class="question-text">
            <p>{{ question.question_text }}</p>
          </div>
        </template>
      </Card>

      <Card class="card">
        <template #title>
          <div class="card-title">Jawaban Anda</div>
        </template>
        <template #content>
          <form @submit.prevent="submitAnswer" class="answer-form">
            <div class="form-group">
              <label for="studentName">Nama Siswa <span class="required">*</span></label>
              <InputText id="studentName" v-model="studentName" :class="{ 'p-invalid': errors.studentName }" 
                        placeholder="Masukkan nama Anda" />
              <small class="error-text" v-if="errors.studentName">{{ errors.studentName }}</small>
            </div>

            <div class="form-group">
              <label for="answerText">Jawaban <span class="required">*</span></label>
              <Textarea id="answerText" v-model="answerText" rows="8" autoResize 
                       :class="{ 'p-invalid': errors.answerText }" 
                       placeholder="Tulis jawaban esai Anda di sini..." />
              <small class="error-text" v-if="errors.answerText">{{ errors.answerText }}</small>
              <small class="help-text">Jawaban Anda akan dievaluasi secara otomatis oleh sistem AES.</small>
            </div>

            <div class="form-actions">
              <Button type="button" label="Batal" class="p-button-secondary" icon="pi pi-times" 
                     @click="cancelSubmit" :disabled="loading" />
              <Button type="submit" label="Kirim Jawaban" icon="pi pi-send" 
                     :loading="loading" />
            </div>
          </form>
        </template>
      </Card>
    </template>
  </div>
</template>

<style scoped>
.answer-question-page {
  max-width: 800px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.card-title {
  font-size: 1.2rem;
  font-weight: 600;
}

.question-text {
  line-height: 1.6;
  font-size: 1.1rem;
  white-space: pre-line;
}

.answer-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin-top: 1rem;
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

.help-text {
  color: var(--secondary-color);
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: 1rem;
}

.loading-container,
.error-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  text-align: center;
}

.error-message {
  color: #EF4444;
  margin-bottom: 1rem;
}
</style>

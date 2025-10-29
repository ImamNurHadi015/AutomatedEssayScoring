<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { examApi, questionApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import Card from 'primevue/card'
import ProgressSpinner from 'primevue/progressspinner'
import Dropdown from 'primevue/dropdown'
import { useToast } from 'primevue/usetoast'

const props = defineProps({
  examId: {
    type: String,
    required: true
  }
})

const router = useRouter()
const toast = useToast()

const exam = ref(null)
const questionText = ref('')
const questionType = ref('panjang')
const loading = ref(false)
const examLoading = ref(false)
const error = ref(null)
const errors = ref({
  questionText: '',
  questionType: ''
})

const questionTypeOptions = [
  { label: 'Soal Panjang (skor 1-4)', value: 'panjang' },
  { label: 'Soal Singkat (skor 0 atau 2)', value: 'singkat' }
]

// Ambil data ujian
const fetchExam = async () => {
  try {
    examLoading.value = true
    error.value = null
    const response = await examApi.getExam(props.examId)
    exam.value = response.data
  } catch (err) {
    console.error('Error fetching exam:', err)
    error.value = 'Gagal mengambil data ujian. Silakan coba lagi.'
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengambil data ujian',
      life: 3000
    })
  } finally {
    examLoading.value = false
  }
}

// Validasi form
const validateForm = () => {
  let isValid = true
  errors.value = {
    questionText: '',
    questionType: ''
  }

  if (!questionText.value.trim()) {
    errors.value.questionText = 'Pertanyaan harus diisi'
    isValid = false
  } else if (questionText.value.trim().length < 10) {
    errors.value.questionText = 'Pertanyaan terlalu pendek (minimal 10 karakter)'
    isValid = false
  }

  if (!questionType.value) {
    errors.value.questionType = 'Tipe soal harus dipilih'
    isValid = false
  }

  return isValid
}

// Simpan pertanyaan
const saveQuestion = async () => {
  if (!validateForm()) return

  try {
    loading.value = true
    const questionData = {
      question_text: questionText.value.trim(),
      question_type: questionType.value
    }

    await questionApi.createQuestion(props.examId, questionData)
    
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Pertanyaan berhasil dibuat',
      life: 3000
    })

    // Redirect ke halaman detail ujian
    router.push(`/exams/${props.examId}`)
  } catch (error) {
    console.error('Error creating question:', error)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal membuat pertanyaan. Silakan coba lagi.',
      life: 5000
    })
  } finally {
    loading.value = false
  }
}

// Kembali ke halaman detail ujian
const cancelCreate = () => {
  router.push(`/exams/${props.examId}`)
}

// Load data saat komponen dimount
onMounted(() => {
  fetchExam()
})
</script>

<template>
  <div class="create-question-page">
    <div class="page-header">
      <Button icon="pi pi-arrow-left" text @click="cancelCreate" />
      <h1>Tambah Pertanyaan</h1>
    </div>

    <div v-if="examLoading" class="loading-container">
      <ProgressSpinner />
      <p>Memuat data ujian...</p>
    </div>
    
    <div v-else-if="error" class="error-container">
      <p class="error-message">{{ error }}</p>
      <Button label="Coba Lagi" icon="pi pi-refresh" @click="fetchExam" />
    </div>
    
    <template v-else-if="exam">
      <Card class="card mb-4">
        <template #title>
          <div class="card-title">Ujian: {{ exam.title }}</div>
        </template>
      </Card>

      <Card class="card">
        <template #content>
          <form @submit.prevent="saveQuestion" class="question-form">
            <div class="form-group">
              <label for="questionText">Pertanyaan <span class="required">*</span></label>
              <Textarea id="questionText" v-model="questionText" rows="5" autoResize 
                       :class="{ 'p-invalid': errors.questionText }" 
                       placeholder="Masukkan pertanyaan esai di sini..." />
              <small class="error-text" v-if="errors.questionText">{{ errors.questionText }}</small>
              <small class="help-text">Buat pertanyaan yang jelas dan spesifik untuk mendapatkan jawaban esai yang baik.</small>
            </div>

            <div class="form-group">
              <label for="questionType">Tipe Soal <span class="required">*</span></label>
              <Dropdown id="questionType"
                        v-model="questionType"
                        :options="questionTypeOptions"
                        optionLabel="label"
                        optionValue="value"
                        placeholder="Pilih tipe soal"
                        :class="{ 'p-invalid': errors.questionType }" />
              <small class="error-text" v-if="errors.questionType">{{ errors.questionType }}</small>
              <small class="help-text">Tipe singkat dinilai 0 atau 2, sedangkan tipe panjang dinilai 1 sampai 4.</small>
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
    </template>
  </div>
</template>

<style scoped>
.create-question-page {
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

.question-form {
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

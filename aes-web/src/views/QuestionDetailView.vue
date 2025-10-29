<script setup>
import { ref, onMounted, watch, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { questionApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressSpinner from 'primevue/progressspinner'
import Card from 'primevue/card'
import Divider from 'primevue/divider'
import Badge from 'primevue/badge'
import Dialog from 'primevue/dialog'
import Textarea from 'primevue/textarea'
import Dropdown from 'primevue/dropdown'
import { useToast } from 'primevue/usetoast'

const props = defineProps({
  id: {
    type: String,
    required: true
  }
})

const router = useRouter()
const toast = useToast()

const question = ref(null)
const loading = ref(false)
const error = ref(null)
const editDialogVisible = ref(false)
const editDialogLoading = ref(false)
const editForm = ref({
  question_text: '',
  question_type: 'panjang'
})
const editErrors = ref({
  question_text: '',
  question_type: ''
})
const questionTypeOptions = [
  { label: 'Soal Panjang (skor 1-4)', value: 'panjang' },
  { label: 'Soal Singkat (skor 0 atau 2)', value: 'singkat' }
]

// Format tanggal
const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('id-ID', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

// Ambil data pertanyaan
const fetchQuestion = async (questionId) => {
  try {
    loading.value = true
    error.value = null
    const response = await questionApi.getQuestion(questionId)
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
    loading.value = false
  }
}

const retryFetchQuestion = () => {
  if (props.id) {
    fetchQuestion(props.id)
  }
}

// Navigasi ke halaman jawab pertanyaan
const answerQuestion = () => {
  router.push(`/questions/${props.id}/answer`)
}

// Navigasi ke halaman detail jawaban
const viewAnswer = (answer) => {
  router.push(`/answers/${answer.id}`)
}

// Kembali ke halaman detail ujian
const goBack = () => {
  if (question.value) {
    router.push(`/exams/${question.value.exam_id}`)
  } else {
    router.push('/exams')
  }
}

const openEditQuestion = () => {
  if (!question.value) return
  editForm.value = {
    question_text: question.value.question_text || '',
    question_type: question.value.question_type || 'panjang'
  }
  editErrors.value = {
    question_text: '',
    question_type: ''
  }
  editDialogVisible.value = true
}

const validateEditForm = () => {
  let isValid = true
  editErrors.value = {
    question_text: '',
    question_type: ''
  }

  const trimmedText = editForm.value.question_text.trim()
  if (!trimmedText) {
    editErrors.value.question_text = 'Pertanyaan harus diisi'
    isValid = false
  } else if (trimmedText.length < 10) {
    editErrors.value.question_text = 'Pertanyaan terlalu pendek (minimal 10 karakter)'
    isValid = false
  }

  if (!editForm.value.question_type) {
    editErrors.value.question_type = 'Tipe soal harus dipilih'
    isValid = false
  }

  return isValid
}

const saveQuestionChanges = async () => {
  if (!question.value) return
  if (!validateEditForm()) return

  const payload = {}
  const trimmedText = editForm.value.question_text.trim()
  const currentType = question.value.question_type || 'panjang'

  if (trimmedText !== question.value.question_text) {
    payload.question_text = trimmedText
  }

  if (editForm.value.question_type !== currentType) {
    payload.question_type = editForm.value.question_type
  }

  if (Object.keys(payload).length === 0) {
    editDialogVisible.value = false
    return
  }

  try {
    editDialogLoading.value = true
    await questionApi.updateQuestion(question.value.id, payload)
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Pertanyaan berhasil diperbarui',
      life: 3000
    })
    editDialogVisible.value = false
    if (props.id) {
      await fetchQuestion(props.id)
    }
  } catch (err) {
    console.error('Error updating question:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: err.response?.data?.error || 'Gagal memperbarui pertanyaan',
      life: 5000
    })
  } finally {
    editDialogLoading.value = false
  }
}

const getScoreRatio = (score, maxScore) => {
  if (score === null || score === undefined) return null
  const parsedMax = Number(maxScore)
  if (!parsedMax || parsedMax <= 0) return null
  return Number(score) / parsedMax
}

// Mendapatkan warna badge berdasarkan skor relatif terhadap skor maksimum
const getScoreBadgeClass = (score, maxScore) => {
  const ratio = getScoreRatio(score, maxScore)
  if (ratio === null) return 'bg-gray-500'
  if (ratio >= 0.95) return 'bg-green-500'
  if (ratio >= 0.75) return 'bg-blue-500'
  if (ratio >= 0.5) return 'bg-orange-500'
  if (ratio > 0) return 'bg-red-500'
  return 'bg-gray-500'
}

const formatScoreDisplay = (score, maxScore) => {
  if (score === null || score === undefined) return 'Belum dinilai'
  const parsedMax = Number(maxScore)
  if (!parsedMax || parsedMax <= 0) return `${score}`
  return `${score}/${parsedMax}`
}

const formatQuestionType = (type) => {
  if (!type) return 'Panjang (1-4)'
  const normalized = String(type).toLowerCase()
  if (normalized === 'singkat') return 'Singkat (0 atau 2)'
  return 'Panjang (1-4)'
}

const formatScoreRange = (allowedScores, maxScore) => {
  if (Array.isArray(allowedScores) && allowedScores.length > 0) {
    return allowedScores.join(', ')
  }
  if (typeof maxScore === 'number') {
    return `0 - ${maxScore}`
  }
  return '-'
}

// Load data saat komponen dimount
onMounted(() => {
  if (props.id) {
    fetchQuestion(props.id)
  }
})

onActivated(() => {
  if (props.id) {
    fetchQuestion(props.id)
  }
})

watch(
  () => props.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      fetchQuestion(newId)
    }
  }
)
</script>

<template>
  <div class="question-detail-wrapper">
    <div class="question-detail-page">
      <div class="page-header">
        <Button icon="pi pi-arrow-left" text @click="goBack" />
        <h1>Detail Pertanyaan</h1>
      </div>

      <div v-if="loading" class="loading-container">
        <ProgressSpinner />
        <p>Memuat data pertanyaan...</p>
      </div>
      
      <div v-else-if="error" class="error-container">
        <p class="error-message">{{ error }}</p>
        <Button label="Coba Lagi" icon="pi pi-refresh" @click="retryFetchQuestion" />
      </div>
      
      <template v-else-if="question">
        <Card class="card">
          <template #title>
            <div class="card-title">Pertanyaan</div>
          </template>
          <template #subtitle>
            <div class="card-subtitle">Dibuat pada: {{ formatDate(question.created_at) }}</div>
          </template>
          <template #content>
            <div class="question-text">
              <p>{{ question.question_text }}</p>
            </div>
            <div class="question-meta">
              <span class="meta-label">Tipe Soal:</span>
              <span class="meta-value">{{ formatQuestionType(question.question_type) }}</span>
            </div>
            <div class="question-meta">
              <span class="meta-label">Rentang Skor:</span>
              <span class="meta-value">{{ formatScoreRange(question.allowed_scores, question.max_score) }}</span>
            </div>
            <div class="question-actions mt-4">
              <Button label="Edit Pertanyaan" icon="pi pi-pencil" class="p-button-secondary"
                      @click="openEditQuestion" />
              <Button label="Jawab Pertanyaan" icon="pi pi-pencil" @click="answerQuestion" />
            </div>
          </template>
        </Card>

        <Divider />

        <div class="answers-section">
          <div class="section-header">
            <h2>Daftar Jawaban</h2>
          </div>

          <Card class="card">
            <template #content>
              <div v-if="question.answers.length === 0" class="empty-container">
                <p>Belum ada jawaban untuk pertanyaan ini.</p>
                <Button label="Jawab Pertanyaan" icon="pi pi-pencil" @click="answerQuestion" class="mt-4" />
              </div>
              
              <DataTable v-else :value="question.answers" stripedRows paginator :rows="5" 
                        :rowsPerPageOptions="[5, 10, 25]" tableStyle="min-width: 50rem">
                <Column field="id" header="ID" sortable style="width: 5%"></Column>
                <Column field="student_name" header="Nama Siswa" sortable style="width: 15%"></Column>
                <Column field="answer_text" header="Jawaban" style="width: 40%">
                  <template #body="slotProps">
                    <div class="answer-text">{{ slotProps.data.answer_text }}</div>
                  </template>
                </Column>
                <Column field="score" header="Skor" sortable style="width: 10%">
                  <template #body="slotProps">
                    <Badge :value="formatScoreDisplay(slotProps.data.score, slotProps.data.max_score)" 
                           :class="getScoreBadgeClass(slotProps.data.score, slotProps.data.max_score)" />
                  </template>
                </Column>
                <Column field="created_at" header="Tanggal Dibuat" sortable style="width: 20%">
                  <template #body="slotProps">
                    {{ formatDate(slotProps.data.created_at) }}
                  </template>
                </Column>
                <Column style="width: 10%">
                  <template #body="slotProps">
                    <Button icon="pi pi-eye" rounded text aria-label="Lihat" @click="viewAnswer(slotProps.data)" />
                  </template>
                </Column>
              </DataTable>
            </template>
          </Card>
        </div>
      </template>
    </div>

    <Dialog v-model:visible="editDialogVisible"
            header="Edit Pertanyaan"
            :modal="true"
            :style="{ width: '520px' }"
            :breakpoints="{ '960px': '90vw', '640px': '95vw' }">
      <div class="dialog-body">
        <div class="form-group">
          <label for="editQuestionText">Teks Pertanyaan <span class="required">*</span></label>
          <Textarea id="editQuestionText"
                    v-model="editForm.question_text"
                    rows="6"
                    autoResize
                    :class="{ 'p-invalid': editErrors.question_text }"
                    placeholder="Masukkan teks pertanyaan" />
          <small class="error-text" v-if="editErrors.question_text">{{ editErrors.question_text }}</small>
        </div>

        <div class="form-group">
          <label for="editQuestionType">Tipe Soal <span class="required">*</span></label>
          <Dropdown id="editQuestionType"
                    v-model="editForm.question_type"
                    :options="questionTypeOptions"
                    optionLabel="label"
                    optionValue="value"
                    placeholder="Pilih tipe soal"
                    :class="{ 'p-invalid': editErrors.question_type }" />
          <small class="error-text" v-if="editErrors.question_type">{{ editErrors.question_type }}</small>
        </div>
      </div>

      <template #footer>
        <Button label="Batal" icon="pi pi-times" class="p-button-text"
               @click="editDialogVisible = false" :disabled="editDialogLoading" />
        <Button label="Simpan" icon="pi pi-save" :loading="editDialogLoading"
               @click="saveQuestionChanges" />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.question-detail-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.card-title {
  font-size: 1.5rem;
  font-weight: 600;
}

.card-subtitle {
  color: var(--secondary-color);
}

.question-text {
  margin-top: 1rem;
  line-height: 1.6;
  font-size: 1.1rem;
  white-space: pre-line;
}

.question-meta {
  margin-top: 0.75rem;
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
  font-size: 0.95rem;
}

.question-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.meta-label {
  font-weight: 600;
  color: var(--secondary-color);
}

.meta-value {
  color: var(--primary-color);
}

.answers-section {
  margin-top: 2rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.answer-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 400px;
}

.loading-container,
.error-container,
.empty-container {
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

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.required {
  color: #EF4444;
}

.error-text {
  color: #EF4444;
  font-size: 0.9rem;
}

/* Badge colors */
.bg-green-500 {
  background-color: #10B981 !important;
}

.bg-blue-500 {
  background-color: #3B82F6 !important;
}

.bg-orange-500 {
  background-color: #F59E0B !important;
}

.bg-red-500 {
  background-color: #EF4444 !important;
}

.bg-gray-500 {
  background-color: #6B7280 !important;
}
</style>

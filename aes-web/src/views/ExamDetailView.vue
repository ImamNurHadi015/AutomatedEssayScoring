<script setup>
import { ref, onMounted, watch, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { examApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressSpinner from 'primevue/progressspinner'
import Card from 'primevue/card'
import Divider from 'primevue/divider'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import { useToast } from 'primevue/usetoast'

const props = defineProps({
  id: {
    type: String,
    required: true
  }
})

const router = useRouter()
const toast = useToast()

const exam = ref(null)
const loading = ref(false)
const error = ref(null)
const editExamDialogVisible = ref(false)
const editExamLoading = ref(false)
const editExamForm = ref({
  title: '',
  description: ''
})
const editExamErrors = ref({
  title: ''
})

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

const formatQuestionType = (type, allowedScores, maxScore) => {
  if (!type) return formatScoreRange(allowedScores, maxScore)
  const normalized = String(type).toLowerCase()
  if (normalized === 'singkat') return 'Singkat (0 atau 2)'
  return 'Panjang (1-4)'
}

const formatScoreRange = (allowedScores, maxScore) => {
  if (Array.isArray(allowedScores) && allowedScores.length > 0) {
    return `Skor: ${allowedScores.join(', ')}`
  }
  if (typeof maxScore === 'number') {
    return `Skor 0 hingga ${maxScore}`
  }
  return 'Skor tidak tersedia'
}

// Ambil data ujian
const fetchExam = async (examId) => {
  try {
    loading.value = true
    error.value = null
    const response = await examApi.getExam(examId)
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
    loading.value = false
  }
}

// Navigasi ke halaman buat pertanyaan
const createQuestion = () => {
  router.push(`/exams/${props.id}/questions/create`)
}

// Navigasi ke halaman detail pertanyaan
const viewQuestion = (question) => {
  router.push(`/questions/${question.id}`)
}

// Kembali ke halaman daftar ujian
const goBack = () => {
  router.push('/exams')
}

const retryFetchExam = () => {
  if (props.id) {
    fetchExam(props.id)
  }
}

const openEditExam = () => {
  if (!exam.value) return
  editExamForm.value = {
    title: exam.value.title || '',
    description: exam.value.description || ''
  }
  editExamErrors.value = { title: '' }
  editExamDialogVisible.value = true
}

const validateExamForm = () => {
  editExamErrors.value = { title: '' }
  if (!editExamForm.value.title.trim()) {
    editExamErrors.value.title = 'Judul ujian harus diisi'
    return false
  }
  return true
}

const saveExamChanges = async () => {
  if (!exam.value) return
  if (!validateExamForm()) return

  const payload = {}
  const trimmedTitle = editExamForm.value.title.trim()
  const trimmedDescription = editExamForm.value.description.trim()

  if (trimmedTitle !== exam.value.title) {
    payload.title = trimmedTitle
  }
  if ((exam.value.description || '') !== trimmedDescription) {
    payload.description = trimmedDescription
  }

  if (Object.keys(payload).length === 0) {
    editExamDialogVisible.value = false
    return
  }

  try {
    editExamLoading.value = true
    const response = await examApi.updateExam(props.id, payload)
    exam.value = {
      ...exam.value,
      title: response.data.title,
      description: response.data.description
    }
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Data ujian berhasil diperbarui',
      life: 3000
    })
    editExamDialogVisible.value = false
  } catch (err) {
    console.error('Error updating exam:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: err.response?.data?.error || 'Gagal memperbarui ujian',
      life: 5000
    })
  } finally {
    editExamLoading.value = false
  }
}

// Load data saat komponen dimount
onMounted(() => {
  if (props.id) {
    fetchExam(props.id)
  }
})

onActivated(() => {
  if (props.id) {
    fetchExam(props.id)
  }
})

watch(
  () => props.id,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      fetchExam(newId)
    }
  }
)
</script>

<template>
  <div class="exam-detail-wrapper">
    <div class="exam-detail-page">
      <div class="page-header">
        <div class="header-left">
          <Button icon="pi pi-arrow-left" text @click="goBack" />
          <h1>Detail Ujian</h1>
        </div>
        <Button label="Edit Ujian" icon="pi pi-pencil" @click="openEditExam" :disabled="!exam" />
      </div>

      <div v-if="loading" class="loading-container">
        <ProgressSpinner />
        <p>Memuat data ujian...</p>
      </div>
      
      <div v-else-if="error" class="error-container">
        <p class="error-message">{{ error }}</p>
        <Button label="Coba Lagi" icon="pi pi-refresh" @click="retryFetchExam" />
      </div>
      
      <template v-else-if="exam">
        <Card class="card">
          <template #title>
            <div class="card-title">{{ exam.title }}</div>
          </template>
          <template #subtitle>
            <div class="card-subtitle">Dibuat pada: {{ formatDate(exam.created_at) }}</div>
          </template>
          <template #content>
            <div class="exam-description">
              <p>{{ exam.description || 'Tidak ada deskripsi' }}</p>
            </div>
          </template>
        </Card>

        <Divider />

        <div class="questions-section">
          <div class="section-header">
            <h2>Daftar Pertanyaan</h2>
            <Button label="Tambah Pertanyaan" icon="pi pi-plus" @click="createQuestion" />
          </div>

          <Card class="card">
            <template #content>
              <div v-if="exam.questions.length === 0" class="empty-container">
                <p>Belum ada pertanyaan yang dibuat untuk ujian ini.</p>
                <Button label="Tambah Pertanyaan" icon="pi pi-plus" @click="createQuestion" class="mt-4" />
              </div>
              
              <DataTable v-else :value="exam.questions" stripedRows paginator :rows="5" 
                        :rowsPerPageOptions="[5, 10, 25]" tableStyle="min-width: 50rem">
                <Column field="id" header="ID" sortable style="width: 5%"></Column>
                <Column field="question_text" header="Pertanyaan" style="width: 60%">
                  <template #body="slotProps">
                    <div class="question-text">{{ slotProps.data.question_text }}</div>
                  </template>
                </Column>
                <Column field="question_type" header="Tipe Soal" style="width: 15%">
                  <template #body="slotProps">
                    <div class="question-type">
                      {{ formatQuestionType(slotProps.data.question_type, slotProps.data.allowed_scores, slotProps.data.max_score) }}
                    </div>
                    <small class="score-range">
                      {{ formatScoreRange(slotProps.data.allowed_scores, slotProps.data.max_score) }}
                    </small>
                  </template>
                </Column>
                <Column field="answer_count" header="Jumlah Jawaban" sortable style="width: 15%"></Column>
                <Column field="created_at" header="Tanggal Dibuat" sortable style="width: 20%">
                  <template #body="slotProps">
                    {{ formatDate(slotProps.data.created_at) }}
                  </template>
                </Column>
                <Column style="width: 10%">
                  <template #body="slotProps">
                    <div class="action-button-wrapper">
                      <Button icon="pi pi-eye" rounded text aria-label="Lihat" @click="viewQuestion(slotProps.data)" />
                    </div>
                  </template>
                </Column>
              </DataTable>
            </template>
          </Card>
        </div>
      </template>
    </div>

    <Dialog v-model:visible="editExamDialogVisible"
            header="Edit Ujian"
            :modal="true"
            :style="{ width: '450px' }"
            :breakpoints="{ '960px': '90vw', '640px': '95vw' }">
      <div class="dialog-body">
        <div class="form-group">
          <label for="examTitle">Judul Ujian <span class="required">*</span></label>
          <InputText id="examTitle"
                     v-model="editExamForm.title"
                     :class="{ 'p-invalid': editExamErrors.title }"
                     placeholder="Masukkan judul ujian" />
          <small class="error-text" v-if="editExamErrors.title">{{ editExamErrors.title }}</small>
        </div>

        <div class="form-group">
          <label for="examDescription">Deskripsi</label>
          <Textarea id="examDescription"
                    v-model="editExamForm.description"
                    rows="4"
                    autoResize
                    placeholder="Masukkan deskripsi ujian (opsional)" />
        </div>
      </div>

      <template #footer>
        <Button label="Batal" icon="pi pi-times" class="p-button-text"
               @click="editExamDialogVisible = false" :disabled="editExamLoading" />
        <Button label="Simpan" icon="pi pi-save" :loading="editExamLoading"
               @click="saveExamChanges" />
      </template>
    </Dialog>
  </div>
</template>

<style scoped>
.exam-detail-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.card-title {
  font-size: 1.5rem;
  font-weight: 600;
}

.card-subtitle {
  color: var(--secondary-color);
}

.exam-description {
  margin-top: 1rem;
  line-height: 1.6;
}

.questions-section {
  margin-top: 2rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.question-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 500px;
}

.question-type {
  font-weight: 600;
}

.score-range {
  display: block;
  color: var(--secondary-color);
  font-size: 0.85rem;
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

.action-button-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 40px;
  background-color: rgba(255, 255, 255, 0.5);
}
</style>
.required {
  color: #EF4444;
}

.error-text {
  color: #EF4444;
  font-size: 0.9rem;
}

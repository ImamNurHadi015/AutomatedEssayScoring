<template>
  <div class="student-results-page">
    <Toast />
    
    <div v-if="loading" class="loading-container card">
      <ProgressSpinner />
      <p>Memuat hasil siswa...</p>
    </div>
    
    <div v-else-if="error" class="error-container card">
      <p class="error-message">{{ error }}</p>
      <Button label="Kembali" icon="pi pi-arrow-left" @click="navigateBack" />
    </div>
    
    <template v-else>
      <div class="page-header">
        <div class="header-content">
          <h1>Hasil Per Siswa</h1>
          <p class="page-subtitle">
            Sesi: <span class="session-code">{{ session.session_code }}</span> - {{ session.exam_title }}
          </p>
        </div>
        <div class="header-actions">
          <Button label="Kembali ke History" icon="pi pi-arrow-left" @click="navigateToHistory" 
                 class="p-button-secondary" />
        </div>
      </div>
      
      <Card class="card filter-card">
        <template #content>
          <div class="filter-container">
            <div class="filter-item">
              <label>Pilih Siswa:</label>
              <Dropdown v-model="selectedStudentId" :options="studentOptions" optionLabel="name" optionValue="id" 
                       placeholder="Semua Siswa" class="w-full" @change="filterResults" />
            </div>
            
            <div class="filter-item">
              <label>Urutkan Berdasarkan:</label>
              <Dropdown v-model="sortOption" :options="sortOptions" optionLabel="label" optionValue="value" 
                       placeholder="Skor Tertinggi" class="w-full" @change="sortResults" />
            </div>
          </div>
        </template>
      </Card>
      
      <div v-if="filteredResults.length > 0" class="results-container">
        <div v-for="student in filteredResults" :key="student.id" class="student-result-card card">
          <div class="student-header">
            <h3>{{ student.name }}</h3>
            <div class="student-score">
              <span class="score-label">Rata-rata:</span>
              <span class="score-value">{{ formatAverageScore(student) }}</span>
            </div>
          </div>
          
          <Divider />
          
          <div class="answers-container">
            <div v-for="answer in student.answers" :key="answer.question_id" class="answer-item">
              <div class="question-text">
                {{ answer.question_text }}
                <div class="question-meta">
                  <span class="meta-label">Ujian:</span>
                  <span class="meta-value">{{ answer.exam_title || 'Tidak diketahui' }}</span>
                  <span class="meta-separator">•</span>
                  <span class="meta-label">Tipe:</span>
                  <span class="meta-value">{{ formatQuestionType(answer.question_type) }}</span>
                  <span class="meta-separator">•</span>
                  <span class="meta-label">Skor:</span>
                  <span class="meta-value">{{ formatScoreRange(answer.allowed_scores, answer.max_score) }}</span>
                </div>
              </div>
              
              <div class="answer-details">
                <div class="answer-text">
                  <div class="answer-label">Jawaban:</div>
                  <div class="answer-content">{{ answer.answer_text }}</div>
                </div>
                
                <div class="evaluation-container">
                  <div class="evaluation-header">
                    <div class="evaluation-label">Evaluasi:</div>
                    <div class="evaluation-score">
                      <Tag :severity="getScoreSeverity(answer.score, answer.max_score)"
                           :value="`Skor: ${formatScoreDisplay(answer.score, answer.max_score)}`" />
                    </div>
                  </div>
                  <div class="evaluation-content">{{ answer.evaluation }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div v-else class="empty-results card">
        <p>Tidak ada hasil yang sesuai dengan filter.</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { sessionApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import Divider from 'primevue/divider'
import Dropdown from 'primevue/dropdown'
import ProgressSpinner from 'primevue/progressspinner'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const route = useRoute()
const toast = useToast()

const session = ref({})
const studentResults = ref([])
const filteredResults = ref([])
const loading = ref(true)
const error = ref(null)

const selectedStudentId = ref(null)
const sortOption = ref('score_desc')

const sortOptions = [
  { label: 'Skor Tertinggi', value: 'score_desc' },
  { label: 'Skor Terendah', value: 'score_asc' },
  { label: 'Nama (A-Z)', value: 'name_asc' },
  { label: 'Nama (Z-A)', value: 'name_desc' }
]

const sessionId = computed(() => route.params.id)

const studentOptions = computed(() => {
  const options = studentResults.value.map(student => ({
    id: student.id,
    name: student.name
  }))
  
  // Sort by name
  return options.sort((a, b) => a.name.localeCompare(b.name))
})

const getScoreRatio = (score, maxScore) => {
  if (score === null || score === undefined) return null
  const parsedMax = Number(maxScore)
  if (!parsedMax || parsedMax <= 0) return null
  return Number(score) / parsedMax
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

const formatAverageScore = (student) => {
  if (!student) return '-'
  const percentage = typeof student.average_percentage === 'number'
    ? `${Math.round(student.average_percentage * 100)}%`
    : null
  const totalDisplay = student.total_max_score
    ? `${student.total_score}/${student.total_max_score}`
    : null

  if (percentage && totalDisplay) {
    return `${percentage} (${totalDisplay})`
  }
  if (percentage) {
    return percentage
  }
  if (student.question_count) {
    return student.average_score.toFixed(2)
  }
  return '-'
}

// Mendapatkan data siswa dan hasil
const fetchStudentResults = async () => {
  try {
    loading.value = true
    error.value = null
    
    // Ambil detail sesi
    const sessionResponse = await sessionApi.getSession(sessionId.value)
    session.value = sessionResponse.data
    
    // Ambil hasil per siswa
    const resultsResponse = await sessionApi.getSessionSummary(sessionId.value)
    studentResults.value = resultsResponse.data.student_results || []
    
    // Terapkan filter dan sorting default
    filterResults()
  } catch (err) {
    console.error('Error fetching student results:', err)
    error.value = `Gagal mendapatkan hasil siswa: ${err.response?.data?.error || 'Terjadi kesalahan'}`
  } finally {
    loading.value = false
  }
}

// Filter hasil berdasarkan siswa yang dipilih
const filterResults = () => {
  if (!selectedStudentId.value) {
    // Tampilkan semua siswa
    filteredResults.value = [...studentResults.value]
  } else {
    // Filter berdasarkan ID siswa
    filteredResults.value = studentResults.value.filter(student => 
      student.id === selectedStudentId.value
    )
  }
  
  // Terapkan sorting
  sortResults()
}

// Urutkan hasil
const sortResults = () => {
  switch (sortOption.value) {
    case 'score_desc':
      filteredResults.value.sort((a, b) => 
        (b.average_percentage || 0) - (a.average_percentage || 0)
      )
      break
    case 'score_asc':
      filteredResults.value.sort((a, b) => 
        (a.average_percentage || 0) - (b.average_percentage || 0)
      )
      break
    case 'name_asc':
      filteredResults.value.sort((a, b) => 
        a.name.localeCompare(b.name)
      )
      break
    case 'name_desc':
      filteredResults.value.sort((a, b) => 
        b.name.localeCompare(a.name)
      )
      break
  }
}

// Mendapatkan severity untuk tag skor
const getScoreSeverity = (score, maxScore) => {
  const ratio = getScoreRatio(score, maxScore)
  if (ratio === null) return 'info'
  if (ratio >= 0.9) return 'success'
  if (ratio >= 0.7) return 'info'
  if (ratio >= 0.5) return 'warning'
  return 'danger'
}

const navigateBack = () => {
  router.push(`/sessions/${sessionId.value}/results`)
}

const navigateToHistory = () => {
  router.push('/sessions/history')
}

// Watch untuk perubahan filter
watch([selectedStudentId, sortOption], () => {
  filterResults()
})

onMounted(() => {
  fetchStudentResults()
})
</script>

<style scoped>
.student-results-page {
  max-width: 1000px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.5rem;
}

.page-subtitle {
  color: var(--secondary-color);
  margin-top: 0.5rem;
}

.session-code {
  font-weight: bold;
  color: var(--primary-color);
  background-color: #f0f9ff;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
}

.filter-card {
  margin-bottom: 1.5rem;
}

.filter-container {
  display: flex;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.filter-item {
  flex: 1;
  min-width: 200px;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.filter-item label {
  font-weight: 600;
  color: var(--secondary-color);
  font-size: 0.9rem;
}

.results-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.student-result-card {
  padding: 1.5rem;
}

.student-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.student-score {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.score-label {
  color: var(--secondary-color);
}

.score-value {
  font-weight: bold;
  font-size: 1.2rem;
  color: var(--primary-color);
}

.answers-container {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  margin-top: 1rem;
}

.answer-item {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1rem;
  background-color: #f8fafc;
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.question-text {
  font-weight: 600;
}

.question-meta {
  margin-top: 0.35rem;
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
  font-size: 0.9rem;
}

.meta-label {
  font-weight: 600;
  color: var(--secondary-color);
}

.meta-value {
  color: var(--primary-color);
}

.meta-separator {
  color: var(--secondary-color);
}

.answer-details {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.answer-text, .evaluation-container {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.answer-label, .evaluation-label {
  font-weight: 600;
  color: var(--secondary-color);
  font-size: 0.9rem;
}

.answer-content {
  white-space: pre-line;
  background-color: white;
  padding: 0.75rem;
  border-radius: 4px;
  border: 1px solid var(--border-color);
}

.evaluation-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.evaluation-content {
  white-space: pre-line;
  background-color: white;
  padding: 0.75rem;
  border-radius: 4px;
  border: 1px solid var(--border-color);
}

.empty-results {
  text-align: center;
  padding: 2rem;
  color: var(--secondary-color);
}

.loading-container,
.error-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem;
  text-align: center;
  margin-top: 2rem;
}

.error-message {
  color: #EF4444;
  margin-bottom: 1rem;
}

.w-full {
  width: 100%;
}
</style>

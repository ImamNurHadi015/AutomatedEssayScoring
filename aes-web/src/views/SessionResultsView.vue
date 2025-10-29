<template>
  <div class="session-results-page">
    <Toast />
    
    <div v-if="loading" class="loading-container card">
      <ProgressSpinner />
      <p>Memuat hasil sesi ujian...</p>
    </div>
    
    <div v-else-if="error" class="error-container card">
      <p class="error-message">{{ error }}</p>
      <Button label="Kembali" icon="pi pi-arrow-left" @click="navigateBack" />
    </div>
    
    <template v-else>
      <div class="page-header">
        <div class="header-content">
          <h1>Hasil Sesi Ujian: {{ summary.exam_title }}</h1>
          <p class="page-subtitle">
            Kode Sesi: <span class="session-code">{{ summary.session_code }}</span>
          </p>
        </div>
        <div class="header-actions">
          <Button label="Kembali ke Sesi" icon="pi pi-arrow-left" @click="navigateBack" 
                 class="p-button-secondary" />
        </div>
      </div>
      
      <Card class="card">
        <template #title>
          <div class="card-title">Ringkasan Hasil</div>
        </template>
        <template #content>
          <div class="summary-info">
            <div class="info-item">
              <div class="info-label">Ujian</div>
              <div class="info-value">{{ summary.exam_title }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Jumlah Siswa</div>
              <div class="info-value">{{ summary.total_students }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Status</div>
              <div class="info-value">
                <Tag :severity="summary.is_completed ? 'success' : 'info'" 
                     :value="summary.is_completed ? 'Selesai' : 'Berlangsung'" />
              </div>
            </div>
          </div>
        </template>
      </Card>
      
      <div v-if="summary.student_results && summary.student_results.length > 0" class="results-container">
        <h2>Hasil Per Siswa</h2>
        
        <div v-for="student in summary.student_results" :key="student.name" class="student-result-card card">
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
                
                <div class="rag-comparison">
                  <Button label="Lihat Referensi RAG" icon="pi pi-search" 
                         @click="viewRagComparison(answer.question_text)" 
                         class="p-button-sm p-button-text" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div v-else class="empty-results card">
        <p>Belum ada hasil untuk sesi ini.</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { sessionApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import Divider from 'primevue/divider'
import ProgressSpinner from 'primevue/progressspinner'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const route = useRoute()
const toast = useToast()

const summary = ref(null)
const loading = ref(true)
const error = ref(null)

const sessionId = computed(() => route.params.id)

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

// Mendapatkan ringkasan sesi
const fetchSessionSummary = async () => {
  try {
    loading.value = true
    error.value = null
    
    const response = await sessionApi.getSessionSummary(sessionId.value)
    summary.value = response.data
  } catch (err) {
    console.error('Error fetching session summary:', err)
    error.value = `Gagal mendapatkan ringkasan sesi: ${err.response?.data?.error || 'Terjadi kesalahan'}`
  } finally {
    loading.value = false
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

// Melihat perbandingan RAG
const viewRagComparison = (question) => {
  // Simpan pertanyaan di localStorage untuk digunakan di halaman compare-rag
  localStorage.setItem('compare_rag_question', question)
  router.push('/compare-rag')
}

const navigateBack = () => {
  router.push(`/sessions/${sessionId.value}`)
}

onMounted(() => {
  fetchSessionSummary()
})
</script>

<style scoped>
.session-results-page {
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

.card-title {
  font-size: 1.2rem;
  font-weight: 600;
}

.summary-info {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1.5rem;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.info-label {
  font-weight: 600;
  color: var(--secondary-color);
  font-size: 0.9rem;
}

.info-value {
  font-size: 1.1rem;
}

.results-container {
  margin-top: 2rem;
}

.student-result-card {
  margin-bottom: 1.5rem;
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

.rag-comparison {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.5rem;
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
</style>

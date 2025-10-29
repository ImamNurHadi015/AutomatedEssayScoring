<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { answerApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import ProgressSpinner from 'primevue/progressspinner'
import Card from 'primevue/card'
import Divider from 'primevue/divider'
import Badge from 'primevue/badge'
import TabView from 'primevue/tabview'
import TabPanel from 'primevue/tabpanel'
import { useToast } from 'primevue/usetoast'

const props = defineProps({
  id: {
    type: String,
    required: true
  }
})

const router = useRouter()
const toast = useToast()

const answer = ref(null)
const loading = ref(false)
const evaluateLoading = ref(false)
const error = ref(null)

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

// Ambil data jawaban
const fetchAnswer = async () => {
  try {
    loading.value = true
    error.value = null
    const response = await answerApi.getAnswer(props.id)
    answer.value = response.data
  } catch (err) {
    console.error('Error fetching answer:', err)
    error.value = 'Gagal mengambil data jawaban. Silakan coba lagi.'
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengambil data jawaban',
      life: 3000
    })
  } finally {
    loading.value = false
  }
}

// Evaluasi ulang jawaban
const evaluateAnswer = async () => {
  try {
    evaluateLoading.value = true
    const response = await answerApi.evaluateAnswer(props.id)
    answer.value = response.data
    
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Jawaban berhasil dievaluasi ulang',
      life: 3000
    })
  } catch (error) {
    console.error('Error evaluating answer:', error)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengevaluasi ulang jawaban',
      life: 5000
    })
  } finally {
    evaluateLoading.value = false
  }
}

// Kembali ke halaman detail pertanyaan
const goBack = () => {
  if (answer.value) {
    router.push(`/questions/${answer.value.question_id}`)
  } else {
    router.push('/exams')
  }
}

// Bandingkan RAG
const compareRag = () => {
  router.push('/compare-rag')
}

// Mendapatkan warna badge berdasarkan skor
const getScoreRatio = (score, maxScore) => {
  if (score === null || score === undefined) return null
  const parsedMax = Number(maxScore)
  if (!parsedMax || parsedMax <= 0) return null
  return Number(score) / parsedMax
}

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
  fetchAnswer()
})
</script>

<template>
  <div class="answer-detail-page">
    <div class="page-header">
      <Button icon="pi pi-arrow-left" text @click="goBack" />
      <h1>Detail Jawaban</h1>
    </div>

    <div v-if="loading" class="loading-container">
      <ProgressSpinner />
      <p>Memuat data jawaban...</p>
    </div>
    
    <div v-else-if="error" class="error-container">
      <p class="error-message">{{ error }}</p>
      <Button label="Coba Lagi" icon="pi pi-refresh" @click="fetchAnswer" />
    </div>
    
    <template v-else-if="answer">
      <div class="answer-header card">
        <div class="student-info">
          <h2>{{ answer.student_name }}</h2>
          <div class="answer-meta">
            <span>Dikirim pada: {{ formatDate(answer.created_at) }}</span>
            <span v-if="answer.evaluated_at">
              | Dievaluasi pada: {{ formatDate(answer.evaluated_at) }}
            </span>
          </div>
        </div>
        
        <div class="score-display">
          <div class="score-value">
            <Badge :value="formatScoreDisplay(answer.score, answer.max_score)"
                   :class="getScoreBadgeClass(answer.score, answer.max_score)" size="large" />
          </div>
          <div class="score-details">
            <div class="score-info">
              <span class="score-label">Tipe Soal:</span>
              <span class="score-data">{{ formatQuestionType(answer.question_type) }}</span>
            </div>
            <div class="score-info">
              <span class="score-label">Rentang Skor:</span>
              <span class="score-data">{{ formatScoreRange(answer.allowed_scores, answer.max_score) }}</span>
            </div>
          </div>
          
          <div class="score-actions">
            <Button v-if="answer.score !== null" label="Evaluasi Ulang" icon="pi pi-refresh" 
                   @click="evaluateAnswer" :loading="evaluateLoading" class="p-button-outlined" />
            <Button v-else label="Evaluasi" icon="pi pi-check" 
                   @click="evaluateAnswer" :loading="evaluateLoading" />
          </div>
        </div>
      </div>

      <div class="content-section">
        <TabView>
          <TabPanel header="Jawaban & Evaluasi">
            <div class="answer-content card">
              <h3>Jawaban Siswa</h3>
              <div class="answer-text">
                <p>{{ answer.answer_text }}</p>
              </div>
            </div>

            <Divider />

            <div class="evaluation-content card" v-if="answer.evaluation">
              <h3>Hasil Evaluasi</h3>
              <div class="evaluation-text">
                <pre>{{ answer.evaluation }}</pre>
              </div>
            </div>

            <div class="no-evaluation card" v-else>
              <p>Belum ada evaluasi untuk jawaban ini.</p>
              <Button label="Evaluasi Sekarang" icon="pi pi-check" 
                     @click="evaluateAnswer" :loading="evaluateLoading" />
            </div>
          </TabPanel>

          <TabPanel header="Referensi">
            <div class="references-content card">
              <div class="references-header">
                <h3>Referensi yang Digunakan</h3>
                <Button label="Bandingkan RAG" icon="pi pi-chart-bar" 
                       @click="compareRag" class="p-button-outlined" />
              </div>
              
              <div v-if="answer.references && answer.references.length > 0" class="references-list">
                <div v-for="(reference, index) in answer.references" :key="index" class="reference-item">
                  <h4>Referensi {{ index + 1 }}</h4>
                  <div class="reference-text">
                    <p>{{ reference }}</p>
                  </div>
                </div>
              </div>
              
              <div v-else class="no-references">
                <p>Tidak ada referensi yang tersedia.</p>
              </div>
            </div>
          </TabPanel>
        </TabView>
      </div>
    </template>
  </div>
</template>

<style scoped>
.answer-detail-page {
  max-width: 1000px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.answer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem;
  margin-bottom: 2rem;
}

.student-info h2 {
  font-size: 1.5rem;
  margin-bottom: 0.5rem;
}

.answer-meta {
  color: var(--secondary-color);
  font-size: 0.9rem;
}

.score-display {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.score-value {
  font-size: 2rem;
  font-weight: bold;
}

.score-details {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.35rem;
  text-align: center;
}

.score-info {
  display: flex;
  gap: 0.5rem;
  font-size: 0.95rem;
}

.score-label {
  font-weight: 600;
  color: var(--secondary-color);
}

.score-data {
  color: var(--primary-color);
}

.score-actions {
  display: flex;
  gap: 0.75rem;
}

.content-section {
  margin-top: 1rem;
}

.answer-content,
.evaluation-content,
.references-content,
.no-evaluation {
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.answer-content h3,
.evaluation-content h3,
.references-content h3 {
  margin-bottom: 1rem;
  color: var(--primary-color);
}

.answer-text,
.evaluation-text,
.reference-text {
  line-height: 1.6;
  white-space: pre-line;
}

.evaluation-text pre {
  font-family: inherit;
  white-space: pre-line;
}

.references-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.reference-item {
  margin-bottom: 1.5rem;
  padding-bottom: 1.5rem;
  border-bottom: 1px solid var(--border-color);
}

.reference-item:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.reference-item h4 {
  margin-bottom: 0.5rem;
  color: var(--secondary-color);
}

.no-evaluation,
.no-references {
  text-align: center;
  padding: 2rem;
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

@media (max-width: 768px) {
  .answer-header {
    flex-direction: column;
    gap: 1.5rem;
  }
  
  .score-display {
    width: 100%;
    flex-direction: column;
    justify-content: center;
  }
}
</style>

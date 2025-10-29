<script setup>
import { ref, onMounted } from 'vue'
import { ragApi, examApi, systemApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Card from 'primevue/card'
import ProgressSpinner from 'primevue/progressspinner'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Chart from 'primevue/chart'
import TabView from 'primevue/tabview'
import TabPanel from 'primevue/tabpanel'
import Dropdown from 'primevue/dropdown'
import { useToast } from 'primevue/usetoast'

const toast = useToast()

const question = ref('')
const selectedExam = ref(null)
const selectedQuestion = ref(null)
const questions = ref([])
const exams = ref([])
const loading = ref(false)
const examsLoading = ref(false)
const questionsLoading = ref(false)
const results = ref(null)
const error = ref(null)
const chartData = ref(null)
const chartOptions = ref({
  plugins: {
    legend: {
      labels: {
        usePointStyle: true,
        color: '#495057'
      }
    }
  },
  scales: {
    r: {
      pointLabels: {
        color: '#495057',
      },
      grid: {
        color: '#ebedef',
      },
      angleLines: {
        color: '#ebedef'
      }
    }
  }
})

// Mendapatkan daftar ujian
const fetchExams = async () => {
  try {
    examsLoading.value = true
    const response = await examApi.getExams()
    
    exams.value = (response.data || []).map(exam => ({
      id: exam.id,
      title: exam.title,
      description: exam.description || '',
      created_at: exam.created_at,
      question_count: exam.question_count ?? 0
    }))
  } catch (err) {
    console.error('Error fetching exams:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengambil daftar ujian',
      life: 3000
    })
  } finally {
    examsLoading.value = false
  }
}

// Mendapatkan pertanyaan untuk ujian terpilih
const fetchExamQuestions = async (exam) => {
  if (!exam) {
    questions.value = []
    return
  }
  
  try {
    questionsLoading.value = true
    const response = await examApi.getExamQuestions(exam.id)
    
    questions.value = (response.data || []).map(q => ({
      id: q.id,
      text: q.question_text,
      examId: exam.id,
      examTitle: exam.title,
      value: q.question_text
    }))
    
    if ((questions.value || []).length === 0) {
      toast.add({
        severity: 'info',
        summary: 'Informasi',
        detail: `Ujian "${exam.title}" belum memiliki pertanyaan.`,
        life: 3000
      })
    }
  } catch (err) {
    console.error('Error fetching exam questions:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengambil pertanyaan untuk ujian terpilih',
      life: 3000
    })
    questions.value = []
  } finally {
    questionsLoading.value = false
  }
}

// Saat ujian dipilih dari dropdown
const onExamSelected = async () => {
  selectedQuestion.value = null
  question.value = ''
  results.value = null
  error.value = null
  chartData.value = null
  questions.value = []
  
  if (!selectedExam.value) {
    return
  }
  
  await fetchExamQuestions(selectedExam.value)
}

// Saat pertanyaan dipilih dari dropdown
const onQuestionSelected = () => {
  if (selectedQuestion.value) {
    question.value = selectedQuestion.value.text
  } else {
    question.value = ''
  }
}

// Bandingkan RAG
const compareRag = async () => {
  // Gunakan pertanyaan dari input text atau dropdown
  const questionText = selectedQuestion.value ? selectedQuestion.value.text : question.value.trim()
  
  if (!questionText) {
    toast.add({
      severity: 'warn',
      summary: 'Peringatan',
      detail: 'Silakan pilih atau masukkan pertanyaan terlebih dahulu',
      life: 3000
    })
    return
  }

  try {
    loading.value = true
    error.value = null
    console.log('Mengirim permintaan perbandingan RAG dengan pertanyaan:', questionText)
    
    const response = await ragApi.compareRag(questionText)
    console.log('Respons perbandingan RAG:', response.data)
    
    if (response.data.error) {
      throw new Error(response.data.error)
    }
    
    results.value = response.data
    
    // Periksa apakah data yang diperlukan untuk chart tersedia
    if (!results.value.bm25_results || !results.value.dpr_results) {
      console.error('Data hasil tidak lengkap:', results.value)
      throw new Error('Data hasil tidak lengkap')
    }
    
    // Persiapkan data untuk chart
    prepareChartData()
    
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Perbandingan RAG berhasil dilakukan',
      life: 3000
    })
  } catch (err) {
    console.error('Error comparing RAG:', err)
    error.value = `Gagal membandingkan RAG: ${err.message || 'Terjadi kesalahan pada server'}`
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: `Gagal membandingkan RAG: ${err.message || 'Silakan coba lagi'}`,
      life: 5000
    })
  } finally {
    loading.value = false
  }
}

// Persiapkan data untuk chart
const prepareChartData = () => {
  if (!results.value) return
  
  try {
    console.log('Mempersiapkan data chart dari hasil:', results.value)
    
    // Periksa apakah data yang diperlukan tersedia
    if (!Array.isArray(results.value.bm25_results) || !Array.isArray(results.value.dpr_results)) {
      console.error('Data hasil tidak valid untuk chart:', results.value)
      return
    }
    
    // Gunakan skor yang sudah dinormalisasi jika tersedia
    const bm25Scores = results.value.bm25_results.map(item => item.score || 0)
    const dprScores = results.value.dpr_results.map(item => item.score || 0)
    
    // Tampilkan informasi normalisasi
    const isNormalized = results.value.normalized === true
    console.log(`Skor ${isNormalized ? 'telah dinormalisasi' : 'belum dinormalisasi'}`)
    console.log('Skor BM25:', bm25Scores)
    console.log('Skor DPR:', dprScores)
    
    // Pastikan kedua array memiliki panjang yang sama
    const maxLength = Math.max(bm25Scores.length, dprScores.length)
    const labels = Array.from({ length: maxLength }, (_, i) => `Doc ${i + 1}`)
    
    // Pastikan kedua array memiliki panjang yang sama untuk chart radar
    // Jika tidak sama, tambahkan nilai 0 untuk menyamakan panjang
    while (bm25Scores.length < maxLength) bm25Scores.push(0)
    while (dprScores.length < maxLength) dprScores.push(0)
    
    chartData.value = {
      labels: labels,
      datasets: [
        {
          label: 'BM25',
          backgroundColor: 'rgba(59, 130, 246, 0.5)',
          borderColor: 'rgb(59, 130, 246)',
          pointBackgroundColor: 'rgb(59, 130, 246)',
          pointBorderColor: '#fff',
          pointHoverBackgroundColor: '#fff',
          pointHoverBorderColor: 'rgb(59, 130, 246)',
          data: bm25Scores
        },
        {
          label: 'DPR',
          backgroundColor: 'rgba(16, 185, 129, 0.5)',
          borderColor: 'rgb(16, 185, 129)',
          pointBackgroundColor: 'rgb(16, 185, 129)',
          pointBorderColor: '#fff',
          pointHoverBackgroundColor: '#fff',
          pointHoverBorderColor: 'rgb(16, 185, 129)',
          data: dprScores
        }
      ]
    }
    
    // Tambahkan konfigurasi untuk skala radar
    chartOptions.value = {
      ...chartOptions.value,
      scales: {
        r: {
          min: 0,
          max: 1,
          ticks: {
            stepSize: 0.2
          }
        }
      },
      plugins: {
        tooltip: {
          callbacks: {
            label: function(context) {
              const item = context.dataset.label;
              const value = context.raw;
              const index = context.dataIndex;
              
              // Jika ada skor asli, tampilkan juga
              const originalScore = isNormalized && results.value[item.toLowerCase() + '_results'] && 
                results.value[item.toLowerCase() + '_results'][index] ? 
                results.value[item.toLowerCase() + '_results'][index].original_score : null;
                
              if (originalScore !== null) {
                return [`${item}: ${value.toFixed(4)} (Normalisasi)`, `Skor Asli: ${originalScore.toFixed(4)}`];
              }
              
              return `${item}: ${value.toFixed(4)}`;
            }
          }
        },
        legend: {
          position: 'top'
        },
        title: {
          display: true,
          text: isNormalized ? 'Perbandingan Skor (Dinormalisasi 0-1)' : 'Perbandingan Skor'
        }
      }
    };
    
    console.log('Chart data berhasil disiapkan:', chartData.value)
  } catch (err) {
    console.error('Error saat mempersiapkan data chart:', err)
    chartData.value = null
  }
}

// Reset hasil
const resetResults = () => {
  question.value = ''
  selectedQuestion.value = null
  results.value = null
  error.value = null
  chartData.value = null
}

// Inisialisasi sistem AES
const initializeAES = async () => {
  try {
    loading.value = true
    error.value = null
    
    toast.add({
      severity: 'info',
      summary: 'Memproses',
      detail: 'Menginisialisasi sistem AES...',
      life: 3000
    })
    
    const response = await systemApi.initializeAES()
    
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Sistem AES berhasil diinisialisasi',
      life: 3000
    })
    
    // Coba bandingkan RAG lagi
    if (selectedQuestion.value || question.value) {
      compareRag()
    }
  } catch (err) {
    console.error('Error initializing AES system:', err)
    error.value = `Gagal menginisialisasi sistem AES: ${err.message || 'Terjadi kesalahan pada server'}`
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: `Gagal menginisialisasi sistem AES: ${err.message || 'Silakan coba lagi'}`,
      life: 5000
    })
  } finally {
    loading.value = false
  }
}

// Load data saat komponen dimount
onMounted(() => {
  fetchExams()
})
</script>

<template>
  <div class="compare-rag-page">
    <div class="page-header">
      <h1>Bandingkan RAG</h1>
      <p class="page-subtitle">
        Bandingkan hasil retrieval dari metode BM25 dan DPR untuk analisis performa
      </p>
    </div>

    <Card class="card">
      <template #title>
        <div class="card-title">Masukkan Pertanyaan</div>
      </template>
      <template #content>
        <div class="search-form">
          <div class="input-group">
            <label>Pilih Judul Ujian:</label>
            <div class="dropdown-container">
              <Dropdown
                v-model="selectedExam"
                :options="exams"
                optionLabel="title"
                placeholder="Pilih ujian..."
                class="w-full"
                :loading="examsLoading"
                showClear
                @change="onExamSelected"
              >
                <template #option="slotProps">
                  <div class="dropdown-item">
                    <div class="dropdown-item-title">{{ slotProps.option.title }}</div>
                    <div class="dropdown-item-subtitle">
                      <span v-if="slotProps.option.question_count && slotProps.option.question_count > 0">
                        {{ slotProps.option.question_count }} pertanyaan
                      </span>
                      <span v-else>Belum ada pertanyaan</span>
                    </div>
                  </div>
                </template>
              </Dropdown>
            </div>
          </div>

          <div class="input-group">
            <label>Pilih Pertanyaan dari Ujian:</label>
            <div class="dropdown-container">
              <Dropdown
                v-model="selectedQuestion"
                :options="questions"
                optionLabel="text"
                :placeholder="selectedExam ? 'Pilih pertanyaan...' : 'Pilih ujian terlebih dahulu'"
                class="w-full"
                :loading="questionsLoading"
                :disabled="!selectedExam"
                showClear
                @change="onQuestionSelected"
              >
                <template #empty>
                  <span v-if="!selectedExam">Pilih ujian terlebih dahulu untuk melihat pertanyaan.</span>
                  <span v-else>Ujian ini belum memiliki pertanyaan.</span>
                </template>
                <template #option="slotProps">
                  <div class="dropdown-item">
                    <div class="dropdown-item-title">{{ slotProps.option.text }}</div>
                    <div class="dropdown-item-subtitle">Ujian: {{ slotProps.option.examTitle }}</div>
                  </div>
                </template>
              </Dropdown>
            </div>
          </div>

          <div class="input-group">
            <label>Atau Masukkan Pertanyaan Baru:</label>
            <InputText v-model="question" placeholder="Masukkan pertanyaan untuk dibandingkan..." class="w-full" />
          </div>
          
          <div class="search-actions">
            <Button type="button" label="Reset" icon="pi pi-times" class="p-button-secondary" 
                   @click="resetResults" :disabled="loading" />
            <Button type="button" label="Bandingkan" icon="pi pi-search" 
                   @click="compareRag" :loading="loading" />
          </div>
        </div>
      </template>
    </Card>

    <div v-if="loading" class="loading-container card">
      <ProgressSpinner />
      <p>Memproses pertanyaan dan membandingkan hasil retrieval...</p>
    </div>
    
    <div v-else-if="error" class="error-container card">
      <p class="error-message">{{ error }}</p>
      <div v-if="error.includes('Sistem AES belum diinisialisasi')" class="error-details">
        <p>Sistem AES belum diinisialisasi dengan benar. Kemungkinan penyebabnya:</p>
        <ul>
          <li>File PDF referensi (BUKU_IPA.pdf) tidak ditemukan</li>
          <li>Model LLM tidak ditemukan di direktori models/</li>
          <li>Terjadi error saat memuat model atau memproses dokumen</li>
        </ul>
        <p>Silakan periksa server API untuk informasi lebih lanjut.</p>
      </div>
      <Button label="Coba Lagi" icon="pi pi-refresh" @click="compareRag" />
      <Button label="Inisialisasi Sistem AES" icon="pi pi-cog" class="p-button-secondary ml-2" @click="initializeAES" />
    </div>
    
    <div v-else-if="results" class="results-container">
      <Card class="card">
        <template #title>
          <div class="card-title">Hasil Perbandingan</div>
        </template>
        <template #content>
          <TabView>
            <TabPanel header="Visualisasi">
              <div v-if="chartData" class="chart-container">
                <Chart type="radar" :data="chartData" :options="chartOptions" class="h-30rem" />
              </div>
              <div v-else class="empty-chart">
                <p>Tidak dapat menampilkan visualisasi. Data tidak tersedia atau tidak valid.</p>
              </div>
            </TabPanel>
            
            <TabPanel header="BM25">
              <div v-if="results.bm25_results && results.bm25_results.length > 0">
                <div v-if="results.normalized" class="normalization-info">
                  <i class="pi pi-info-circle" style="margin-right: 0.5rem;"></i>
                  <span>Skor telah dinormalisasi ke rentang 0-1 untuk perbandingan yang lebih adil</span>
                </div>
                <DataTable :value="results.bm25_results" stripedRows tableStyle="min-width: 50rem">
                  <Column field="index" header="Index" sortable></Column>
                  <Column field="score" header="Skor (Normalisasi)" sortable>
                    <template #body="slotProps">
                      <div class="score-container">
                        <div class="score-bar" :style="{ width: `${slotProps.data.score * 100}%` }"></div>
                        <span>{{ slotProps.data.score.toFixed(4) }}</span>
                      </div>
                    </template>
                  </Column>
                  <Column field="original_score" header="Skor Asli" sortable v-if="results.normalized"></Column>
                  <Column field="chunk" header="Content">
                    <template #body="slotProps">
                      <div class="chunk-content">{{ slotProps.data.chunk }}</div>
                    </template>
                  </Column>
                </DataTable>
              </div>
              <div v-else class="empty-results">
                <p>Tidak ada hasil BM25 yang ditemukan.</p>
              </div>
            </TabPanel>
            
            <TabPanel header="DPR">
              <div v-if="results.dpr_results && results.dpr_results.length > 0">
                <div v-if="results.normalized" class="normalization-info">
                  <i class="pi pi-info-circle" style="margin-right: 0.5rem;"></i>
                  <span>Skor telah dinormalisasi ke rentang 0-1 untuk perbandingan yang lebih adil</span>
                </div>
                <DataTable :value="results.dpr_results" stripedRows tableStyle="min-width: 50rem">
                  <Column field="index" header="Index" sortable></Column>
                  <Column field="score" header="Skor (Normalisasi)" sortable>
                    <template #body="slotProps">
                      <div class="score-container">
                        <div class="score-bar" :style="{ width: `${slotProps.data.score * 100}%` }"></div>
                        <span>{{ slotProps.data.score.toFixed(4) }}</span>
                      </div>
                    </template>
                  </Column>
                  <Column field="original_score" header="Skor Asli" sortable v-if="results.normalized"></Column>
                  <Column field="chunk" header="Content">
                    <template #body="slotProps">
                      <div class="chunk-content">{{ slotProps.data.chunk }}</div>
                    </template>
                  </Column>
                </DataTable>
              </div>
              <div v-else class="empty-results">
                <p>Tidak ada hasil DPR yang ditemukan. Pastikan DPR retriever telah diinstal dan diinisialisasi.</p>
                <p class="help-text">Untuk mengaktifkan DPR retriever, install dependensi dengan perintah:</p>
                <div class="code-block">pip install -r requirements_dpr.txt</div>
              </div>
            </TabPanel>
          </TabView>
        </template>
      </Card>
    </div>
  </div>
</template>

<style scoped>
.compare-rag-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 1.5rem;
}

.page-subtitle {
  color: var(--secondary-color);
  margin-top: 0.5rem;
}

.card-title {
  font-size: 1.2rem;
  font-weight: 600;
}

.search-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.input-group label {
  font-weight: 600;
  color: var(--text-color);
}

.dropdown-container {
  width: 100%;
}

.dropdown-item {
  padding: 0.5rem 0;
}

.dropdown-item-title {
  font-weight: 500;
}

.dropdown-item-subtitle {
  font-size: 0.85rem;
  color: var(--secondary-color);
}

.search-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: 0.5rem;
}

.w-full {
  width: 100%;
}

.results-container {
  margin-top: 2rem;
}

.chart-container {
  display: flex;
  justify-content: center;
  padding: 1rem;
}

.h-30rem {
  height: 30rem;
}

.chunk-content {
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-line;
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

.error-details {
  background-color: #fef2f2;
  border: 1px solid #fee2e2;
  border-radius: 8px;
  padding: 1rem;
  margin: 1rem 0;
}

.error-details p {
  margin-bottom: 0.5rem;
}

.error-details ul {
  margin: 0.5rem 0;
  padding-left: 1.5rem;
}

.error-details li {
  margin-bottom: 0.25rem;
}

.ml-2 {
  margin-left: 0.5rem;
}

.empty-chart,
.empty-results {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 1rem;
  text-align: center;
  color: var(--secondary-color);
}

.help-text {
  margin-top: 1rem;
  font-size: 0.9rem;
  color: var(--secondary-color);
}

.code-block {
  background-color: #f1f5f9;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  font-family: monospace;
  margin-top: 0.5rem;
}

.normalization-info {
  display: flex;
  align-items: center;
  background-color: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  margin-bottom: 1rem;
  color: #0369a1;
}

.score-container {
  position: relative;
  width: 100%;
  height: 24px;
  display: flex;
  align-items: center;
}

.score-bar {
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  background-color: rgba(59, 130, 246, 0.2);
  z-index: 0;
  border-radius: 2px;
}

.score-container span {
  position: relative;
  z-index: 1;
  padding-left: 4px;
}

@media (max-width: 768px) {
  .search-actions {
    flex-direction: column;
    width: 100%;
  }
  
  .search-actions button {
    width: 100%;
  }
  
  .h-30rem {
    height: 20rem;
  }
}
</style>

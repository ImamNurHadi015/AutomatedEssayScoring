<template>
  <div class="session-page">
    <Toast />
    
    <div v-if="loading" class="loading-container card">
      <ProgressSpinner />
      <p>Memuat sesi ujian...</p>
    </div>
    
    <div v-else-if="error" class="error-container card">
      <p class="error-message">{{ error }}</p>
      <Button label="Kembali" icon="pi pi-arrow-left" @click="navigateBack" />
    </div>
    
    <template v-else>
      <div class="page-header">
        <div class="header-content">
          <h1>Sesi Ujian: {{ session.exam_title }}</h1>
          <p class="page-subtitle">
            Kode Sesi: <span class="session-code">{{ session.session_code }}</span>
          </p>
        </div>
        <div class="header-actions" v-if="!session.is_completed">
          <Button label="Mulai Ujian" icon="pi pi-play" @click="startExam" 
                 v-if="!examStarted" class="p-button-success" />
          <Button label="Lihat Hasil" icon="pi pi-chart-bar" @click="viewResults" 
                 v-if="session.is_completed" class="p-button-info" />
        </div>
      </div>
      
      <Card class="card">
        <template #title>
          <div class="card-title">Informasi Sesi</div>
        </template>
        <template #content>
            <div class="session-info">
            <div class="info-item">
              <div class="info-label">Ujian</div>
              <div class="info-value">{{ session.exam_title }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Jumlah Siswa</div>
              <div class="info-value">{{ session.total_students }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Siswa Saat Ini</div>
              <div class="info-value">{{ session.current_student?.name || '-' }} ({{ session.current_student_index + 1 }}) dari {{ session.total_students }}</div>
            </div>
            <div class="info-item">
              <div class="info-label">Status</div>
              <div class="info-value">
                <Tag :severity="session.is_completed ? 'success' : 'info'" 
                     :value="session.is_completed ? 'Selesai' : 'Berlangsung'" />
              </div>
            </div>
          </div>
        </template>
      </Card>
      
      <div v-if="examStarted && !session.is_completed" class="exam-container">
        <Card class="card">
          <template #title>
            <div class="card-title">
              Siswa {{ session.current_student }} dari {{ session.total_students }}
            </div>
          </template>
          <template #content>
            <div class="student-form">
              <div class="input-group">
                <label>Pilih Siswa:</label>
                <Dropdown v-model="selectedStudentId" :options="session.students || []" optionLabel="name" optionValue="id" placeholder="Pilih siswa..." class="w-full" @change="onStudentSelected" />
              </div>
              
              <div class="questions-container" v-if="questions.length > 0">
                <h3>Daftar Pertanyaan</h3>
                
                <div v-for="question in questions" :key="question.id" class="question-card">
                  <div class="question-text">{{ question.question_text }}</div>
                  <div class="answer-form">
                    <label>Jawaban:</label>
                    <Textarea v-model="answers[question.id]" rows="5" class="w-full" 
                             placeholder="Ketik jawaban Anda di sini..." />
                  </div>
                </div>
                
                <div class="form-actions">
                  <Button label="Simpan Jawaban" icon="pi pi-save" @click="submitAnswers" 
                         :loading="submitting" />
                </div>
              </div>
              
              <div v-else class="empty-questions">
                <p>Tidak ada pertanyaan dalam ujian ini.</p>
              </div>
            </div>
          </template>
        </Card>
      </div>
      
      <div v-if="session.is_completed" class="results-container">
        <Card class="card">
          <template #title>
            <div class="card-title">Hasil Ujian</div>
          </template>
          <template #content>
            <Button label="Lihat Hasil Lengkap" icon="pi pi-chart-bar" @click="viewResults" />
          </template>
        </Card>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { examApi, sessionApi, answerApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import Card from 'primevue/card'
import Dropdown from 'primevue/dropdown'
import Textarea from 'primevue/textarea'
import Tag from 'primevue/tag'
import ProgressSpinner from 'primevue/progressspinner'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const route = useRoute()
const toast = useToast()

const session = ref(null)
const questions = ref([])
const selectedStudentId = ref('')
const answers = ref({})
const loading = ref(true)
const error = ref(null)
const examStarted = ref(false)
const submitting = ref(false)

const sessionId = computed(() => route.params.id)

// Mendapatkan detail sesi
const fetchSession = async () => {
  try {
    loading.value = true
    error.value = null
    
    const response = await sessionApi.getSession(sessionId.value)
    session.value = response.data
    // Set default selected student ke current_student jika ada
    if (session.value?.current_student?.id) {
      selectedStudentId.value = session.value.current_student.id
    }
    
    // Jika sesi sudah selesai, tampilkan pesan
    if (session.value.is_completed) {
      toast.add({
        severity: 'info',
        summary: 'Sesi Selesai',
        detail: 'Sesi ujian ini telah selesai',
        life: 3000
      })
    }
  } catch (err) {
    console.error('Error fetching session:', err)
    error.value = `Gagal mendapatkan detail sesi: ${err.response?.data?.error || 'Terjadi kesalahan'}`
  } finally {
    loading.value = false
  }
}

// Mendapatkan daftar pertanyaan untuk ujian
const fetchQuestions = async () => {
  try {
    if (!session.value || !session.value.exam_id) return
    
    const response = await examApi.getExamQuestions(session.value.exam_id)
    questions.value = response.data
    
    // Inisialisasi objek jawaban
    questions.value.forEach(question => {
      answers.value[question.id] = ''
    })
  } catch (err) {
    console.error('Error fetching questions:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mendapatkan daftar pertanyaan',
      life: 3000
    })
  }
}

// Memulai ujian
const startExam = () => {
  examStarted.value = true
  // Pastikan selectedStudentId terisi
  if (!selectedStudentId.value && session.value?.current_student?.id) {
    selectedStudentId.value = session.value.current_student.id
  }
  fetchQuestions()
}

// Mengirim jawaban
const submitAnswers = async () => {
  // Validasi pemilihan siswa
  if (!selectedStudentId.value) {
    toast.add({
      severity: 'warn',
      summary: 'Peringatan',
      detail: 'Silakan pilih siswa terlebih dahulu',
      life: 3000
    })
    return
  }
  
  // Validasi jawaban
  const unansweredQuestions = Object.entries(answers.value)
    .filter(([_, answer]) => !answer.trim())
    .length
    
  if (unansweredQuestions > 0) {
    toast.add({
      severity: 'warn',
      summary: 'Peringatan',
      detail: `Ada ${unansweredQuestions} pertanyaan yang belum dijawab`,
      life: 3000
    })
    return
  }
  
  try {
    submitting.value = true
    
    // Kirim semua jawaban
    for (const questionId in answers.value) {
      await answerApi.createAnswer({
        question_id: questionId, // gunakan ObjectId string apa adanya
        answer_text: answers.value[questionId],
        session_id: session.value.id
      })
    }
    
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Jawaban berhasil disimpan',
      life: 3000
    })
    
    // Jika ini adalah siswa terakhir, selesaikan sesi
    if ((session.value.current_student_index + 1) >= session.value.total_students) {
      await sessionApi.nextStudent(session.value.id)
      session.value.is_completed = true
      examStarted.value = false
      
      toast.add({
        severity: 'info',
        summary: 'Sesi Selesai',
        detail: 'Semua siswa telah menyelesaikan ujian',
        life: 3000
      })
    } else {
      // Pindah ke siswa berikutnya
      const response = await sessionApi.nextStudent(session.value.id)
      session.value.current_student = response.data.current_student
      session.value.current_student_index = response.data.current_student_index
      if (session.value?.current_student?.id) {
        selectedStudentId.value = session.value.current_student.id
      }
      
      // Reset form
      Object.keys(answers.value).forEach(key => {
        answers.value[key] = ''
      })
      
      toast.add({
        severity: 'info',
        summary: 'Siswa Berikutnya',
        detail: `Silakan lanjutkan dengan siswa ${session.value.current_student?.name || ''} (${session.value.current_student_index + 1} dari ${session.value.total_students})`,
        life: 3000
      })
    }
  } catch (err) {
    console.error('Error submitting answers:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: `Gagal menyimpan jawaban: ${err.response?.data?.error || 'Terjadi kesalahan'}`,
      life: 5000
    })
  } finally {
    submitting.value = false
  }
}

// Melihat hasil ujian
const viewResults = () => {
  router.push(`/sessions/${session.value.id}/results`)
}

// Event ketika memilih siswa manual (opsional)
const onStudentSelected = () => {
  const found = (session.value?.students || []).find(s => s.id === selectedStudentId.value)
  if (found) {
    session.value.current_student = found
    session.value.current_student_index = (session.value.students || []).findIndex(s => s.id === found.id)
  }
}

const navigateBack = () => {
  router.push('/exams')
}

onMounted(() => {
  fetchSession()
})
</script>

<style scoped>
.session-page {
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

.session-info {
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

.exam-container {
  margin-top: 1.5rem;
}

.student-form {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.questions-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.question-card {
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 1rem;
  background-color: #f8fafc;
}

.question-text {
  font-weight: 600;
  margin-bottom: 1rem;
}

.answer-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 1rem;
}

.empty-questions {
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

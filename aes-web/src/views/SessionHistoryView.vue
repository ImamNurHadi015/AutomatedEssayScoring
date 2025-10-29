<template>
  <div class="session-history-page">
    <Toast />
    
    <div class="page-header">
      <h1>History Sesi Ujian</h1>
      <Button label="Buat Sesi Baru" icon="pi pi-plus" @click="createSession" class="p-button-success" />
    </div>
    
    <Card class="card">
      <template #content>
        <div v-if="loading" class="loading-container">
          <ProgressSpinner />
          <p>Memuat history sesi ujian...</p>
        </div>
        
        <div v-else-if="error" class="error-container">
          <p class="error-message">{{ error }}</p>
          <Button label="Coba Lagi" icon="pi pi-refresh" @click="fetchSessions" />
        </div>
        
        <div v-else-if="sessions.length === 0" class="empty-container">
          <p>Belum ada sesi ujian yang dibuat.</p>
          <Button label="Buat Sesi Baru" icon="pi pi-plus" @click="createSession" class="mt-4" />
        </div>
        
        <DataTable v-else :value="sessions" stripedRows paginator :rows="10" 
                  :rowsPerPageOptions="[5, 10, 25, 50]" tableStyle="min-width: 50rem">
          <Column field="session_code" header="Kode Sesi" sortable style="width: 10%"></Column>
          <Column field="exam_title" header="Ujian" sortable style="width: 30%">
            <template #body="slotProps">
              <div>
                {{ slotProps.data.exam_title }}
                <div v-if="slotProps.data.exams && slotProps.data.exams.length > 1" class="multiple-exams">
                  <small>({{ slotProps.data.exams.length }} ujian)</small>
                </div>
              </div>
            </template>
          </Column>
          <Column field="total_students" header="Jumlah Siswa" sortable style="width: 10%"></Column>
          <Column field="created_at" header="Tanggal" sortable style="width: 20%">
            <template #body="slotProps">
              {{ formatDate(slotProps.data.created_at) }}
            </template>
          </Column>
          <Column field="is_completed" header="Status" sortable style="width: 10%">
            <template #body="slotProps">
              <Tag :severity="slotProps.data.is_completed ? 'success' : 'info'" 
                   :value="slotProps.data.is_completed ? 'Selesai' : 'Berlangsung'" />
            </template>
          </Column>
          <Column style="width: 20%">
            <template #body="slotProps">
              <div class="action-button-wrapper">
                <Button v-if="slotProps.data.is_completed" 
                        icon="pi pi-chart-bar" 
                        rounded 
                        text 
                        aria-label="Hasil" 
                        @click="viewResults(slotProps.data)" 
                        tooltip="Lihat Hasil"
                        :tooltipOptions="{ position: 'top' }" />
                <Button v-else
                        icon="pi pi-play" 
                        rounded 
                        text 
                        aria-label="Lanjutkan" 
                        @click="continueSession(slotProps.data)" 
                        tooltip="Lanjutkan Sesi"
                        :tooltipOptions="{ position: 'top' }" />
                <Button icon="pi pi-users" 
                        rounded 
                        text 
                        aria-label="Detail Siswa" 
                        @click="viewStudentResults(slotProps.data)" 
                        tooltip="Detail Per Siswa"
                        :tooltipOptions="{ position: 'top' }" />
              </div>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { sessionApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import ProgressSpinner from 'primevue/progressspinner'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const toast = useToast()

const sessions = ref([])
const loading = ref(false)
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

// Ambil data sesi
const fetchSessions = async () => {
  try {
    loading.value = true
    error.value = null
    
    const response = await sessionApi.getAllSessions()
    sessions.value = response.data
  } catch (err) {
    console.error('Error fetching sessions:', err)
    error.value = 'Gagal mengambil data sesi ujian. Silakan coba lagi.'
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengambil data sesi ujian',
      life: 3000
    })
  } finally {
    loading.value = false
  }
}

// Navigasi ke halaman detail sesi
const continueSession = (session) => {
  router.push(`/sessions/${session.id}`)
}

// Navigasi ke halaman hasil sesi
const viewResults = (session) => {
  router.push(`/sessions/${session.id}/results`)
}

// Navigasi ke halaman detail hasil per siswa
const viewStudentResults = (session) => {
  router.push(`/sessions/${session.id}/student-results`)
}

// Navigasi ke halaman buat sesi
const createSession = () => {
  router.push('/sessions/create')
}

// Load data saat komponen dimount
onMounted(() => {
  fetchSessions()
})

onActivated(() => {
  fetchSessions()
})
</script>

<style scoped>
.session-history-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
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
  gap: 0.5rem;
  min-height: 40px;
  background-color: rgba(255, 255, 255, 0.5);
}

.multiple-exams {
  margin-top: 0.25rem;
  color: var(--secondary-color);
}

.mt-4 {
  margin-top: 1rem;
}
</style>

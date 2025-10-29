<script setup>
import { ref, onMounted, onActivated, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { examApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import ProgressSpinner from 'primevue/progressspinner'
import Card from 'primevue/card'

const router = useRouter()
const route = useRoute()
const exams = ref([])
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

// Ambil data ujian
const fetchExams = async () => {
  if (loading.value) return
  try {
    loading.value = true
    error.value = null
    
    // Coba ambil data dari API
    try {
      const response = await examApi.getExams()
      exams.value = Array.isArray(response.data) ? response.data : []
    } catch (apiErr) {
      console.error('API Error:', apiErr)
      error.value = apiErr.response?.data?.error || 'Gagal mengambil data ujian. Silakan coba lagi.'
      exams.value = []
    }
  } catch (err) {
    console.error('Error fetching exams:', err)
    error.value = 'Gagal mengambil data ujian. Silakan coba lagi.'
  } finally {
    loading.value = false
  }
}

const retryFetchExams = () => {
  fetchExams()
}

// Navigasi ke halaman detail ujian
const viewExam = (exam) => {
  router.push(`/exams/${exam.id}`)
}

// Navigasi ke halaman buat ujian
const createExam = () => {
  console.log('Navigating to /exams/create')
  router.push('/exams/create')
}

// Load data saat komponen dimount
onMounted(() => {
  fetchExams()
})

onActivated(() => {
  fetchExams()
})

watch(
  () => route.fullPath,
  () => {
    fetchExams()
  }
)
</script>

<template>
  <div class="exams-page">
    <div class="page-header">
      <h1>Daftar Ujian</h1>
      <Button label="Buat Ujian Baru" icon="pi pi-plus" @click="createExam" class="p-button-success" />
    </div>

    <Card class="card">
      <template #content>
        <div v-if="loading" class="loading-container">
          <ProgressSpinner />
          <p>Memuat data ujian...</p>
        </div>
        
        <div v-else-if="error" class="error-container">
          <p class="error-message">{{ error }}</p>
          <Button label="Coba Lagi" icon="pi pi-refresh" @click="retryFetchExams" />
        </div>
        
        <div v-else-if="exams.length === 0" class="empty-container">
          <p>Belum ada ujian yang dibuat.</p>
          <Button label="Buat Ujian Baru" icon="pi pi-plus" @click="createExam" class="mt-4" />
        </div>
        
        <DataTable v-else :value="exams" stripedRows paginator :rows="10" 
                  :rowsPerPageOptions="[5, 10, 25, 50]" tableStyle="min-width: 50rem">
          <Column field="id" header="ID" sortable style="width: 5%"></Column>
          <Column field="title" header="Judul" sortable style="width: 30%"></Column>
          <Column field="description" header="Deskripsi" style="width: 35%">
            <template #body="slotProps">
              <span>{{ slotProps.data.description || '-' }}</span>
            </template>
          </Column>
          <Column field="question_count" header="Jumlah Soal" sortable style="width: 10%"></Column>
          <Column field="created_at" header="Tanggal Dibuat" sortable style="width: 20%">
            <template #body="slotProps">
              {{ formatDate(slotProps.data.created_at) }}
            </template>
          </Column>
          <Column style="width: 10%">
            <template #body="slotProps">
              <div class="action-button-wrapper">
                <Button icon="pi pi-eye" rounded text aria-label="Lihat" @click="viewExam(slotProps.data)" />
              </div>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>
  </div>
</template>

<style scoped>
.exams-page {
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
  min-height: 40px;
  background-color: rgba(255, 255, 255, 0.5);
}
</style>

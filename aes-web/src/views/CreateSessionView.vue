<template>
  <div class="create-session-page">
    <Toast />
    
    <div class="page-header">
      <h1>Buat Sesi Ujian</h1>
      <p class="page-subtitle">
        Buat sesi ujian untuk beberapa siswa sekaligus
      </p>
    </div>
    
    <Card class="card">
      <template #title>
        <div class="card-title">Form Sesi Ujian</div>
      </template>
      <template #content>
        <div class="form-container">
          <div class="input-group">
            <label>Pilih Ujian:</label>
            <MultiSelect v-model="selectedExams" :options="exams" optionLabel="title" 
                     placeholder="Pilih satu atau lebih ujian..." class="w-full" :loading="loadingExams"
                     display="chip" />
            <small>Pilih satu atau lebih ujian untuk sesi ini. Ujian akan dijalankan sesuai urutan.</small>
          </div>
          
          <div class="input-group" v-if="selectedExams.length > 0">
            <label>Urutan Ujian:</label>
            <OrderList v-model="selectedExams" listStyle="height:auto" 
                      :metaKeySelection="false" dataKey="id">
              <template #item="slotProps">
                <div class="order-list-item">
                  <span>{{ slotProps.item.title }}</span>
                </div>
              </template>
            </OrderList>
            <small>Drag and drop untuk mengatur urutan ujian</small>
          </div>
          
          <div class="input-group">
            <label>Jumlah Siswa:</label>
            <div class="p-inputgroup">
              <InputNumber v-model="totalStudents" :min="1" :max="50" placeholder="Masukkan jumlah siswa" />
              <span class="p-inputgroup-addon">siswa</span>
            </div>
            <small>Maksimal 50 siswa per sesi</small>
          </div>
          
          <div class="form-actions">
            <Button type="button" label="Kembali" icon="pi pi-arrow-left" class="p-button-secondary" 
                   @click="navigateBack" :disabled="loading" />
            <Button type="button" label="Buat Sesi" icon="pi pi-check" 
                   @click="createSession" :loading="loading" />
          </div>
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { examApi, sessionApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import Card from 'primevue/card'
import MultiSelect from 'primevue/multiselect'
import OrderList from 'primevue/orderlist'
import InputNumber from 'primevue/inputnumber'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const toast = useToast()

const exams = ref([])
const selectedExams = ref([])
const totalStudents = ref(1)
const loading = ref(false)
const loadingExams = ref(false)

// Mendapatkan daftar ujian
const fetchExams = async () => {
  try {
    loadingExams.value = true
    const response = await examApi.getExams()
    exams.value = response.data
    
    if (exams.value.length === 0) {
      toast.add({
        severity: 'warn',
        summary: 'Tidak ada ujian',
        detail: 'Tidak ada ujian yang tersedia. Silakan buat ujian terlebih dahulu.',
        life: 5000
      })
    }
  } catch (err) {
    console.error('Error fetching exams:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mendapatkan daftar ujian',
      life: 3000
    })
  } finally {
    loadingExams.value = false
  }
}

// Membuat sesi ujian baru
const createSession = async () => {
  if (!selectedExams.value || selectedExams.value.length === 0) {
    toast.add({
      severity: 'warn',
      summary: 'Peringatan',
      detail: 'Silakan pilih minimal satu ujian',
      life: 3000
    })
    return
  }
  
  if (!totalStudents.value || totalStudents.value < 1) {
    toast.add({
      severity: 'warn',
      summary: 'Peringatan',
      detail: 'Jumlah siswa minimal 1',
      life: 3000
    })
    return
  }
  
  try {
    loading.value = true
    
    // Siapkan data untuk API
    const examIds = selectedExams.value.map(exam => exam.id)
    
    // Tambahkan ke API service
    const response = await sessionApi.createSession({
      exam_ids: examIds,
      total_students: totalStudents.value
    })
    
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Sesi ujian berhasil dibuat',
      life: 3000
    })
    
    // Navigasi ke halaman sesi
    router.push(`/sessions/${response.data.id}`)
  } catch (err) {
    console.error('Error creating session:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: `Gagal membuat sesi ujian: ${err.response?.data?.error || 'Terjadi kesalahan'}`,
      life: 5000
    })
  } finally {
    loading.value = false
  }
}

const navigateBack = () => {
  router.back()
}

onMounted(() => {
  fetchExams()
})
</script>

<style scoped>
.create-session-page {
  max-width: 800px;
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

.form-container {
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

.input-group small {
  color: var(--secondary-color);
  font-size: 0.85rem;
}

.form-actions {
  display: flex;
  justify-content: space-between;
  margin-top: 1rem;
}

.w-full {
  width: 100%;
}

.order-list-item {
  display: flex;
  align-items: center;
  padding: 0.5rem;
  width: 100%;
}

:deep(.p-orderlist) {
  width: 100%;
  max-height: 250px;
}

:deep(.p-orderlist-list) {
  min-height: 100px;
}
</style>

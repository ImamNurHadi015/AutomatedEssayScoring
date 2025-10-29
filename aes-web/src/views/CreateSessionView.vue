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
            <label>Pilih Siswa:</label>
            <MultiSelect v-model="selectedStudents" :options="students" optionLabel="name" 
                     placeholder="Pilih siswa untuk ujian ini..." class="w-full" :loading="loadingStudents"
                     display="chip" :filter="true" />
            <div class="student-actions">
              <small>Pilih siswa yang akan mengikuti ujian ini</small>
              <Button type="button" label="Kelola Siswa" icon="pi pi-user" class="p-button-text p-button-sm" 
                     @click="navigateToStudents" />
            </div>
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
import { examApi, sessionApi, studentApi } from '@/services/api'

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
const students = ref([])
const selectedStudents = ref([])
const loading = ref(false)
const loadingExams = ref(false)
const loadingStudents = ref(false)

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

// Mendapatkan daftar siswa
const fetchStudents = async () => {
  try {
    loadingStudents.value = true
    const response = await studentApi.getAllStudents()
    students.value = response.data
    
    if (students.value.length === 0) {
      toast.add({
        severity: 'warn',
        summary: 'Tidak ada siswa',
        detail: 'Tidak ada siswa yang tersedia. Silakan tambahkan siswa terlebih dahulu.',
        life: 5000
      })
    }
  } catch (err) {
    console.error('Error fetching students:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mendapatkan daftar siswa',
      life: 3000
    })
  } finally {
    loadingStudents.value = false
  }
}

// Navigasi ke halaman kelola siswa
const navigateToStudents = () => {
  router.push('/students')
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
  
  if (!selectedStudents.value || selectedStudents.value.length === 0) {
    toast.add({
      severity: 'warn',
      summary: 'Peringatan',
      detail: 'Silakan pilih minimal satu siswa',
      life: 3000
    })
    return
  }
  
  try {
    loading.value = true
    
    // Siapkan data untuk API
    const examIds = selectedExams.value.map(exam => exam.id)
    const studentIds = selectedStudents.value.map(student => student.id)
    
    // Tambahkan ke API service
    const response = await sessionApi.createSession({
      exam_ids: examIds,
      student_ids: studentIds
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
  fetchStudents()
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

.student-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
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

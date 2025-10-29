<template>
  <div class="students-page">
    <Toast />
    
    <div class="page-header">
      <h1>Daftar Siswa</h1>
      <Button label="Tambah Siswa" icon="pi pi-plus" @click="openAddDialog" class="p-button-success" />
    </div>
    
    <Card class="card">
      <template #content>
        <div v-if="loading" class="loading-container">
          <ProgressSpinner />
          <p>Memuat data siswa...</p>
        </div>
        
        <div v-else-if="error" class="error-container">
          <p class="error-message">{{ error }}</p>
          <Button label="Coba Lagi" icon="pi pi-refresh" @click="fetchStudents" />
        </div>
        
        <div v-else-if="students.length === 0" class="empty-container">
          <p>Belum ada siswa yang terdaftar.</p>
          <Button label="Tambah Siswa" icon="pi pi-plus" @click="openAddDialog" class="mt-4" />
        </div>
        
        <DataTable v-else :value="students" stripedRows paginator :rows="10" 
                  :rowsPerPageOptions="[5, 10, 25, 50]" tableStyle="min-width: 50rem"
                  :filters="filters" filterDisplay="row">
          <Column field="id" header="ID" sortable style="width: 10%"></Column>
          <Column field="name" header="Nama" sortable style="width: 30%">
            <template #filter="{filterModel, filterCallback}">
              <InputText v-model="filters['name'].value" @input="filterCallback()" placeholder="Cari nama..." class="p-column-filter" />
            </template>
          </Column>
          <Column field="nis" header="NIS" sortable style="width: 20%">
            <template #filter="{filterModel, filterCallback}">
              <InputText v-model="filters['nis'].value" @input="filterCallback()" placeholder="Cari NIS..." class="p-column-filter" />
            </template>
          </Column>
          <Column field="created_at" header="Tanggal Daftar" sortable style="width: 20%">
            <template #body="slotProps">
              {{ formatDate(slotProps.data.created_at) }}
            </template>
          </Column>
          <Column style="width: 20%">
            <template #body="slotProps">
              <div class="action-button-wrapper">
                <Button icon="pi pi-pencil" 
                        rounded 
                        text 
                        aria-label="Edit" 
                        @click="editStudent(slotProps.data)" 
                        tooltip="Edit"
                        :tooltipOptions="{ position: 'top' }" />
                <Button icon="pi pi-trash" 
                        rounded 
                        text 
                        aria-label="Hapus" 
                        @click="confirmDeleteStudent(slotProps.data)" 
                        tooltip="Hapus"
                        :tooltipOptions="{ position: 'top' }"
                        class="p-button-danger" />
              </div>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>
    
    <!-- Dialog untuk tambah/edit siswa -->
    <Dialog v-model:visible="studentDialog" :header="dialogMode === 'add' ? 'Tambah Siswa' : 'Edit Siswa'" 
            :modal="true" class="p-fluid" :style="{width: '450px'}">
      <div class="form-container">
        <div class="field">
          <label for="name">Nama <span class="required">*</span></label>
          <InputText id="name" v-model="student.name" :class="{'p-invalid': submitted && !student.name}" />
          <small class="p-error" v-if="submitted && !student.name">Nama harus diisi</small>
        </div>
        
        <div class="field">
          <label for="nis">NIS <span class="required">*</span></label>
          <InputText id="nis" v-model="student.nis" :class="{'p-invalid': submitted && !student.nis}" />
          <small class="p-error" v-if="submitted && !student.nis">NIS harus diisi</small>
        </div>
      </div>
      
      <template #footer>
        <Button label="Batal" icon="pi pi-times" class="p-button-text" @click="hideDialog" />
        <Button label="Simpan" icon="pi pi-check" class="p-button-text" @click="saveStudent" :loading="saving" />
      </template>
    </Dialog>
    
    <!-- Dialog konfirmasi hapus -->
    <Dialog v-model:visible="deleteDialog" header="Konfirmasi" :modal="true" :style="{width: '450px'}">
      <div class="confirmation-content">
        <i class="pi pi-exclamation-triangle mr-3" style="font-size: 2rem" />
        <span v-if="student">Apakah Anda yakin ingin menghapus siswa <b>{{ student.name }}</b>?</span>
      </div>
      <template #footer>
        <Button label="Tidak" icon="pi pi-times" class="p-button-text" @click="deleteDialog = false" />
        <Button label="Ya" icon="pi pi-check" class="p-button-text p-button-danger" @click="deleteStudent" :loading="deleting" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import { FilterMatchMode } from 'primevue/api'
import { studentApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Card from 'primevue/card'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import ProgressSpinner from 'primevue/progressspinner'
import { useToast } from 'primevue/usetoast'

const router = useRouter()
const toast = useToast()

const students = ref([])
const student = ref({})
const studentDialog = ref(false)
const deleteDialog = ref(false)
const submitted = ref(false)
const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)
const error = ref(null)
const dialogMode = ref('add')

// Filter
const filters = ref({
  'name': { value: null, matchMode: FilterMatchMode.CONTAINS },
  'nis': { value: null, matchMode: FilterMatchMode.CONTAINS }
})

// Format tanggal
const formatDate = (date) => {
  if (!date) return '-'
  return new Date(date).toLocaleDateString('id-ID', {
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  })
}

// Ambil data siswa
const fetchStudents = async () => {
  try {
    loading.value = true
    error.value = null
    
    const response = await studentApi.getAllStudents()
    students.value = response.data
  } catch (err) {
    console.error('Error fetching students:', err)
    error.value = 'Gagal mengambil data siswa. Silakan coba lagi.'
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: 'Gagal mengambil data siswa',
      life: 3000
    })
  } finally {
    loading.value = false
  }
}

// Buka dialog tambah siswa
const openAddDialog = () => {
  student.value = {}
  submitted.value = false
  dialogMode.value = 'add'
  studentDialog.value = true
}

// Buka dialog edit siswa
const editStudent = (data) => {
  student.value = {...data}
  dialogMode.value = 'edit'
  studentDialog.value = true
}

// Tutup dialog
const hideDialog = () => {
  studentDialog.value = false
  submitted.value = false
}

// Simpan siswa (tambah/edit)
const saveStudent = async () => {
  submitted.value = true
  
  if (!student.value.name?.trim() || !student.value.nis?.trim()) {
    return
  }
  
  try {
    saving.value = true
    
    if (dialogMode.value === 'add') {
      // Tambah siswa baru
      const response = await studentApi.createStudent({
        name: student.value.name.trim(),
        nis: student.value.nis.trim()
      })
      
      students.value.push(response.data)
      
      toast.add({
        severity: 'success',
        summary: 'Berhasil',
        detail: 'Siswa berhasil ditambahkan',
        life: 3000
      })
    } else {
      // Update siswa
      const response = await studentApi.updateStudent(student.value.id, {
        name: student.value.name.trim(),
        nis: student.value.nis.trim()
      })
      
      const index = students.value.findIndex(s => s.id === student.value.id)
      if (index !== -1) {
        students.value[index] = response.data
      }
      
      toast.add({
        severity: 'success',
        summary: 'Berhasil',
        detail: 'Data siswa berhasil diperbarui',
        life: 3000
      })
    }
    
    hideDialog()
  } catch (err) {
    console.error('Error saving student:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: `Gagal ${dialogMode.value === 'add' ? 'menambahkan' : 'memperbarui'} siswa: ${err.response?.data?.error || 'Terjadi kesalahan'}`,
      life: 5000
    })
  } finally {
    saving.value = false
  }
}

// Konfirmasi hapus siswa
const confirmDeleteStudent = (data) => {
  student.value = data
  deleteDialog.value = true
}

// Hapus siswa
const deleteStudent = async () => {
  try {
    deleting.value = true
    
    await studentApi.deleteStudent(student.value.id)
    
    students.value = students.value.filter(s => s.id !== student.value.id)
    deleteDialog.value = false
    
    toast.add({
      severity: 'success',
      summary: 'Berhasil',
      detail: 'Siswa berhasil dihapus',
      life: 3000
    })
  } catch (err) {
    console.error('Error deleting student:', err)
    toast.add({
      severity: 'error',
      summary: 'Gagal',
      detail: `Gagal menghapus siswa: ${err.response?.data?.error || 'Terjadi kesalahan'}`,
      life: 5000
    })
  } finally {
    deleting.value = false
  }
}

// Load data saat komponen dimount
onMounted(() => {
  fetchStudents()
})

onActivated(() => {
  fetchStudents()
})
</script>

<style scoped>
.students-page {
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

.form-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin-bottom: 1.5rem;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.required {
  color: #EF4444;
}

.confirmation-content {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.mr-3 {
  margin-right: 0.75rem;
}

.mt-4 {
  margin-top: 1rem;
}

.p-column-filter {
  width: 100%;
}
</style>

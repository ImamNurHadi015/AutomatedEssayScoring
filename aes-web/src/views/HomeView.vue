<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { systemApi } from '@/services/api'

// PrimeVue Components
import Button from 'primevue/button'
import Card from 'primevue/card'
import ProgressSpinner from 'primevue/progressspinner'

const router = useRouter()
const loading = ref(false)
const systemStatus = ref('Memeriksa...')

// Memeriksa status sistem
onMounted(async () => {
  try {
    loading.value = true
    const response = await systemApi.healthCheck()
    if (response.data.status === 'ok') {
      systemStatus.value = 'Aktif'
    } else {
      systemStatus.value = 'Tidak Aktif'
    }
  } catch (error) {
    console.error('Error checking system status:', error)
    systemStatus.value = 'Tidak Aktif'
  } finally {
    loading.value = false
  }
})

// Navigasi ke halaman
const navigateTo = (path) => {
  console.log('Navigating to:', path)
  router.push(path)
}
</script>

<template>
  <div class="home">
    <h1 class="page-title">Selamat Datang di Sistem Automated Essay Scoring</h1>
    <p class="page-subtitle">
      Sistem penilaian otomatis jawaban esai menggunakan LLM dan RAG
    </p>

    <div class="status-card card">
      <div class="status-header">
        <h2>Status Sistem</h2>
        <div class="status-indicator" :class="{ 'active': systemStatus === 'Aktif' }">
          <span v-if="loading"><ProgressSpinner style="width: 20px; height: 20px;" /></span>
          <span v-else>{{ systemStatus }}</span>
        </div>
      </div>
    </div>

    <div class="features-grid">
      <div class="card feature-card plain-card">
        <h2 class="feature-title">
          <span class="feature-icon-wrapper">
            <i class="pi pi-plus feature-icon" aria-hidden="true"></i>
          </span>
          Buat Agenda Ujian
        </h2>
        <div class="feature-content">
          <p>Buat agenda ujian baru dengan berbagai pertanyaan esai untuk siswa.</p>
        </div>
        <div class="feature-footer">
          <Button class="w-full" label="Buat Ujian" icon="pi pi-plus" @click="navigateTo('/exams/create')" />
        </div>
      </div>

      <div class="card feature-card plain-card">
        <h2 class="feature-title">
          <span class="feature-icon-wrapper">
            <i class="pi pi-list feature-icon" aria-hidden="true"></i>
          </span>
          Lihat Ujian
        </h2>
        <div class="feature-content">
          <p>Lihat daftar ujian yang telah dibuat dan kelola pertanyaan.</p>
        </div>
        <div class="feature-footer">
          <Button class="w-full" label="Lihat Ujian" icon="pi pi-list" @click="navigateTo('/exams')" />
        </div>
      </div>

      <div class="card feature-card plain-card">
        <h2 class="feature-title">
          <span class="feature-icon-wrapper">
            <i class="pi pi-chart-bar feature-icon" aria-hidden="true"></i>
          </span>
          Bandingkan RAG
        </h2>
        <div class="feature-content">
          <p>Bandingkan hasil retrieval dari BM25 dan DPR untuk analisis.</p>
        </div>
        <div class="feature-footer">
          <Button class="w-full" label="Bandingkan RAG" icon="pi pi-chart-bar" @click="navigateTo('/compare-rag')" />
        </div>
      </div>
    </div>

    <div class="info-section card">
      <h2>Tentang Sistem AES</h2>
      <p>
        Sistem Automated Essay Scoring (AES) ini menggunakan model bahasa besar (LLM) Llama-3.2 dan teknik Retrieval-Augmented Generation (RAG) 
        untuk menilai jawaban esai siswa secara otomatis. Sistem ini menggunakan dua metode retrieval: BM25 dan Dense Passage Retrieval (DPR) 
        untuk mengambil konten yang relevan dari buku referensi.
      </p>
      <p>
        Sistem ini dapat membantu guru dalam menilai jawaban esai siswa dengan lebih efisien dan konsisten, 
        sambil memberikan umpan balik yang konstruktif kepada siswa.
      </p>
      
      <div class="navigation-buttons">
        <h3>Navigasi Langsung</h3>
        <div class="button-group">
          <Button label="Daftar Ujian" icon="pi pi-list" @click="navigateTo('/exams')" class="p-button-primary" />
          <Button label="Buat Ujian Baru" icon="pi pi-plus" @click="navigateTo('/exams/create')" class="p-button-success" />
          <Button label="Buat Sesi Ujian" icon="pi pi-users" @click="navigateTo('/sessions/create')" class="p-button-warning" />
          <Button label="Bandingkan RAG" icon="pi pi-chart-bar" @click="navigateTo('/compare-rag')" class="p-button-info" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
}

.page-title {
  font-size: 2rem;
  color: var(--primary-color);
  margin-bottom: 0.5rem;
}

.page-subtitle {
  font-size: 1.2rem;
  color: var(--secondary-color);
  margin-bottom: 2rem;
}

.status-card {
  margin-bottom: 2rem;
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-indicator {
  padding: 0.5rem 1rem;
  border-radius: 20px;
  background-color: #FEE2E2;
  color: #EF4444;
  font-weight: 600;
}

.status-indicator.active {
  background-color: #DCFCE7;
  color: #10B981;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.feature-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* Ratakan struktur internal Card PrimeVue */
/* Kartu plain mengikuti gaya section "Tentang Sistem AES" */
.plain-card {
  border: 1px solid var(--border-color);
  border-radius: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
  padding: 1rem;
}
.plain-card:hover {
  box-shadow: 0 4px 14px rgba(0,0,0,0.08);
  transform: translateY(-1px);
  transition: all .2s ease;
}

.feature-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 1.1rem;
}

.feature-icon-wrapper {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background-color: rgba(59, 130, 246, 0.1);
  margin-right: 8px;
}

.feature-icon {
  color: var(--primary-color);
  font-size: 1rem;
}

.feature-content {
  min-height: 64px;
}

/* Tombol full width dan konsisten */
.w-full {
  width: 100%;
}

.feature-title {
  margin: 0 0 .75rem 0;
  color: var(--primary-color);
  display: flex;
  align-items: center;
  gap: .5rem;
  font-size: 1.1rem;
}

.feature-footer { margin-top: auto; }

.info-section {
  margin-top: 2rem;
}

.info-section h2 {
  margin-bottom: 1rem;
  color: var(--primary-color);
}

.info-section p {
  margin-bottom: 1rem;
  line-height: 1.6;
}

.navigation-buttons {
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-color);
}

.navigation-buttons h3 {
  margin-bottom: 1rem;
  color: var(--primary-color);
}

.button-group {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .features-grid {
    grid-template-columns: 1fr;
  }
}
</style>
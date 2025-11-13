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
    <div class="welcome-banner">
      <div class="welcome-content">
    <h1 class="page-title">Selamat Datang di Sistem Automated Essay Scoring</h1>
    <p class="page-subtitle">
      Sistem penilaian otomatis jawaban esai menggunakan LLM dan RAG
    </p>
      </div>
      <div class="status-badge" :class="{ 'active': systemStatus === 'Aktif' }">
          <span v-if="loading"><ProgressSpinner style="width: 20px; height: 20px;" /></span>
        <span v-else>{{ systemStatus === 'Aktif' ? 'Sistem Aktif' : 'Sistem Tidak Aktif' }}</span>
      </div>
    </div>

    <div class="section-title">
      <h2>Aplikasi dan Layanan</h2>
    </div>
    
    <div class="app-grid">
      <div class="feature-card" @click="navigateTo('/exams')">
        <span class="feature-icon-wrapper">
          <i class="pi pi-list feature-icon"></i>
        </span>
        <div class="feature-content">
          <h3 class="feature-title">Kelola Ujian</h3>
          <p class="feature-description">Daftar ujian yang telah dibuat</p>
        </div>
      </div>
      
      <div class="feature-card" @click="navigateTo('/exams/create')">
        <span class="feature-icon-wrapper">
          <i class="pi pi-plus feature-icon"></i>
        </span>
        <div class="feature-content">
          <h3 class="feature-title">Buat Ujian</h3>
          <p class="feature-description">Buat ujian dengan soal esai</p>
        </div>
      </div>

      <div class="feature-card" @click="navigateTo('/sessions/create')">
        <span class="feature-icon-wrapper">
          <i class="pi pi-users feature-icon"></i>
        </span>
        <div class="feature-content">
          <h3 class="feature-title">Sesi Ujian</h3>
          <p class="feature-description">Buat dan kelola sesi ujian</p>
        </div>
      </div>
      
      <div class="feature-card" @click="navigateTo('/students')">
        <span class="feature-icon-wrapper">
          <i class="pi pi-user feature-icon"></i>
        </span>
        <div class="feature-content">
          <h3 class="feature-title">Data Siswa</h3>
          <p class="feature-description">Kelola data siswa</p>
        </div>
      </div>

      <div class="feature-card" @click="navigateTo('/compare-rag')">
        <span class="feature-icon-wrapper">
          <i class="pi pi-chart-bar feature-icon"></i>
        </span>
        <div class="feature-content">
          <h3 class="feature-title">Analisis RAG</h3>
          <p class="feature-description">Bandingkan metode retrieval</p>
        </div>
      </div>
      
      <div class="feature-card" @click="navigateTo('/sessions/history')">
        <span class="feature-icon-wrapper">
          <i class="pi pi-history feature-icon"></i>
        </span>
        <div class="feature-content">
          <h3 class="feature-title">History Sesi</h3>
          <p class="feature-description">Lihat history sesi ujian</p>
        </div>
      </div>
    </div>

    <div class="section-title">
      <h2>Pengumuman</h2>
    </div>
    
    <div class="card announcement-card">
      <div class="announcement-header">
        <h3>Selamat Datang di AES System</h3>
        <span class="announcement-date">29 Oktober 2025</span>
      </div>
      <div class="announcement-content">
      <p>
          Sistem Automated Essay Scoring (AES) ini menggunakan model bahasa besar (LLM) Llama-3.2 dan teknik 
          Retrieval-Augmented Generation (RAG) untuk menilai jawaban esai siswa secara otomatis.
      </p>
      <p>
        Sistem ini dapat membantu guru dalam menilai jawaban esai siswa dengan lebih efisien dan konsisten, 
        sambil memberikan umpan balik yang konstruktif kepada siswa.
      </p>
      </div>
    </div>
      
    <div class="card announcement-card">
      <div class="announcement-header">
        <h3>Fitur Terbaru: Manajemen Siswa</h3>
        <span class="announcement-date">28 Oktober 2025</span>
      </div>
      <div class="announcement-content">
        <p>
          Fitur manajemen siswa telah ditambahkan ke sistem. Sekarang Anda dapat mengelola data siswa, 
          melihat history ujian mereka, dan memilih siswa spesifik untuk sesi ujian.
        </p>
      </div>
    </div>
    
    <div class="section-title">
      <h2>Tentang Sistem</h2>
        </div>
    
    <div class="card info-card">
      <h3>Automated Essay Scoring dengan LLM dan RAG</h3>
      <div class="info-content">
        <p>
          Sistem ini menggunakan dua metode retrieval: BM25 (Sparse Retrieval) dan Dense Passage Retrieval (DPR) 
          untuk mengambil konten yang relevan dari buku referensi. Selain itu, sistem juga menggunakan metode Hybrid
          yang menggabungkan kelebihan dari kedua metode tersebut.
        </p>
        <p>
          Model bahasa yang digunakan adalah Llama-3.2, yang telah dioptimasi untuk memberikan penilaian
          yang akurat dan konsisten terhadap jawaban esai siswa.
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.home {
  max-width: 1200px;
  margin: 0 auto;
}

/* Welcome banner */
.welcome-banner {
  background-color: white;
  border-radius: 8px;
  padding: 2rem;
  margin-bottom: 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--border-color);
}

.welcome-content {
  flex: 1;
}

.page-title {
  font-size: 1.75rem;
  color: var(--myits-blue);
  margin-bottom: 0.5rem;
  font-weight: 600;
}

.page-subtitle {
  font-size: 1.1rem;
  color: var(--secondary-color);
  margin: 0;
}

.status-badge {
  padding: 0.5rem 1rem;
  border-radius: 20px;
  background-color: #FEE2E2;
  color: #EF4444;
  font-weight: 600;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-badge.active {
  background-color: #DCFCE7;
  color: #10B981;
}

/* Section title */
.section-title {
  margin: 2rem 0 1rem 0;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border-color);
}

.section-title h2 {
  font-size: 1.25rem;
  color: var(--myits-blue);
  font-weight: 600;
  margin: 0;
}

/* App grid */
.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.feature-card {
  display: flex;
  align-items: center;
  padding: 1.25rem;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  margin-bottom: 0.5rem;
  border: 1px solid var(--border-color);
  transition: transform 0.2s, box-shadow 0.2s;
  cursor: pointer;
}

.feature-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.feature-icon-wrapper {
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 48px !important;
  height: 48px !important;
  border-radius: 12px !important;
  background-color: rgba(59, 130, 246, 0.1) !important;
  margin-right: 1rem !important;
  color: var(--myits-blue) !important;
}

.feature-icon {
  font-size: 1.5rem !important;
  color: var(--myits-blue) !important;
}

.feature-content {
  flex: 1;
}

.feature-title {
  font-weight: 600;
  margin: 0 0 0.25rem 0;
  font-size: 1rem;
  color: var(--myits-blue);
}

.feature-description {
  font-size: 0.875rem;
  color: var(--secondary-color);
  margin: 0;
}

/* Announcement card */
.announcement-card {
  margin-bottom: 1rem;
}

.announcement-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.announcement-header h3 {
  font-size: 1.125rem;
  color: var(--myits-blue);
  margin: 0;
  font-weight: 600;
}

.announcement-date {
  font-size: 0.875rem;
  color: var(--secondary-color);
}

.announcement-content p {
  font-size: 0.9375rem;
  line-height: 1.6;
  margin-bottom: 1rem;
}

.announcement-content p:last-child {
  margin-bottom: 0;
}

/* Info card */
.info-card h3 {
  font-size: 1.125rem;
  color: var(--myits-blue);
  margin: 0 0 1rem 0;
  font-weight: 600;
}

.info-content p {
  font-size: 0.9375rem;
  line-height: 1.6;
  margin-bottom: 1rem;
}

.info-content p:last-child {
  margin-bottom: 0;
}

@media (max-width: 768px) {
  .welcome-banner {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .status-badge {
    margin-top: 1rem;
  }
  
  .app-grid {
    grid-template-columns: 1fr;
  }
}
</style>
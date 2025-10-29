<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { ref, onMounted } from 'vue'
import NavigationHelper from './components/NavigationHelper.vue'

// PrimeVue Components
import Menubar from 'primevue/menubar'
import Toast from 'primevue/toast'

// Referensi ke NavigationHelper
const navHelper = ref(null)

// Menu items
const menuItems = ref([
  {
    label: 'Beranda',
    icon: 'pi pi-fw pi-home',
    command: () => {
      if (navHelper.value) {
        navHelper.value.navigateTo('/')
      }
    }
  },
  {
    label: 'Ujian',
    icon: 'pi pi-fw pi-file',
    items: [
      {
        label: 'Daftar Ujian',
        icon: 'pi pi-fw pi-list',
        command: () => {
          if (navHelper.value) {
            navHelper.value.navigateTo('/exams')
          }
        }
      },
      {
        label: 'Buat Ujian Baru',
        icon: 'pi pi-fw pi-plus',
        command: () => {
          if (navHelper.value) {
            navHelper.value.navigateTo('/exams/create')
          }
        }
      }
    ]
  },
  {
    label: 'Sesi Ujian',
    icon: 'pi pi-fw pi-users',
    items: [
      {
        label: 'Buat Sesi Ujian',
        icon: 'pi pi-fw pi-plus',
        command: () => {
          if (navHelper.value) {
            navHelper.value.navigateTo('/sessions/create')
          }
        }
      }
    ]
  },
  {
    label: 'Bandingkan RAG',
    icon: 'pi pi-fw pi-chart-bar',
    command: () => {
      if (navHelper.value) {
        navHelper.value.navigateTo('/compare-rag')
      }
    }
  },
  {
    label: 'Tentang',
    icon: 'pi pi-fw pi-info-circle',
    command: () => {
      if (navHelper.value) {
        navHelper.value.navigateTo('/about')
      }
    }
  }
])
</script>

<template>
  <div class="app-container">
    <Toast />
    
    <NavigationHelper ref="navHelper" />
    
    <header class="app-header">
      <div class="app-title">
        <h1>Automated Essay Scoring</h1>
      </div>
      <div class="menubar-container">
        <Menubar :model="menuItems" class="app-menubar" />
      </div>
    </header>

    <main class="app-content">
      <div class="router-view-container">
        <RouterView v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <Suspense>
              <template #default>
                <component :is="Component" />
              </template>
              <template #fallback>
                <div class="loading-container">
                  <ProgressSpinner />
                  <p>Memuat halaman...</p>
                </div>
              </template>
            </Suspense>
          </transition>
        </RouterView>
      </div>
    </main>

    <footer class="app-footer">
      <p>&copy; {{ new Date().getFullYear() }} - Automated Essay Scoring dengan LLM dan RAG</p>
    </footer>
  </div>
</template>

<style>
/* Global styles */
:root {
  --primary-color: #3B82F6;
  --secondary-color: #64748B;
  --accent-color: #10B981;
  --background-color: #F8FAFC;
  --text-color: #334155;
  --border-color: #E2E8F0;
}

html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background-color: var(--background-color) !important;
  color: var(--text-color) !important;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  color: var(--text-color) !important;
  background-color: var(--background-color) !important;
  line-height: 1.6;
  width: 100%;
  margin: 0;
  padding: 0;
  overflow-x: hidden;
}

.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  width: 100%;
  max-width: 100%;
  background-color: var(--background-color);
}

.app-header {
  background-color: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 1rem;
  width: 100%;
  display: flex;
  flex-direction: column;
}

.menubar-container {
  width: 100%;
  margin-top: 1rem;
}

.app-title {
  margin-bottom: 1rem;
  color: var(--primary-color);
}

.app-menubar {
  border: none !important;
}

.app-content {
  flex: 1;
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  background-color: var(--background-color);
}

.app-footer {
  background-color: white;
  text-align: center;
  padding: 1rem;
  border-top: 1px solid var(--border-color);
  margin-top: 2rem;
  width: 100%;
}

/* Utility classes */
.card {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

.text-center {
  text-align: center;
}

.mb-2 {
  margin-bottom: 0.5rem;
}

.mb-4 {
  margin-bottom: 1rem;
}

.mt-4 {
  margin-top: 1rem;
}

.flex {
  display: flex;
}

.flex-col {
  flex-direction: column;
}

.items-center {
  align-items: center;
}

.justify-between {
  justify-content: space-between;
}

.gap-4 {
  gap: 1rem;
}

/* Responsive */
@media (max-width: 768px) {
  .app-content {
    padding: 1rem;
  }
}

/* Animasi transisi halaman */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Loading container */
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3rem 0;
  min-height: 400px;
}

.loading-container p {
  margin-top: 1rem;
  color: var(--secondary-color);
}
</style>

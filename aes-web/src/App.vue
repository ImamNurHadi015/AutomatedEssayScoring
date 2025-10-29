<script setup>
import { RouterLink, RouterView } from 'vue-router'
import { ref, onMounted, computed } from 'vue'
import NavigationHelper from './components/NavigationHelper.vue'

// PrimeVue Components
import Menubar from 'primevue/menubar'
import Toast from 'primevue/toast'
import Sidebar from 'primevue/sidebar'
import Menu from 'primevue/menu'
import Button from 'primevue/button'
import Avatar from 'primevue/avatar'
import Badge from 'primevue/badge'
import OverlayPanel from 'primevue/overlaypanel'
import Divider from 'primevue/divider'
import ProgressSpinner from 'primevue/progressspinner'

// Referensi ke NavigationHelper
const navHelper = ref(null)
const sidebarVisible = ref(false)
const userMenuRef = ref(null)
const notificationPanelRef = ref(null)
const notificationCount = ref(2)

// User info
const user = ref({
  name: 'Admin AES',
  role: 'Administrator',
  avatar: null
})

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
      },
      {
        label: 'History Sesi',
        icon: 'pi pi-fw pi-history',
        command: () => {
          if (navHelper.value) {
            navHelper.value.navigateTo('/sessions/history')
          }
        }
      }
    ]
  },
  {
    label: 'Siswa',
    icon: 'pi pi-fw pi-user',
    command: () => {
      if (navHelper.value) {
        navHelper.value.navigateTo('/students')
      }
    }
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

// Sidebar menu items
const sidebarItems = ref([
  {
    label: 'Aplikasi dan Layanan',
    items: [
      {
        label: 'AES Dashboard',
        icon: 'pi pi-home',
        command: () => navHelper.value?.navigateTo('/')
      }
    ]
  },
  {
    label: 'Akun',
    items: [
      {
        label: 'Profil',
        icon: 'pi pi-user-edit',
        command: () => navHelper.value?.navigateTo('/account')
      },
      {
        label: 'Pengaturan',
        icon: 'pi pi-cog',
        command: () => navHelper.value?.navigateTo('/settings')
      }
    ]
  },
  {
    label: 'Pengumuman',
    items: [
      {
        label: 'Notifikasi',
        icon: 'pi pi-bell',
        command: () => navHelper.value?.navigateTo('/notifications')
      },
      {
        label: 'Berita',
        icon: 'pi pi-megaphone',
        command: () => navHelper.value?.navigateTo('/news')
      }
    ]
  }
])

// User menu items
const userMenuItems = ref([
  {
    label: 'Profil',
    icon: 'pi pi-user',
    command: () => navHelper.value?.navigateTo('/account')
  },
  {
    label: 'Pengaturan',
    icon: 'pi pi-cog',
    command: () => navHelper.value?.navigateTo('/settings')
  },
  {
    separator: true
  },
  {
    label: 'Keluar',
    icon: 'pi pi-sign-out',
    command: () => console.log('Logout')
  }
])

// Notification items
const notifications = ref([
  {
    id: 1,
    title: 'Ujian Baru',
    message: 'Ujian IPA telah dibuat dan siap untuk digunakan',
    time: '10 menit yang lalu',
    read: false
  },
  {
    id: 2,
    title: 'Sesi Selesai',
    message: 'Sesi ujian "IPA Kelas 8" telah selesai',
    time: '1 jam yang lalu',
    read: false
  }
])

const unreadNotifications = computed(() => {
  return notifications.value.filter(n => !n.read).length
})

const showUserMenu = (event) => {
  userMenuRef.value.toggle(event)
}

const showNotifications = (event) => {
  notificationPanelRef.value.toggle(event)
}

const markAsRead = (id) => {
  const notification = notifications.value.find(n => n.id === id)
  if (notification) {
    notification.read = true
  }
}

const markAllAsRead = () => {
  notifications.value.forEach(n => n.read = true)
}
</script>

<template>
  <div class="app-container">
    <Toast />
    
    <NavigationHelper ref="navHelper" />
    
    <!-- Sidebar -->
    <Sidebar v-model:visible="sidebarVisible" :baseZIndex="1000" class="custom-sidebar">
      <div class="sidebar-header">
        <div class="sidebar-logo">
          <h2>AES System</h2>
        </div>
      </div>
      
      <div class="sidebar-content">
        <div v-for="(section, i) in sidebarItems" :key="i" class="sidebar-section">
          <h3 class="sidebar-section-title">{{ section.label }}</h3>
          <div class="sidebar-menu-items">
            <div v-for="(item, j) in section.items" :key="j" 
                class="sidebar-menu-item"
                @click="item.command">
              <span class="sidebar-menu-icon">
                <i :class="'pi ' + item.icon"></i>
              </span>
              <span class="sidebar-menu-label">{{ item.label }}</span>
            </div>
          </div>
        </div>
      </div>
    </Sidebar>
    
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <Button icon="pi pi-bars" text @click="sidebarVisible = !sidebarVisible" />
        <div class="app-title">
          <h1>Automated Essay Scoring</h1>
        </div>
      </div>
      
      <div class="header-right">
        <!-- Notification button -->
        <div class="notification-wrapper">
          <Button icon="pi pi-bell" text rounded aria-label="Notifikasi" @click="showNotifications" />
          <Badge v-if="unreadNotifications > 0" :value="unreadNotifications" severity="danger" />
          
          <OverlayPanel ref="notificationPanelRef" :showCloseIcon="true" class="notification-panel">
            <template #header>
              <div class="notification-header">
                <h3>Notifikasi</h3>
                <Button v-if="unreadNotifications > 0" 
                       label="Tandai semua sudah dibaca" 
                       text 
                       size="small" 
                       @click="markAllAsRead" />
              </div>
            </template>
            
            <div class="notification-list">
              <div v-if="notifications.length === 0" class="notification-empty">
                <p>Tidak ada notifikasi</p>
              </div>
              <div v-for="notification in notifications" :key="notification.id" 
                  :class="['notification-item', {'unread': !notification.read}]"
                  @click="markAsRead(notification.id)">
                <div class="notification-content">
                  <h4>{{ notification.title }}</h4>
                  <p>{{ notification.message }}</p>
                  <small>{{ notification.time }}</small>
                </div>
              </div>
            </div>
          </OverlayPanel>
        </div>
        
        <!-- User menu -->
        <div class="user-menu-wrapper">
          <Button class="user-button" text @click="showUserMenu">
            <Avatar :image="user.avatar" :label="user.name.charAt(0)" shape="circle" size="normal" />
            <span class="user-name">{{ user.name }}</span>
            <i class="pi pi-chevron-down"></i>
          </Button>
          
          <Menu ref="userMenuRef" :model="userMenuItems" :popup="true" />
        </div>
      </div>
    </header>

    <!-- Main content -->
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
  --sidebar-width: 280px;
  --header-height: 64px;
  --myits-blue: #013880;
  --myits-light-blue: #0b63d0;
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

/* Header styles */
.app-header {
  background-color: white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 0 1.5rem;
  width: 100%;
  height: var(--header-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.app-title {
  color: var(--myits-blue);
  margin: 0;
}

.app-title h1 {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0;
}

/* Sidebar styles */
.custom-sidebar {
  width: var(--sidebar-width) !important;
  max-width: 90vw !important;
}

.p-sidebar-content {
  padding: 0 !important;
}

.sidebar-header {
  padding: 1rem;
  background-color: var(--myits-blue);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--header-height);
}

.sidebar-logo {
  text-align: center;
}

.sidebar-logo h2 {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0;
}

.sidebar-content {
  padding: 1rem 0;
}

.sidebar-section {
  margin-bottom: 1.5rem;
}

.sidebar-section-title {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--secondary-color);
  padding: 0.5rem 1.5rem;
  text-transform: uppercase;
}

.sidebar-menu-items {
  display: flex;
  flex-direction: column;
}

.sidebar-menu-item {
  display: flex;
  align-items: center;
  padding: 0.75rem 1.5rem;
  cursor: pointer;
  transition: background-color 0.2s;
}

.sidebar-menu-item:hover {
  background-color: rgba(59, 130, 246, 0.1);
}

.sidebar-menu-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 0.75rem;
  color: var(--secondary-color);
}

.sidebar-menu-label {
  font-size: 0.9375rem;
  font-weight: 500;
}

/* User menu styles */
.user-menu-wrapper {
  position: relative;
}

.user-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 0.375rem;
}

.user-name {
  font-weight: 500;
  font-size: 0.875rem;
  margin-right: 0.25rem;
}

/* Notification styles */
.notification-wrapper {
  position: relative;
}

.p-badge {
  position: absolute;
  top: -5px;
  right: -5px;
}

.notification-panel {
  width: 350px;
  max-width: 90vw;
}

.notification-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
}

.notification-header h3 {
  font-size: 1rem;
  margin: 0;
}

.notification-list {
  max-height: 400px;
  overflow-y: auto;
}

.notification-item {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border-color);
  cursor: pointer;
  transition: background-color 0.2s;
}

.notification-item:hover {
  background-color: rgba(59, 130, 246, 0.05);
}

.notification-item.unread {
  background-color: rgba(59, 130, 246, 0.1);
}

.notification-content h4 {
  font-size: 0.875rem;
  margin: 0 0 0.25rem 0;
}

.notification-content p {
  font-size: 0.8125rem;
  margin: 0 0 0.25rem 0;
  color: var(--secondary-color);
}

.notification-content small {
  font-size: 0.75rem;
  color: var(--secondary-color);
}

.notification-empty {
  padding: 1.5rem;
  text-align: center;
  color: var(--secondary-color);
}

/* Main content */
.app-content {
  flex: 1;
  padding: 2rem;
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  background-color: var(--background-color);
}

.router-view-container {
  width: 100%;
}

/* Footer */
.app-footer {
  background-color: white;
  text-align: center;
  padding: 1rem;
  border-top: 1px solid var(--border-color);
  margin-top: 2rem;
  width: 100%;
  font-size: 0.875rem;
  color: var(--secondary-color);
}

/* Card styles */
.card {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  border: 1px solid var(--border-color);
}

/* Utility classes */
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
  
  .app-header {
    padding: 0 1rem;
  }
  
  .user-name {
    display: none;
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

/* Loading overlay */
.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.8);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.loading-overlay-content {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  padding: 2rem;
  text-align: center;
  max-width: 90%;
  width: 400px;
}

.loading-overlay-title {
  font-size: 1.25rem;
  font-weight: 600;
  margin-bottom: 1rem;
  color: var(--myits-blue);
}

.loading-overlay-subtitle {
  font-size: 0.9375rem;
  color: var(--secondary-color);
  margin-bottom: 1.5rem;
}

.loading-progress {
  margin: 1.5rem 0;
}

/* Feature card styles for homepage */
.feature-card {
  display: flex;
  align-items: center;
  padding: 1.25rem;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  margin-bottom: 1rem;
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
  margin-bottom: 0.25rem;
}

.feature-description {
  font-size: 0.875rem;
  color: var(--secondary-color);
}

/* Fix for PrimeVue components */
.p-button.p-button-text {
  color: var(--myits-blue);
}

.p-button.p-button-text:hover {
  background: rgba(59, 130, 246, 0.04);
  color: var(--myits-light-blue);
}

.p-button.p-button-primary {
  background: var(--myits-blue);
  border-color: var(--myits-blue);
}

.p-button.p-button-primary:hover {
  background: var(--myits-light-blue);
  border-color: var(--myits-light-blue);
}

/* Fix for icons */
.pi {
  display: inline-block !important;
  visibility: visible !important;
  opacity: 1 !important;
}
</style>

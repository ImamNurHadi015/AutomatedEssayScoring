<script setup>
import { ref } from 'vue'
import Card from 'primevue/card'
import Button from 'primevue/button'
</script>

<template>
  <div class="settings-page">
    <h1 class="page-title">Pengaturan</h1>
    
    <div class="card coming-soon-card">
      <div class="coming-soon-content">
        <i class="pi pi-cog coming-soon-icon"></i>
        <h2>Coming Soon</h2>
        <p>Halaman pengaturan sedang dalam pengembangan. Fitur ini akan segera tersedia.</p>
        <Button label="Kembali ke Beranda" icon="pi pi-home" @click="$router.push('/')" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-title {
  font-size: 1.75rem;
  color: var(--myits-blue);
  margin-bottom: 1.5rem;
  font-weight: 600;
}

.coming-soon-card {
  padding: 3rem;
  text-align: center;
}

.coming-soon-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.coming-soon-icon {
  font-size: 4rem;
  color: var(--myits-blue);
  margin-bottom: 1rem;
}

.coming-soon-content h2 {
  font-size: 1.75rem;
  color: var(--myits-blue);
  margin: 0;
}

.coming-soon-content p {
  font-size: 1.1rem;
  color: var(--secondary-color);
  margin-bottom: 2rem;
  max-width: 500px;
}
</style>

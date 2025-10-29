<template>
  <div class="error-page">
    <h1>Halaman Tidak Tersedia</h1>
    <p>Maaf, halaman yang Anda cari tidak tersedia atau terjadi kesalahan.</p>
    <div class="actions">
      <Button label="Kembali ke Beranda" icon="pi pi-home" @click="$router.push('/')" />
    </div>
  </div>
</template>

<style scoped>
.error-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  text-align: center;
}

h1 {
  color: var(--primary-color);
  margin-bottom: 1rem;
}

p {
  margin-bottom: 2rem;
  font-size: 1.1rem;
  color: var(--secondary-color);
}

.actions {
  margin-top: 1rem;
}
</style>

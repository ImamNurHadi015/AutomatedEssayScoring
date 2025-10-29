<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

// Metode untuk navigasi
const navigateTo = (path) => {
  console.log('Navigating to:', path)
  router.push(path)
}

// Ekspos metode untuk digunakan oleh komponen lain
defineExpose({
  navigateTo
})
</script>

<template>
  <!-- Komponen ini tidak merender apapun -->
</template>

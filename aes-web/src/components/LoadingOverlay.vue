<script setup>
import { ref, watch } from 'vue'
import ProgressBar from 'primevue/progressbar'
import ProgressSpinner from 'primevue/progressspinner'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    default: 'Sedang Memproses'
  },
  message: {
    type: String,
    default: 'Mohon tunggu sebentar...'
  },
  progress: {
    type: Number,
    default: null
  },
  indeterminate: {
    type: Boolean,
    default: true
  }
})

const showProgress = ref(false)
const currentProgress = ref(0)

watch(() => props.visible, (newValue) => {
  if (newValue && props.indeterminate) {
    // Reset dan mulai progress bar simulasi jika indeterminate
    currentProgress.value = 0
    showProgress.value = true
    simulateProgress()
  } else {
    showProgress.value = false
  }
})

watch(() => props.progress, (newValue) => {
  if (newValue !== null) {
    currentProgress.value = newValue
    showProgress.value = true
  }
})

const simulateProgress = () => {
  if (!props.visible) return
  
  // Simulasi progress untuk memberikan feedback visual
  const interval = setInterval(() => {
    if (currentProgress.value < 90) {
      // Increment dengan kecepatan yang semakin lambat
      if (currentProgress.value < 30) {
        currentProgress.value += 5
      } else if (currentProgress.value < 60) {
        currentProgress.value += 3
      } else if (currentProgress.value < 80) {
        currentProgress.value += 1
      } else {
        currentProgress.value += 0.5
      }
    } else {
      clearInterval(interval)
    }
    
    if (!props.visible) {
      clearInterval(interval)
    }
  }, 300)
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="loading-overlay">
      <div class="loading-overlay-content">
        <ProgressSpinner style="width: 50px; height: 50px" />
        
        <h3 class="loading-overlay-title">{{ title }}</h3>
        <p class="loading-overlay-subtitle">{{ message }}</p>
        
        <div v-if="showProgress" class="loading-progress">
          <ProgressBar :value="currentProgress" />
          <div class="progress-text">{{ Math.round(currentProgress) }}%</div>
        </div>
        
        <div class="loading-steps">
          <div class="loading-step">
            <i class="pi pi-check-circle"></i>
            <span>Memuat pertanyaan</span>
          </div>
          <div class="loading-step">
            <i class="pi pi-sync pi-spin"></i>
            <span>Menganalisis jawaban</span>
          </div>
          <div class="loading-step loading-step-pending">
            <i class="pi pi-clock"></i>
            <span>Menilai jawaban dengan LLM</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
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
  margin-top: 1rem;
  margin-bottom: 0.5rem;
  color: var(--myits-blue);
}

.loading-overlay-subtitle {
  font-size: 0.9375rem;
  color: var(--secondary-color);
  margin-bottom: 1rem;
}

.loading-progress {
  margin: 1.5rem 0;
}

.progress-text {
  margin-top: 0.5rem;
  font-size: 0.875rem;
  color: var(--secondary-color);
}

.loading-steps {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  text-align: left;
  margin-top: 1rem;
  gap: 0.75rem;
}

.loading-step {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.875rem;
}

.loading-step i {
  color: var(--accent-color);
  font-size: 1rem;
}

.loading-step.loading-step-pending i {
  color: var(--secondary-color);
}

.loading-step-pending {
  color: var(--secondary-color);
}
</style>

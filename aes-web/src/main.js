import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import axios from 'axios'
import { API_URL } from './config'

// PrimeVue
import 'primevue/resources/themes/lara-light-blue/theme.css'
import 'primeicons/primeicons.css'
import PrimeVuePlugin from './plugins/primevue'

// Custom CSS
import './assets/main.css'
import './assets/fix-styles.css'

// Konfigurasi axios
axios.defaults.baseURL = API_URL

const app = createApp(App)

app.use(router)
app.use(PrimeVuePlugin)

// Debug
console.log('App initialized with PrimeVue plugin')

app.mount('#app')

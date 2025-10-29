// PrimeVue plugin setup
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'

// PrimeVue Components
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Card from 'primevue/card'
import Toast from 'primevue/toast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Menubar from 'primevue/menubar'
import ProgressSpinner from 'primevue/progressspinner'
import Divider from 'primevue/divider'
import TabView from 'primevue/tabview'
import TabPanel from 'primevue/tabpanel'
import Badge from 'primevue/badge'
import Chart from 'primevue/chart'

export default {
  install: (app) => {
    // Use PrimeVue
    app.use(PrimeVue, { ripple: true })
    app.use(ToastService)
    
    // Register components
    app.component('Button', Button)
    app.component('InputText', InputText)
    app.component('Textarea', Textarea)
    app.component('Card', Card)
    app.component('Toast', Toast)
    app.component('DataTable', DataTable)
    app.component('Column', Column)
    app.component('Menubar', Menubar)
    app.component('ProgressSpinner', ProgressSpinner)
    app.component('Divider', Divider)
    app.component('TabView', TabView)
    app.component('TabPanel', TabPanel)
    app.component('Badge', Badge)
    app.component('Chart', Chart)
    
    console.log('PrimeVue components registered globally')
  }
}

import axios from 'axios'

// Exam API
export const examApi = {
  // Mendapatkan semua ujian
  getExams() {
    return axios.get('/exams')
  },
  
  // Mendapatkan detail ujian berdasarkan ID
  getExam(id) {
    return axios.get(`/exams/${id}`)
  },

  // Memperbarui ujian
  updateExam(id, examData) {
    return axios.patch(`/exams/${id}`, examData)
  },
  
  // Membuat ujian baru
  createExam(examData) {
    return axios.post('/exams', examData)
  },
  
  // Mendapatkan semua pertanyaan untuk ujian tertentu
  getExamQuestions(examId) {
    return axios.get(`/exams/${examId}/questions`)
  }
}

// Question API
export const questionApi = {
  // Mendapatkan detail pertanyaan berdasarkan ID
  getQuestion(id) {
    return axios.get(`/questions/${id}`)
  },

  // Memperbarui pertanyaan
  updateQuestion(id, questionData) {
    return axios.patch(`/questions/${id}`, questionData)
  },
  
  // Membuat pertanyaan baru untuk ujian
  createQuestion(examId, questionData) {
    return axios.post(`/exams/${examId}/questions`, questionData)
  }
}

// Answer API
export const answerApi = {
  // Mendapatkan detail jawaban berdasarkan ID
  getAnswer(id) {
    return axios.get(`/answers/${id}`)
  },
  
  // Mengirimkan jawaban untuk pertanyaan
  submitAnswer(questionId, answerData) {
    return axios.post(`/questions/${questionId}/answers`, answerData)
  },
  
  // Membuat jawaban baru (dengan atau tanpa sesi)
  createAnswer(answerData) {
    return axios.post('/answers', answerData)
  },
  
  // Mengevaluasi ulang jawaban
  evaluateAnswer(answerId) {
    return axios.post(`/answers/${answerId}/evaluate`)
  }
}

// RAG API
export const ragApi = {
  // Membandingkan hasil RAG (BM25 vs DPR)
  compareRag(question) {
    return axios.post('/compare-rag', { question })
  },
  
  // Mendapatkan semua pertanyaan dari semua ujian untuk dropdown
  getAllQuestions() {
    return axios.get('/questions')
  }
}

// Session API
export const sessionApi = {
  // Membuat sesi ujian baru
  createSession(sessionData) {
    return axios.post('/sessions', sessionData)
  },
  
  // Mendapatkan semua sesi
  getAllSessions() {
    return axios.get('/sessions')
  },
  
  // Mendapatkan detail sesi
  getSession(id) {
    return axios.get(`/sessions/${id}`)
  },
  
  // Pindah ke siswa berikutnya dalam sesi
  nextStudent(sessionId) {
    return axios.post(`/sessions/${sessionId}/next-student`)
  },
  
  // Mendapatkan semua jawaban dalam sesi
  getSessionAnswers(sessionId) {
    return axios.get(`/sessions/${sessionId}/answers`)
  },
  
  // Mendapatkan ringkasan hasil sesi
  getSessionSummary(sessionId) {
    return axios.get(`/sessions/${sessionId}/summary`)
  }
}

// Student API
export const studentApi = {
  // Mendapatkan semua siswa
  getAllStudents() {
    return axios.get('/students')
  },
  
  // Mendapatkan detail siswa berdasarkan ID
  getStudent(id) {
    return axios.get(`/students/${id}`)
  },
  
  // Membuat siswa baru
  createStudent(studentData) {
    return axios.post('/students', studentData)
  },
  
  // Memperbarui siswa
  updateStudent(id, studentData) {
    return axios.put(`/students/${id}`, studentData)
  },
  
  // Menghapus siswa
  deleteStudent(id) {
    return axios.delete(`/students/${id}`)
  }
}

// System API
export const systemApi = {
  // Mengecek kesehatan API
  healthCheck() {
    return axios.get('/health')
  },
  
  // Menginisialisasi sistem AES
  initializeAES() {
    return axios.post('/initialize-aes')
  }
}

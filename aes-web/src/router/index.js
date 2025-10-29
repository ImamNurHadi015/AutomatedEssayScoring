import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ErrorView from '../views/ErrorView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/exams',
      name: 'exams',
      component: () => import('../views/ExamsView.vue'),
    },
    {
      path: '/exams/create',
      name: 'create-exam',
      component: () => import('../views/CreateExamView.vue'),
    },
    {
      path: '/exams/:id',
      name: 'exam-detail',
      component: () => import('../views/ExamDetailView.vue'),
      props: true,
    },
    {
      path: '/exams/:examId/questions/create',
      name: 'create-question',
      component: () => import('../views/CreateQuestionView.vue'),
      props: true,
    },
    {
      path: '/questions/:id',
      name: 'question-detail',
      component: () => import('../views/QuestionDetailView.vue'),
      props: true,
    },
    {
      path: '/questions/:id/answer',
      name: 'answer-question',
      component: () => import('../views/AnswerQuestionView.vue'),
      props: true,
    },
    {
      path: '/answers/:id',
      name: 'answer-detail',
      component: () => import('../views/AnswerDetailView.vue'),
      props: true,
    },
    {
      path: '/compare-rag',
      name: 'compare-rag',
      component: () => import('../views/CompareRagView.vue'),
    },
    {
      path: '/sessions/create',
      name: 'create-session',
      component: () => import('../views/CreateSessionView.vue'),
    },
    {
      path: '/sessions/:id',
      name: 'session-detail',
      component: () => import('../views/SessionView.vue'),
      props: true,
    },
    {
      path: '/sessions/:id/results',
      name: 'session-results',
      component: () => import('../views/SessionResultsView.vue'),
      props: true,
    },
    {
      path: '/about',
      name: 'about',
      component: () => import('../views/AboutView.vue'),
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: ErrorView
    },
  ],
})

export default router

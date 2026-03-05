import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
    },
    {
      path: '/projects',
      name: 'projects',
      component: () => import('@/views/ProjectListView.vue'),
    },
    {
      path: '/projects/:id',
      name: 'project-detail',
      component: () => import('@/views/ProjectDetailView.vue'),
      props: true,
    },
    {
      path: '/projects/:id/board',
      name: 'kanban-board',
      component: () => import('@/views/KanbanBoardView.vue'),
      props: true,
    },
    {
      path: '/tasks/:id',
      name: 'task-detail',
      component: () => import('@/views/TaskDetailView.vue'),
      props: true,
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
    },
    {
      path: '/chat/:sessionId',
      name: 'chat-session',
      component: () => import('@/views/ChatView.vue'),
      props: true,
    },
    {
      path: '/agents',
      name: 'agents',
      component: () => import('@/views/AgentsView.vue'),
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
    },
  ],
})

router.beforeEach((to) => {
  const token = localStorage.getItem('auth_token')
  if (!to.meta.public && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

export default router

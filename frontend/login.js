const { createApp } = Vue;

const RoleSwitch = {
  props: {
    role: {
      type: String,
      required: true,
    },
  },
  emits: ['update:role'],
  template: `
    <div class="tabs" role="tablist" aria-label="角色切换">
      <button
        type="button"
        :class="['tab', role === 'student' ? 'active' : '']"
        @click="$emit('update:role', 'student')"
      >
        学生
      </button>
      <button
        type="button"
        :class="['tab', role === 'teacher' ? 'active' : '']"
        @click="$emit('update:role', 'teacher')"
      >
        教师
      </button>
    </div>
  `,
};

const SessionCard = {
  props: {
    user: {
      type: Object,
      required: true,
    },
    formatTime: {
      type: Function,
      required: true,
    },
  },
  emits: ['enter-workspace', 'logout'],
  computed: {
    actionLabel() {
      return this.user.role === 'teacher' ? '进入教师页' : '进入学生页';
    },
  },
  template: `
    <section class="session-card">
      <h2>当前登录状态</h2>
      <p>账号：{{ user.account }}</p>
      <p>姓名：{{ user.name }}</p>
      <p>角色：{{ user.role }}</p>
      <p>创建时间：{{ formatTime(user.created_at) }}</p>
      <div class="action-row">
        <button class="primary" type="button" @click="$emit('enter-workspace')">{{ actionLabel }}</button>
        <button class="ghost" type="button" @click="$emit('logout')">退出登录</button>
      </div>
    </section>
  `,
};

createApp({
  components: {
    RoleSwitch,
    SessionCard,
  },
  data() {
    return {
      role: 'student',
      account: 'student001',
      password: '123456',
      loading: false,
      message: '',
      messageType: '',
      sessionUser: null,
    };
  },
  async mounted() {
    const token = localStorage.getItem('access_token');
    if (!token) {
      return;
    }

    try {
      const me = await this.fetchMe(token);
      this.sessionUser = me;
      this.role = me.role;
      this.account = me.account;
      this.password = '123456';
      this.message =
        me.role === 'teacher'
          ? '检测到教师已登录，可直接进入教师页。'
          : '检测到学生已登录，可直接进入学生页。';
      this.messageType = 'success';
    } catch {
      localStorage.removeItem('access_token');
    }
  },
  methods: {
    setRole(nextRole) {
      this.role = nextRole;
      if (!this.sessionUser || this.sessionUser.role !== nextRole) {
        this.account = nextRole === 'student' ? 'student001' : 'teacher001';
        this.password = '123456';
      }
    },

    async submitLogin() {
      this.loading = true;
      this.message = '正在登录...';
      this.messageType = '';
      this.sessionUser = null;

      const endpoint = this.role === 'teacher' ? '/api/auth/login/teacher' : '/api/auth/login/student';

      try {
        const loginRes = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account: this.account, password: this.password }),
        });

        const loginData = await loginRes.json();
        if (!loginRes.ok) {
          throw new Error(loginData.detail || '登录失败');
        }

        localStorage.setItem('access_token', loginData.access_token);
        const me = await this.fetchMe(loginData.access_token);
        this.sessionUser = me;
        this.role = me.role;
        this.account = me.account;

        this.message = me.role === 'teacher' ? '登录成功，正在进入教师页...' : '登录成功，正在进入学生页...';
        this.messageType = 'success';
        window.setTimeout(() => this.goWorkspace(), 180);
      } catch (error) {
        localStorage.removeItem('access_token');
        this.message = error.message || '登录失败';
        this.messageType = 'error';
      } finally {
        this.loading = false;
      }
    },

    async fetchMe(token) {
      const res = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        throw new Error('登录状态已失效');
      }
      return res.json();
    },

    formatTime(value) {
      if (!value) return '-';
      return new Date(value).toLocaleString('zh-CN', { hour12: false });
    },

    logout() {
      localStorage.removeItem('access_token');
      this.sessionUser = null;
      this.message = '已退出登录';
      this.messageType = '';
      this.setRole('student');
    },

    goStudent() {
      window.location.href = '/frontend/student.html';
    },

    goTeacher() {
      window.location.href = '/frontend/teacher/index.html';
    },

    goWorkspace() {
      if (this.sessionUser?.role === 'teacher') {
        this.goTeacher();
        return;
      }
      this.goStudent();
    },
  },
}).mount('#app');

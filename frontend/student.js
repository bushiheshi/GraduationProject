const { createApp, nextTick } = Vue;

if (window.marked) {
  window.marked.setOptions({
    gfm: true,
    breaks: true,
  });
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function finalizeRenderedHtml(html) {
  const wrapper = document.createElement('div');
  wrapper.innerHTML = html;

  wrapper.querySelectorAll('a').forEach((link) => {
    link.target = '_blank';
    link.rel = 'noreferrer noopener';
  });

  wrapper.querySelectorAll('pre').forEach((pre) => {
    const parent = pre.parentElement;
    if (!parent || parent.classList.contains('markdown-code-block')) {
      return;
    }

    const block = document.createElement('div');
    block.className = 'markdown-code-block';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'copy-code-btn';
    button.textContent = '复制代码';

    parent.insertBefore(block, pre);
    block.appendChild(button);
    block.appendChild(pre);
  });

  return wrapper.innerHTML;
}

function markdownToHtml(content) {
  const source = String(content ?? '').trim();
  if (!source) {
    return '';
  }

  const rawHtml = window.marked
    ? window.marked.parse(source)
    : `<p>${escapeHtml(source).replace(/\n/g, '<br>')}</p>`;

  const sanitized = window.DOMPurify
    ? window.DOMPurify.sanitize(rawHtml, { USE_PROFILES: { html: true } })
    : rawHtml;

  return finalizeRenderedHtml(sanitized);
}

function isLikelyUrl(value) {
  return /^https?:\/\//i.test(String(value || '').trim());
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', 'readonly');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();

  try {
    document.execCommand('copy');
  } finally {
    document.body.removeChild(textarea);
  }
}

function flashCopyButton(button, text) {
  const original = button.dataset.originalLabel || button.textContent || '复制代码';
  button.dataset.originalLabel = original;
  button.textContent = text;

  window.clearTimeout(Number(button.dataset.resetTimer || 0));
  const timer = window.setTimeout(() => {
    button.textContent = original;
  }, 1500);
  button.dataset.resetTimer = String(timer);
}

function createAnswerEditor(submission = null) {
  return {
    open: false,
    text: submission?.answer_text || '',
    file: null,
    fileName: '',
    submitting: false,
    message: '',
    messageType: '',
  };
}

createApp({
  data() {
    return {
      token: '',
      user: null,
      models: [],
      selectedModel: '',
      conversations: [],
      activeConversationId: null,
      records: [],
      conversationSubmission: null,
      answerEditor: createAnswerEditor(),
      prompt: '',
      loading: false,
      creatingConversation: false,
      refreshTimer: null,
      refreshingConversations: false,
      message: '',
      messageType: '',
    };
  },
  computed: {
    activeConversation() {
      return this.conversations.find((item) => item.id === this.activeConversationId) || null;
    },
  },
  async mounted() {
    this.token = localStorage.getItem('access_token') || '';
    if (!this.token) {
      this.goLogin();
      return;
    }

    try {
      const me = await this.request('/api/auth/me');
      if (me.role !== 'student') {
        throw new Error('只有学生可以进入该页面');
      }
      this.user = me;
      await this.loadModels();
      await this.loadConversations();
      this.startAutoRefresh();
      this.message = '左侧选择对话即可继续上下文';
      this.messageType = 'success';
    } catch (error) {
      this.message = error.message || '登录状态失效';
      this.messageType = 'error';
      localStorage.removeItem('access_token');
      setTimeout(() => this.goLogin(), 800);
    }
  },
  beforeUnmount() {
    window.clearInterval(this.refreshTimer);
  },
  methods: {
    renderMarkdown(content) {
      return markdownToHtml(content);
    },

    isLikelyUrl(value) {
      return isLikelyUrl(value);
    },

    async request(url, options = {}) {
      const headers = {
        ...(options.headers || {}),
        Authorization: `Bearer ${this.token}`,
      };

      const res = await fetch(url, { ...options, headers });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || '请求失败');
      }
      return data;
    },

    async loadModels() {
      const models = await this.request('/api/chat/models');
      this.models = models;
      if (!this.selectedModel && models.length > 0) {
        this.selectedModel = models[0].key;
      }
    },

    resetAnswerEditor(submission = null) {
      this.conversationSubmission = submission;
      this.answerEditor = createAnswerEditor(submission);
    },

    async loadConversations(options = {}) {
      const focusConversationId = options.focusConversationId ?? this.activeConversationId;
      const conversations = await this.request('/api/chat/conversations');
      this.conversations = conversations;

      const nextConversationId = conversations.some((item) => item.id === focusConversationId)
        ? focusConversationId
        : (conversations[0]?.id ?? null);

      this.activeConversationId = nextConversationId;
      if (nextConversationId) {
        await this.loadConversationData(nextConversationId);
      } else {
        this.records = [];
        this.resetAnswerEditor();
      }
    },

    startAutoRefresh() {
      window.clearInterval(this.refreshTimer);
      this.refreshTimer = window.setInterval(() => {
        this.refreshConversationList();
      }, 5000);
    },

    async refreshConversationList() {
      if (this.refreshingConversations || !this.token) {
        return;
      }

      this.refreshingConversations = true;
      try {
        const conversations = await this.request('/api/chat/conversations');
        const activeStillExists = this.activeConversationId
          && conversations.some((item) => item.id === this.activeConversationId);

        this.conversations = conversations;

        if (!activeStillExists && conversations.length > 0) {
          this.activeConversationId = conversations[0].id;
          await this.loadConversationData(this.activeConversationId);
        }
      } catch (error) {
        console.warn('Failed to refresh conversations', error);
      } finally {
        this.refreshingConversations = false;
      }
    },

    async loadConversationData(conversationId) {
      const [records, submission] = await Promise.all([
        this.request(`/api/chat/conversations/${conversationId}/records`),
        this.request(`/api/chat/conversations/${conversationId}/answer-submission`),
      ]);

      if (this.activeConversationId !== conversationId) {
        return;
      }

      this.records = records;
      this.resetAnswerEditor(submission);
      await nextTick();
      this.scrollThreadToBottom();
    },

    async openConversation(conversationId) {
      if (!conversationId) {
        return;
      }
      this.activeConversationId = conversationId;
      await this.loadConversationData(conversationId);
      this.message = '已切换到该对话';
      this.messageType = 'success';
    },

    async createConversation() {
      this.creatingConversation = true;
      try {
        const conversation = await this.request('/api/chat/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        await this.loadConversations({ focusConversationId: conversation.id });
        this.message = '已创建新对话';
        this.messageType = 'success';
      } catch (error) {
        this.message = error.message || '创建对话失败';
        this.messageType = 'error';
      } finally {
        this.creatingConversation = false;
      }
    },

    async ensureConversationReady() {
      if (this.activeConversationId) {
        return this.activeConversationId;
      }

      const conversation = await this.request('/api/chat/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      this.activeConversationId = conversation.id;
      await this.loadConversations({ focusConversationId: conversation.id });
      return conversation.id;
    },

    async submitPrompt() {
      if (!this.selectedModel) {
        this.message = '请先选择模型';
        this.messageType = 'error';
        return;
      }

      if (!this.prompt) {
        this.message = '请输入提示词';
        this.messageType = 'error';
        return;
      }

      this.loading = true;
      this.message = '模型生成中...';
      this.messageType = '';

      try {
        const conversationId = await this.ensureConversationReady();
        const result = await this.request('/api/chat/completions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            model: this.selectedModel,
            prompt: this.prompt,
            conversation_id: conversationId,
          }),
        });

        this.prompt = '';
        await this.loadConversations({ focusConversationId: result.conversation_id });
        this.message = `生成完成，当前对话标题：${result.conversation_title}`;
        this.messageType = 'success';
      } catch (error) {
        this.message = error.message || '调用失败';
        this.messageType = 'error';
      } finally {
        this.loading = false;
      }
    },

    toggleAnswerEditor() {
      this.answerEditor.open = !this.answerEditor.open;
      if (!this.answerEditor.open) {
        this.answerEditor.file = null;
        this.answerEditor.fileName = '';
        this.answerEditor.message = '';
        this.answerEditor.messageType = '';
        return;
      }

      if (!this.answerEditor.text && this.conversationSubmission?.answer_text) {
        this.answerEditor.text = this.conversationSubmission.answer_text;
      }
    },

    answerButtonLabel() {
      if (this.answerEditor.open) {
        return '收起提交';
      }
      return this.conversationSubmission ? '修改答案' : '提交答案';
    },

    onAnswerFileChange(event) {
      const file = event.target.files && event.target.files[0];

      if (!file) {
        this.answerEditor.file = null;
        this.answerEditor.fileName = '';
        return;
      }

      if (!/\.txt$/i.test(file.name)) {
        this.answerEditor.file = null;
        this.answerEditor.fileName = '';
        this.answerEditor.message = '仅支持上传 .txt 文件';
        this.answerEditor.messageType = 'error';
        event.target.value = '';
        return;
      }

      this.answerEditor.file = file;
      this.answerEditor.fileName = file.name;
      this.answerEditor.message = '';
      this.answerEditor.messageType = '';
    },

    clearAnswerFile() {
      this.answerEditor.file = null;
      this.answerEditor.fileName = '';
      this.answerEditor.message = '';
      this.answerEditor.messageType = '';
    },

    async submitAnswer() {
      if (!this.activeConversationId) {
        this.answerEditor.message = '请先进入一个对话';
        this.answerEditor.messageType = 'error';
        return;
      }

      if (!this.answerEditor.text.trim() && !this.answerEditor.file) {
        this.answerEditor.message = '请粘贴答案内容或上传一个 .txt 文件';
        this.answerEditor.messageType = 'error';
        return;
      }

      this.answerEditor.submitting = true;
      this.answerEditor.message = '提交中...';
      this.answerEditor.messageType = '';

      try {
        const formData = new FormData();
        if (this.answerEditor.text.trim()) {
          formData.append('answer_text', this.answerEditor.text);
        }
        if (this.answerEditor.file) {
          formData.append('answer_file', this.answerEditor.file, this.answerEditor.fileName || this.answerEditor.file.name);
        }

        const submission = await this.request(
          `/api/chat/conversations/${this.activeConversationId}/answer-submission`,
          {
            method: 'POST',
            body: formData,
          },
        );

        this.conversationSubmission = submission;
        this.answerEditor.text = submission.answer_text || '';
        this.answerEditor.file = null;
        this.answerEditor.fileName = '';
        this.answerEditor.message = '答案已提交';
        this.answerEditor.messageType = 'success';
      } catch (error) {
        this.answerEditor.message = error.message || '提交失败';
        this.answerEditor.messageType = 'error';
      } finally {
        this.answerEditor.submitting = false;
      }
    },

    async handleMarkdownClick(event) {
      const button = event.target.closest('.copy-code-btn');
      if (!button) {
        return;
      }

      const code = button.closest('.markdown-code-block')?.querySelector('pre code');
      const text = code?.textContent || '';
      if (!text.trim()) {
        flashCopyButton(button, '无可复制内容');
        return;
      }

      try {
        await copyText(text);
        flashCopyButton(button, '已复制');
      } catch {
        flashCopyButton(button, '复制失败');
      }
    },

    scrollThreadToBottom() {
      const el = this.$refs.threadScroll;
      if (!el) {
        return;
      }
      el.scrollTop = el.scrollHeight;
    },

    formatTime(value) {
      if (!value) return '-';
      return new Date(value).toLocaleString('zh-CN', { hour12: false });
    },

    formatShortTime(value) {
      if (!value) return '-';
      const date = new Date(value);
      const now = new Date();
      const sameDay = date.toDateString() === now.toDateString();
      return sameDay
        ? date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
        : date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
    },

    logout() {
      localStorage.removeItem('access_token');
      this.goLogin();
    },

    goLogin() {
      window.location.href = '/frontend/login.html';
    },
  },
}).mount('#app');

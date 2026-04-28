(() => {
  const state = {
    role: 'student',
    token: localStorage.getItem('access_token') || '',
    models: [],
  };

  const tabs = document.querySelectorAll('.tab');
  const form = document.getElementById('login-form');
  const accountInput = document.getElementById('account');
  const passwordInput = document.getElementById('password');
  const submitBtn = document.getElementById('submit-btn');
  const logoutBtn = document.getElementById('logout-btn');
  const message = document.getElementById('message');
  const userCard = document.getElementById('user-card');
  const tokenBox = document.getElementById('token-box');

  const userAccount = document.getElementById('u-account');
  const userName = document.getElementById('u-name');
  const userRole = document.getElementById('u-role');
  const userCreated = document.getElementById('u-created');

  const studentChat = document.getElementById('student-chat');
  const modelSelect = document.getElementById('model-select');
  const promptInput = document.getElementById('prompt-input');
  const chatSubmitBtn = document.getElementById('chat-submit-btn');
  const chatMessage = document.getElementById('chat-message');
  const contentBox = document.getElementById('content-box');
  const metaModel = document.getElementById('meta-model');
  const metaTime = document.getElementById('meta-time');
  const citationList = document.getElementById('citation-list');
  const historyList = document.getElementById('history-list');
  const refreshHistoryBtn = document.getElementById('refresh-history-btn');

  function setMessage(text, type = '') {
    message.textContent = text;
    message.className = `message ${type}`.trim();
  }

  function setChatMessage(text, type = '') {
    chatMessage.textContent = text;
    chatMessage.className = `message ${type}`.trim();
  }

  function setLoading(loading) {
    submitBtn.disabled = loading;
    submitBtn.classList.toggle('loading', loading);
    submitBtn.textContent = loading ? '登录中...' : '登录并获取 Token';
  }

  function setChatLoading(loading) {
    chatSubmitBtn.disabled = loading;
    refreshHistoryBtn.disabled = loading;
    chatSubmitBtn.textContent = loading ? '生成中...' : '发送到模型';
  }

  function setRole(nextRole) {
    state.role = nextRole;
    tabs.forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.role === nextRole);
    });

  }

  function setUserView(user, token) {
    userAccount.textContent = user.account;
    userName.textContent = user.name;
    userRole.textContent = user.role;
    userCreated.textContent = formatTime(user.created_at);
    tokenBox.value = token;
    userCard.classList.remove('hidden');
  }

  function clearUserView() {
    userCard.classList.add('hidden');
    tokenBox.value = '';
  }

  function formatTime(value) {
    try {
      return new Date(value).toLocaleString('zh-CN', { hour12: false });
    } catch {
      return String(value || '-');
    }
  }

  function setStudentChatVisible(visible) {
    studentChat.classList.toggle('hidden', !visible);
  }

  function clearChatResult() {
    contentBox.value = '';
    metaModel.textContent = '-';
    metaTime.textContent = '-';
    citationList.innerHTML = '';
    setChatMessage('', '');
  }

  function clearChatWorkspace() {
    state.models = [];
    modelSelect.innerHTML = '';
    promptInput.value = '';
    historyList.innerHTML = '';
    clearChatResult();
    setStudentChatVisible(false);
  }

  function renderModelOptions(models) {
    modelSelect.innerHTML = '';
    models.forEach((item) => {
      const option = document.createElement('option');
      option.value = item.key;
      option.textContent = `${item.model_name} (${item.provider})`;
      modelSelect.appendChild(option);
    });
  }

  function renderCitations(citations) {
    citationList.innerHTML = '';

    if (!Array.isArray(citations) || citations.length === 0) {
      const li = document.createElement('li');
      li.textContent = '无';
      citationList.appendChild(li);
      return;
    }

    citations.forEach((entry) => {
      const li = document.createElement('li');
      li.textContent = entry;
      citationList.appendChild(li);
    });
  }

  function renderHistory(records) {
    historyList.innerHTML = '';

    if (!Array.isArray(records) || records.length === 0) {
      const empty = document.createElement('p');
      empty.className = 'history-empty';
      empty.textContent = '暂无历史记录';
      historyList.appendChild(empty);
      return;
    }

    records.forEach((record) => {
      const card = document.createElement('div');
      card.className = 'history-item';

      const time = document.createElement('p');
      time.className = 'h-time';
      time.textContent = `${record.model_name} | ${formatTime(record.generated_at)}`;

      const prompt = document.createElement('p');
      prompt.className = 'h-prompt';
      prompt.textContent = `提示词：${record.prompt}`;

      const content = document.createElement('p');
      content.className = 'h-content';
      content.textContent = `生成内容：${record.content}`;

      card.appendChild(time);
      card.appendChild(prompt);
      card.appendChild(content);
      historyList.appendChild(card);
    });
  }

  async function requestWithToken(path, options = {}) {
    const headers = {
      ...(options.headers || {}),
      Authorization: `Bearer ${state.token}`,
    };

    const res = await fetch(path, {
      ...options,
      headers,
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || '请求失败');
    }

    return data;
  }

  async function fetchMe(token) {
    const res = await fetch('/api/auth/me', {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!res.ok) {
      throw new Error('Token 已失效，请重新登录');
    }

    return res.json();
  }

  async function login(account, password) {
    const endpoint = state.role === 'student' ? '/api/auth/login/student' : '/api/auth/login/teacher';

    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ account, password }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || '登录失败');
    }

    return data;
  }

  async function loadStudentChatData() {
    const models = await requestWithToken('/api/chat/models');
    state.models = models;
    renderModelOptions(models);

    if (models.length > 0) {
      modelSelect.value = models[0].key;
    }

    const history = await requestWithToken('/api/chat/history?limit=10');
    renderHistory(history);
  }

  async function initStudentChat() {
    setStudentChatVisible(true);
    clearChatResult();
    await loadStudentChatData();
  }

  async function handleLoginSubmit(event) {
    event.preventDefault();

    const account = accountInput.value.trim();
    const password = passwordInput.value;
    if (!account || !password) {
      setMessage('请输入账号和密码。', 'error');
      return;
    }

    setLoading(true);
    setMessage('正在验证身份...', '');

    try {
      const tokenData = await login(account, password);
      state.token = tokenData.access_token;
      localStorage.setItem('access_token', state.token);

      const me = await fetchMe(state.token);
      setUserView(me, state.token);
      setRole(me.role);

      if (me.role === 'student') {
        await initStudentChat();
      } else {
        clearChatWorkspace();
      }

      setMessage(`登录成功，当前角色：${me.role}`, 'success');
    } catch (error) {
      clearUserView();
      clearChatWorkspace();
      localStorage.removeItem('access_token');
      setMessage(error.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  function handleLogout() {
    state.token = '';
    localStorage.removeItem('access_token');
    clearUserView();
    clearChatWorkspace();
    setMessage('已退出登录。', '');
    setRole('student');
  }

  async function handleChatSubmit() {
    const prompt = promptInput.value.trim();
    const selectedModel = modelSelect.value;

    if (!prompt) {
      setChatMessage('请输入提示词。', 'error');
      return;
    }

    if (!selectedModel) {
      setChatMessage('请先选择模型。', 'error');
      return;
    }

    setChatLoading(true);
    setChatMessage('模型生成中...', '');

    try {
      const result = await requestWithToken('/api/chat/completions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ model: selectedModel, prompt }),
      });

      contentBox.value = result.content;
      metaModel.textContent = result.model_name;
      metaTime.textContent = formatTime(result.generated_at);
      renderCitations(result.citations);
      setChatMessage('生成完成，元数据已记录。', 'success');

      const history = await requestWithToken('/api/chat/history?limit=10');
      renderHistory(history);
    } catch (error) {
      setChatMessage(error.message, 'error');
    } finally {
      setChatLoading(false);
    }
  }

  async function handleRefreshHistory() {
    try {
      const history = await requestWithToken('/api/chat/history?limit=10');
      renderHistory(history);
      setChatMessage('历史记录已刷新。', 'success');
    } catch (error) {
      setChatMessage(error.message, 'error');
    }
  }

  async function tryRestoreSession() {
    if (!state.token) {
      setRole('student');
      clearChatWorkspace();
      return;
    }

    try {
      const me = await fetchMe(state.token);
      setRole(me.role);
      setUserView(me, state.token);

      if (me.role === 'student') {
        await initStudentChat();
      } else {
        clearChatWorkspace();
      }

      setMessage(`欢迎回来，${me.name}`, 'success');
    } catch (error) {
      localStorage.removeItem('access_token');
      state.token = '';
      clearChatWorkspace();
      setRole('student');
      setMessage(error.message, 'error');
    }
  }

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => setRole(tab.dataset.role));
  });

  form.addEventListener('submit', handleLoginSubmit);
  logoutBtn.addEventListener('click', handleLogout);
  chatSubmitBtn.addEventListener('click', handleChatSubmit);
  refreshHistoryBtn.addEventListener('click', handleRefreshHistory);

  tryRestoreSession();
})();

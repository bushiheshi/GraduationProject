<script setup>
import { computed, onMounted, ref } from 'vue';

const token = ref(localStorage.getItem('access_token') || '');
const user = ref(null);
const assignments = ref([]);
const selectedAssignmentId = ref(null);
const submissions = ref([]);
const keywordSummary = ref([]);
const selectedStudentId = ref(null);
const selectedSubmissionDetail = ref(null);
const selectedKeywordDetail = ref(null);
const loadingAssignments = ref(false);
const loadingSubmissions = ref(false);
const loadingSubmissionDetail = ref(false);
const loadingKeywordSummary = ref(false);
const loadingKeywordDetail = ref(false);
const publishing = ref(false);
const showPublishModal = ref(false);
const showFilePreviewModal = ref(false);
const showKeywordDetailModal = ref(false);
const message = ref('');
const messageType = ref('');
const form = ref({
  title: '',
  description: '',
});

const selectedAssignment = computed(() => {
  return assignments.value.find((item) => item.id === selectedAssignmentId.value) || null;
});

const selectedSubmissionSummary = computed(() => {
  return submissions.value.find((item) => item.student_id === selectedStudentId.value) || null;
});

const selectedAiUsage = computed(() => {
  return selectedSubmissionDetail.value?.ai_usage || null;
});

const totalAssignments = computed(() => assignments.value.length);
const totalDistributedCount = computed(() => assignments.value.reduce((sum, item) => sum + item.student_count, 0));
const totalSubmissions = computed(() => assignments.value.reduce((sum, item) => sum + item.submitted_count, 0));
const selectedStudentCount = computed(() => selectedAssignment.value?.student_count || 0);
const selectedSubmittedCount = computed(() => selectedAssignment.value?.submitted_count || 0);
const selectedPendingCount = computed(() => {
  if (!selectedAssignment.value) {
    return 0;
  }
  return Math.max(selectedAssignment.value.student_count - selectedAssignment.value.submitted_count, 0);
});
const selectedCompletionRate = computed(() => {
  if (!selectedAssignment.value?.student_count) {
    return 0;
  }
  return Math.round((selectedAssignment.value.submitted_count / selectedAssignment.value.student_count) * 100);
});
const selectedWithFileCount = computed(() => submissions.value.filter((item) => item.source_filename).length);
const selectedAnsweredCount = computed(() => submissions.value.filter((item) => item.has_submission).length);
const keywordQuestionCount = computed(() => keywordSummary.value.reduce((sum, item) => sum + item.count, 0));
const keywordStudentCoverage = computed(() => {
  const total = keywordSummary.value.reduce((sum, item) => sum + item.student_count, 0);
  return keywordSummary.value.length ? Math.round(total / keywordSummary.value.length) : 0;
});

onMounted(async () => {
  if (!token.value) {
    goLogin();
    return;
  }

  try {
    const me = await request('/api/auth/me');
    if (me.role !== 'teacher') {
      throw new Error('当前账号不是教师账号。');
    }

    user.value = me;
    await loadAssignments();
    setMessage('教师工作台已支持查看每位学生的 AI 使用分析。', 'success');
  } catch (error) {
    localStorage.removeItem('access_token');
    setMessage(error.message || '登录状态已失效。', 'error');
    window.setTimeout(goLogin, 600);
  }
});

async function request(url, options = {}) {
  const headers = {
    ...(options.headers || {}),
    Authorization: `Bearer ${token.value}`,
  };

  const response = await fetch(url, {
    ...options,
    headers,
  });
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      localStorage.removeItem('access_token');
    }
    throw new Error(data.detail || '请求失败。');
  }

  return data;
}

async function loadAssignments() {
  loadingAssignments.value = true;
  try {
    const data = await request('/api/teacher/assignments');
    assignments.value = data;

    if (!data.length) {
      selectedAssignmentId.value = null;
      submissions.value = [];
      keywordSummary.value = [];
      selectedStudentId.value = null;
      selectedSubmissionDetail.value = null;
      selectedKeywordDetail.value = null;
      return;
    }

    const nextAssignmentId = data.some((item) => item.id === selectedAssignmentId.value)
      ? selectedAssignmentId.value
      : data[0].id;
    await selectAssignment(nextAssignmentId);
  } finally {
    loadingAssignments.value = false;
  }
}

async function selectAssignment(assignmentId) {
  if (!assignments.value.some((item) => item.id === assignmentId)) {
    return;
  }

  selectedAssignmentId.value = assignmentId;
  keywordSummary.value = [];
  selectedKeywordDetail.value = null;
  showKeywordDetailModal.value = false;
  await Promise.all([
    loadSubmissions(assignmentId),
    loadKeywordSummary(assignmentId),
  ]);
}

async function loadSubmissions(assignmentId) {
  if (!assignmentId) {
    submissions.value = [];
    selectedStudentId.value = null;
    selectedSubmissionDetail.value = null;
    return;
  }

  loadingSubmissions.value = true;
  selectedSubmissionDetail.value = null;
  try {
    const data = await request(`/api/teacher/assignments/${assignmentId}/submissions`);
    submissions.value = data;

    if (!data.length) {
      selectedStudentId.value = null;
      selectedSubmissionDetail.value = null;
      return;
    }

    const nextStudentId = data.some((item) => item.student_id === selectedStudentId.value)
      ? selectedStudentId.value
      : (data.find((item) => item.has_submission)?.student_id || data[0].student_id);

    await selectSubmission(nextStudentId, { silent: true });
  } catch (error) {
    submissions.value = [];
    selectedStudentId.value = null;
    selectedSubmissionDetail.value = null;
    setMessage(error.message || '加载提交列表失败。', 'error');
  } finally {
    loadingSubmissions.value = false;
  }
}

async function loadKeywordSummary(assignmentId) {
  if (!assignmentId) {
    keywordSummary.value = [];
    return;
  }

  loadingKeywordSummary.value = true;
  try {
    const data = await request(`/api/teacher/assignments/${assignmentId}/question-keywords`);

    if (selectedAssignmentId.value !== assignmentId) {
      return;
    }

    keywordSummary.value = data;
  } catch (error) {
    keywordSummary.value = [];
    setMessage(error.message || '加载关键词统计失败。', 'error');
  } finally {
    loadingKeywordSummary.value = false;
  }
}

async function selectSubmission(studentId, options = {}) {
  if (!selectedAssignmentId.value || !studentId) {
    selectedStudentId.value = null;
    selectedSubmissionDetail.value = null;
    return;
  }

  selectedStudentId.value = studentId;
  await loadSubmissionDetail(selectedAssignmentId.value, studentId, options);
}

async function loadSubmissionDetail(assignmentId, studentId, options = {}) {
  loadingSubmissionDetail.value = true;
  try {
    const detail = await request(`/api/teacher/assignments/${assignmentId}/submissions/${studentId}`);

    if (selectedAssignmentId.value !== assignmentId || selectedStudentId.value !== studentId) {
      return;
    }

    selectedSubmissionDetail.value = detail;
    if (!options.silent) {
      setMessage(`正在查看 ${detail.student_name} 的提交与 AI 使用情况。`, 'success');
    }
  } catch (error) {
    selectedSubmissionDetail.value = null;
    setMessage(error.message || '加载提交详情失败。', 'error');
  } finally {
    loadingSubmissionDetail.value = false;
  }
}

function openPublishModal() {
  showPublishModal.value = true;
}

function closePublishModal() {
  if (publishing.value) {
    return;
  }
  showPublishModal.value = false;
}

async function publishAssignment() {
  const title = form.value.title.trim();
  const description = form.value.description.trim();

  if (!title) {
    setMessage('请先填写作业标题。', 'error');
    return;
  }

  publishing.value = true;
  setMessage('正在发布作业...', '');

  try {
    const created = await request('/api/teacher/assignments', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        title,
        description: description || null,
      }),
    });

    form.value.title = '';
    form.value.description = '';
    showPublishModal.value = false;
    await loadAssignments();
    selectedAssignmentId.value = created.id;
    await loadSubmissions(created.id);
    setMessage(`作业已发布，已为 ${created.student_count} 名学生创建提交入口。`, 'success');
  } catch (error) {
    setMessage(error.message || '发布作业失败。', 'error');
  } finally {
    publishing.value = false;
  }
}

async function openKeywordDetail(keyword) {
  if (!selectedAssignmentId.value || !keyword) {
    return;
  }

  const assignmentId = selectedAssignmentId.value;
  showKeywordDetailModal.value = true;
  loadingKeywordDetail.value = true;
  selectedKeywordDetail.value = null;

  try {
    const detail = await request(
      `/api/teacher/assignments/${assignmentId}/question-keywords/detail?keyword=${encodeURIComponent(keyword)}`,
    );

    if (!showKeywordDetailModal.value || selectedAssignmentId.value !== assignmentId) {
      return;
    }

    selectedKeywordDetail.value = detail;
  } catch (error) {
    selectedKeywordDetail.value = null;
    setMessage(error.message || '加载关键词明细失败。', 'error');
  } finally {
    loadingKeywordDetail.value = false;
  }
}

function closeKeywordDetail() {
  showKeywordDetailModal.value = false;
  loadingKeywordDetail.value = false;
  selectedKeywordDetail.value = null;
}

function openFilePreview() {
  if (!selectedSubmissionDetail.value?.source_filename || !selectedSubmissionDetail.value?.answer_text) {
    return;
  }
  showFilePreviewModal.value = true;
}

function closeFilePreview() {
  showFilePreviewModal.value = false;
}

function downloadSourceFile() {
  const detail = selectedSubmissionDetail.value;
  if (!detail?.source_filename || !detail.answer_text) {
    return;
  }

  const blob = new Blob([detail.answer_text], { type: 'text/plain;charset=utf-8' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = detail.source_filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

function summarizeModels(models) {
  return models?.length ? models.join('、') : '暂无模型记录';
}

function setMessage(text, type) {
  message.value = text;
  messageType.value = type;
}

function formatTime(value) {
  if (!value) {
    return '-';
  }
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

function logout() {
  localStorage.removeItem('access_token');
  goLogin();
}

function goLogin() {
  window.location.href = '/frontend/login.html';
}
</script>

<template>
  <div class="teacher-shell">
    <aside class="teacher-sidebar panel">
      <div class="brand-block">
        <div class="brand-mark">T</div>
        <div class="brand-copy">
          <strong>教师作业台</strong>
          <span>统计与 AI 使用分析</span>
        </div>
      </div>

      <section class="identity-card">
        <div class="identity-top">
          <p class="eyebrow">当前教师</p>
          <span class="identity-badge">在线</span>
        </div>
        <h2>{{ user ? user.name : '正在校验身份...' }}</h2>
        <p class="identity-account">{{ user ? user.account : '...' }}</p>
      </section>

      <section class="sidebar-stats">
        <article>
          <span>已发布作业</span>
          <strong>{{ totalAssignments }}</strong>
        </article>
        <article>
          <span>累计提交</span>
          <strong>{{ totalSubmissions }}</strong>
        </article>
        <article>
          <span>累计下发</span>
          <strong>{{ totalDistributedCount }}</strong>
        </article>
      </section>

      <div class="sidebar-actions">
        <button class="primary-button" type="button" @click="openPublishModal">发布作业</button>
        <button class="ghost-button" type="button" @click="logout">退出登录</button>
      </div>
    </aside>

    <main class="teacher-main">
      <section class="panel spotlight-card">
        <div class="spotlight-copy">
          <p class="eyebrow">统计概览</p>
          <h1>{{ selectedAssignment ? selectedAssignment.title : '请先选择或发布一份作业' }}</h1>
          <p class="spotlight-description">
            {{ selectedAssignment?.description || '教师页现在可以查看每位学生的提交内容、AI 使用次数、模型分布、时间线和学习过程总结。' }}
          </p>
          <div class="toolbar-message-wrap">
            <p :class="['toolbar-message', messageType]">{{ message }}</p>
          </div>
        </div>

        <div class="spotlight-progress">
          <span>当前作业提交率</span>
          <strong>{{ selectedCompletionRate }}%</strong>
          <div class="progress-track">
            <div class="progress-bar" :style="{ width: `${selectedCompletionRate}%` }"></div>
          </div>
          <div class="progress-meta">
            <span>已提交 {{ selectedSubmittedCount }}</span>
            <span>未提交 {{ selectedPendingCount }}</span>
          </div>
        </div>
      </section>

      <section class="summary-grid">
        <article class="panel summary-card accent-card">
          <span>当前作业学生数</span>
          <strong>{{ selectedStudentCount }}</strong>
          <small>按当前选中作业统计</small>
        </article>
        <article class="panel summary-card mint-card">
          <span>当前已提交</span>
          <strong>{{ selectedSubmittedCount }}</strong>
          <small>点击学生查看详细分析</small>
        </article>
        <article class="panel summary-card sky-card">
          <span>TXT 提交数</span>
          <strong>{{ selectedWithFileCount }}</strong>
          <small>支持预览和下载</small>
        </article>
        <article class="panel summary-card slate-card">
          <span>提交列表条数</span>
          <strong>{{ selectedAnsweredCount }}</strong>
          <small>当前作业可见的提交记录</small>
        </article>
      </section>

      <section class="panel keyword-board">
        <div class="section-head">
          <div>
            <p class="eyebrow">问题关键词</p>
            <h2>{{ selectedAssignment ? '本次作业里学生最常问的问题' : '请先选择一份作业' }}</h2>
          </div>
          <span v-if="selectedAssignment" class="head-tag">
            {{ loadingKeywordSummary ? '统计中' : `${keywordSummary.length} 个高频词` }}
          </span>
        </div>

        <div v-if="!selectedAssignment" class="empty-state compact-empty">
          <strong>先选择作业</strong>
          <p>选中作业后，这里会统计学生提问里出现频率最高的关键词，并支持点开查看原始问答。</p>
        </div>

        <div v-else-if="loadingKeywordSummary" class="empty-state compact-empty">
          <strong>正在统计关键词</strong>
          <p>系统正在分析当前作业下全部学生提问的高频词。</p>
        </div>

        <div v-else-if="!keywordSummary.length" class="empty-state compact-empty">
          <strong>还没有可统计的问题</strong>
          <p>当前作业还没有足够的提问记录，学生开始对话后这里会自动出现关键词汇总。</p>
        </div>

        <div v-else class="keyword-board-body">
          <div class="keyword-overview-grid">
            <article class="keyword-overview-card">
              <span>关键词总数</span>
              <strong>{{ keywordSummary.length }}</strong>
              <small>当前展示的高频问题标签</small>
            </article>
            <article class="keyword-overview-card">
              <span>累计命中次数</span>
              <strong>{{ keywordQuestionCount }}</strong>
              <small>按提问轮次去重统计</small>
            </article>
            <article class="keyword-overview-card">
              <span>平均涉及学生</span>
              <strong>{{ keywordStudentCoverage }}</strong>
              <small>每个关键词平均覆盖的学生人数</small>
            </article>
          </div>

          <div class="keyword-chip-grid">
            <button
              v-for="item in keywordSummary"
              :key="item.keyword"
              type="button"
              class="keyword-chip-card"
              @click="openKeywordDetail(item.keyword)"
            >
              <div class="keyword-chip-head">
                <strong>{{ item.keyword }}</strong>
                <span>{{ item.count }} 次</span>
              </div>
              <p>{{ item.student_count }} 名学生提到过</p>
              <small v-if="item.sample_prompts.length">
                {{ item.sample_prompts.join(' · ') }}
              </small>
              <small v-else>点击查看命中的原始提问与回答</small>
            </button>
          </div>
        </div>
      </section>

      <section class="workspace-grid">
        <article class="panel assignment-card">
          <div class="section-head">
            <div>
              <p class="eyebrow">作业列表</p>
              <h2>按作业查看统计</h2>
            </div>
            <span class="head-tag">{{ loadingAssignments ? '刷新中' : `${assignments.length} 份作业` }}</span>
          </div>

          <div v-if="!assignments.length" class="empty-state compact-empty">
            <strong>还没有作业</strong>
            <p>发布作业后，这里将开始展示提交情况和 AI 使用分析。</p>
            <button class="primary-button" type="button" @click="openPublishModal">立即发布</button>
          </div>

          <div v-else class="assignment-list">
            <button
              v-for="item in assignments"
              :key="item.id"
              type="button"
              :class="['assignment-item', { active: item.id === selectedAssignmentId }]"
              @click="selectAssignment(item.id)"
            >
              <div class="assignment-item-top">
                <strong>{{ item.title }}</strong>
                <span>{{ item.submitted_count }}/{{ item.student_count }}</span>
              </div>
              <p v-if="item.description">{{ item.description }}</p>
              <div class="assignment-meta">
                <span>发布时间 {{ formatTime(item.created_at) }}</span>
                <span class="assignment-meta-pill">提交率 {{ item.student_count ? Math.round((item.submitted_count / item.student_count) * 100) : 0 }}%</span>
              </div>
            </button>
          </div>
        </article>

        <article class="panel submission-card">
          <div class="section-head">
            <div>
              <p class="eyebrow">学生提交</p>
              <h2>{{ selectedAssignment ? '点击学生查看提交与 AI 使用情况' : '请先选择一份作业' }}</h2>
            </div>
            <span v-if="selectedAssignment" class="head-tag">{{ selectedSubmittedCount }}/{{ selectedStudentCount }} 已提交</span>
          </div>

          <div v-if="!selectedAssignment" class="empty-state">
            <strong>尚未选择作业</strong>
            <p>先在左侧选择作业，这里会显示学生提交列表和 AI 使用简况。</p>
          </div>

          <div v-else-if="loadingSubmissions" class="empty-state">
            <strong>正在加载提交列表</strong>
            <p>系统正在读取当前作业的学生提交记录。</p>
          </div>

          <div v-else-if="!submissions.length" class="empty-state">
            <strong>暂无学生记录</strong>
            <p>当前作业暂时没有可供展示的学生提交信息。</p>
          </div>

          <div v-else class="submission-list">
            <button
              v-for="item in submissions"
              :key="item.student_id"
              type="button"
              :class="['submission-item', item.has_submission ? 'is-submitted' : 'is-pending', { active: item.student_id === selectedStudentId }]"
              @click="selectSubmission(item.student_id)"
            >
              <div class="submission-header">
                <div class="submission-copy">
                  <strong>{{ item.student_name }}</strong>
                  <span>{{ item.student_account }}</span>
                </div>
                <span class="status-pill">{{ item.has_submission ? '已提交' : '未提交' }}</span>
              </div>

              <p v-if="item.answer_preview" class="submission-preview">{{ item.answer_preview }}</p>
              <p v-else class="submission-preview is-empty">暂无答案内容</p>

              <p class="submission-ai-brief" :class="{ 'is-empty': !item.ai_usage_count }">
                {{ item.ai_usage_count ? `AI 使用 ${item.ai_usage_count} 次 · ${summarizeModels(item.ai_models_used)}` : '本次作业对话暂无 AI 使用记录' }}
              </p>

              <div class="submission-meta-row">
                <small>对话 ID {{ item.conversation_id }}</small>
                <small v-if="item.submitted_at">提交于 {{ formatTime(item.submitted_at) }}</small>
                <small v-if="item.ai_last_used_at">最近使用 AI {{ formatTime(item.ai_last_used_at) }}</small>
                <small v-if="item.source_filename" class="file-chip">{{ item.source_filename }}</small>
              </div>
            </button>
          </div>
        </article>

        <article class="panel detail-card">
          <div class="section-head">
            <div>
              <p class="eyebrow">提交详情</p>
              <h2>{{ selectedSubmissionSummary ? selectedSubmissionSummary.student_name : '请选择一个学生' }}</h2>
            </div>
            <span v-if="selectedSubmissionSummary" class="head-tag">{{ selectedSubmissionSummary.has_submission ? '可查看全文' : '暂无提交' }}</span>
          </div>

          <div v-if="!selectedAssignment" class="empty-state detail-empty">
            <strong>这里展示学生提交全文与 AI 分析</strong>
            <p>先选择作业，再点击学生，即可查看完整答案、TXT 文件和 AI 使用历史。</p>
          </div>

          <div v-else-if="loadingSubmissionDetail" class="empty-state detail-empty">
            <strong>正在加载学生详情</strong>
            <p>系统正在读取提交正文和 AI 使用总结。</p>
          </div>

          <div v-else-if="!selectedSubmissionDetail" class="empty-state detail-empty">
            <strong>还没有选中学生</strong>
            <p>点击中间列表中的任意学生，即可查看详细内容。</p>
          </div>

          <div v-else class="detail-body">
            <div class="detail-meta">
              <div>
                <span>学生账号</span>
                <strong>{{ selectedSubmissionDetail.student_account }}</strong>
              </div>
              <div>
                <span>提交时间</span>
                <strong>{{ formatTime(selectedSubmissionDetail.submitted_at) }}</strong>
              </div>
            </div>

            <section class="usage-panel">
              <div class="answer-head">
                <span>AI 使用情况</span>
                <small>{{ selectedAiUsage?.total_count ? `AI 调用总次数：${selectedAiUsage.total_count}` : '本次作业对话暂无 AI 使用记录' }}</small>
              </div>

              <div v-if="selectedAiUsage?.total_count" class="usage-block">
                <div class="usage-stat-grid">
                  <article class="usage-stat-card">
                    <span>总使用次数</span>
                    <strong>{{ selectedAiUsage.total_count }}</strong>
                    <small>提交前 {{ selectedAiUsage.pre_submission_count }} 次 · 提交后 {{ selectedAiUsage.post_submission_count }} 次</small>
                  </article>
                  <article class="usage-stat-card">
                    <span>使用模型</span>
                    <strong>{{ summarizeModels(selectedAiUsage.models_used) }}</strong>
                    <small v-if="selectedAiUsage.model_stats.length">{{ selectedAiUsage.model_stats.map((item) => `${item.model_name} ? ${item.count}`).join(' ? ') }}</small>
                    <small v-else>暂无模型明细</small>
                  </article>
                  <article class="usage-stat-card">
                    <span>首次使用</span>
                    <strong>{{ formatTime(selectedAiUsage.first_used_at) }}</strong>
                    <small>最近一次 {{ formatTime(selectedAiUsage.last_used_at) }}</small>
                  </article>
                </div>

                <div v-if="selectedAiUsage.behavior_tags.length" class="usage-tags">
                  <span v-for="tag in selectedAiUsage.behavior_tags" :key="tag" class="usage-tag">{{ tag }}</span>
                </div>

                <div class="usage-summary-panel">
                  <span class="file-panel-label">学习过程总结</span>
                  <p class="usage-summary-text">{{ selectedAiUsage.learning_summary }}</p>
                </div>

                <div v-if="selectedAiUsage.stage_stats.length" class="usage-stage-grid">
                  <article v-for="item in selectedAiUsage.stage_stats" :key="item.key" class="usage-stage-card">
                    <strong>{{ item.count }}</strong>
                    <span>{{ item.label }}</span>
                  </article>
                </div>

                <div class="usage-timeline">
                  <div class="answer-head">
                    <span>AI 使用时间线</span>
                    <small>按生成时间顺序展示本次作业的每次 AI 调用</small>
                  </div>

                  <div class="usage-timeline-list">
                    <article v-for="entry in selectedAiUsage.timeline" :key="entry.record_id" class="usage-timeline-item">
                      <div class="usage-timeline-head">
                        <strong>{{ formatTime(entry.generated_at) }}</strong>
                        <div class="usage-timeline-meta">
                          <span class="usage-stage-chip">{{ entry.stage_label }}</span>
                          <span class="file-chip usage-model-chip">{{ entry.model_name }}</span>
                        </div>
                      </div>
                      <p>{{ entry.prompt_preview }}</p>
                    </article>
                  </div>
                </div>
              </div>

              <div v-else class="usage-empty">
                <strong>暂无 AI 记录</strong>
                <p>该学生在这次作业对应的对话中还没有产生 AI 记录。</p>
              </div>
            </section>

            <div v-if="selectedSubmissionDetail.source_filename" class="file-panel">
              <div>
                <span class="file-panel-label">TXT 文件</span>
                <strong>{{ selectedSubmissionDetail.source_filename }}</strong>
              </div>
              <div class="file-actions">
                <button class="ghost-button" type="button" @click="openFilePreview">预览 TXT</button>
                <button class="primary-button" type="button" @click="downloadSourceFile">下载 TXT</button>
              </div>
            </div>

            <div v-if="selectedSubmissionDetail.has_submission && selectedSubmissionDetail.answer_text" class="answer-panel">
              <div class="answer-head">
                <span>提交答案</span>
                <small>学生最终提交的全文内容</small>
              </div>
              <pre class="answer-content">{{ selectedSubmissionDetail.answer_text }}</pre>
            </div>

            <div v-else class="empty-state detail-empty">
              <strong>该学生尚未提交</strong>
              <p>当前还没有答案或 TXT 文件，但上方的 AI 使用记录仍可以查看。</p>
            </div>
          </div>
        </article>
      </section>
    </main>

    <div v-if="showPublishModal" class="modal-overlay" @click.self="closePublishModal">
      <div class="modal-card panel publish-modal">
        <div class="section-head modal-head">
          <div>
            <p class="eyebrow">发布作业</p>
            <h2>新建一份作业</h2>
          </div>
          <button class="icon-button" type="button" @click="closePublishModal">×</button>
        </div>

        <label class="field">
          <span>作业标题</span>
          <input v-model="form.title" type="text" maxlength="120" placeholder="例如：数据结构实验一" />
        </label>

        <label class="field">
          <span>作业说明</span>
          <textarea v-model="form.description" rows="6" maxlength="4000" placeholder="填写作业要求、评分说明或提交约束。"></textarea>
        </label>

        <div class="modal-actions">
          <button class="ghost-button" type="button" @click="closePublishModal">取消</button>
          <button class="primary-button" type="button" :disabled="publishing" @click="publishAssignment">{{ publishing ? '发布中...' : '确认发布' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showKeywordDetailModal" class="modal-overlay" @click.self="closeKeywordDetail">
      <div class="modal-card panel keyword-modal">
        <div class="section-head modal-head">
          <div>
            <p class="eyebrow">关键词明细</p>
            <h2>{{ selectedKeywordDetail?.keyword || '正在加载关键词...' }}</h2>
          </div>
          <button class="icon-button" type="button" @click="closeKeywordDetail">×</button>
        </div>

        <div v-if="loadingKeywordDetail" class="empty-state detail-empty">
          <strong>正在加载关键词明细</strong>
          <p>系统正在整理命中该关键词的学生原始提问和 AI 回答。</p>
        </div>

        <div v-else-if="!selectedKeywordDetail?.matches?.length" class="empty-state detail-empty">
          <strong>没有匹配记录</strong>
          <p>当前关键词下暂时没有可展示的原始问答。</p>
        </div>

        <div v-else class="keyword-detail-body">
          <div class="keyword-detail-stats">
            <article class="keyword-detail-stat">
              <span>关键词</span>
              <strong>{{ selectedKeywordDetail.keyword }}</strong>
            </article>
            <article class="keyword-detail-stat">
              <span>命中次数</span>
              <strong>{{ selectedKeywordDetail.count }}</strong>
            </article>
            <article class="keyword-detail-stat">
              <span>涉及学生</span>
              <strong>{{ selectedKeywordDetail.student_count }}</strong>
            </article>
          </div>

          <div class="keyword-match-list">
            <article
              v-for="match in selectedKeywordDetail.matches"
              :key="match.record_id"
              class="keyword-match-card"
            >
              <div class="keyword-match-head">
                <div>
                  <strong>{{ match.student_name }}</strong>
                  <span>{{ match.student_account }} · 对话 {{ match.conversation_id }}</span>
                </div>
                <span class="file-chip">{{ formatTime(match.generated_at) }}</span>
              </div>

              <div class="keyword-match-section">
                <span>学生原始提问</span>
                <pre class="keyword-match-content">{{ match.prompt }}</pre>
              </div>

              <div class="keyword-match-section">
                <span>AI 回答</span>
                <pre class="keyword-match-content">{{ match.content }}</pre>
              </div>

              <div v-if="match.submission_answer_preview" class="keyword-match-section is-compact">
                <span>学生最终提交摘要</span>
                <p>{{ match.submission_answer_preview }}</p>
              </div>
            </article>
          </div>
        </div>

        <div class="modal-actions">
          <button class="ghost-button" type="button" @click="closeKeywordDetail">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showFilePreviewModal" class="modal-overlay" @click.self="closeFilePreview">
      <div class="modal-card panel preview-modal">
        <div class="section-head modal-head">
          <div>
            <p class="eyebrow">TXT 预览</p>
            <h2>{{ selectedSubmissionDetail?.source_filename || '文件内容' }}</h2>
          </div>
          <button class="icon-button" type="button" @click="closeFilePreview">×</button>
        </div>

        <pre class="answer-content preview-content">{{ selectedSubmissionDetail?.answer_text || '' }}</pre>

        <div class="modal-actions">
          <button class="ghost-button" type="button" @click="closeFilePreview">关闭</button>
          <button class="primary-button" type="button" @click="downloadSourceFile">下载 TXT</button>
        </div>
      </div>
    </div>
  </div>
</template>

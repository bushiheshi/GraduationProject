<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';

const token = ref(localStorage.getItem('access_token') || '');
const user = ref(null);
const assignments = ref([]);
const selectedAssignmentId = ref(null);
const submissions = ref([]);
const keywordSummary = ref([]);
const assessmentSummary = ref(null);
const questionOverview = ref(null);
const isQuestionOverviewExpanded = ref(false);
const selectedStudentId = ref(null);
const selectedSubmissionDetail = ref(null);
const selectedKeywordDetail = ref(null);
const assignmentSearch = ref('');
const assignmentFilter = ref('recent');
const submissionFilter = ref('all');
const loadingAssignments = ref(false);
const loadingSubmissions = ref(false);
const loadingSubmissionDetail = ref(false);
const loadingKeywordSummary = ref(false);
const loadingAssessmentSummary = ref(false);
const loadingQuestionOverview = ref(false);
const loadingKeywordDetail = ref(false);
const publishing = ref(false);
const assignmentPickerOpen = ref(false);
const activeDrawer = ref(null);
const collapsedSections = reactive({
  assessment: true,
  overview: true,
  keywords: true,
});
const loadedSections = reactive({
  assessment: false,
  overview: false,
  keywords: false,
});
const showPublishModal = ref(false);
const showFilePreviewModal = ref(false);
const showKeywordDetailModal = ref(false);
const message = ref('');
const messageType = ref('');
const form = ref({
  title: '',
  description: '',
});
let refreshTimer = null;
let refreshingDashboard = false;
const TEACHER_REFRESH_INTERVAL_MS = 30 * 60 * 1000;
const OVERVIEW_COLLAPSED_LIMIT = 5;

const selectedAssignment = computed(() => {
  return assignments.value.find((item) => item.id === selectedAssignmentId.value) || null;
});

const selectedSubmissionSummary = computed(() => {
  return submissions.value.find((item) => item.student_id === selectedStudentId.value) || null;
});

const selectedAiUsage = computed(() => {
  return selectedSubmissionDetail.value?.ai_usage || null;
});

const filteredAssignments = computed(() => {
  const query = assignmentSearch.value.trim().toLowerCase();
  let list = [...assignments.value];

  if (query) {
    list = list.filter((item) => {
      return `${item.title || ''} ${item.description || ''}`.toLowerCase().includes(query);
    });
  }

  if (assignmentFilter.value === 'current') {
    return selectedAssignment.value ? list.filter((item) => item.id === selectedAssignment.value.id) : [];
  }

  if (assignmentFilter.value === 'low') {
    return list.sort((left, right) => getAssignmentRate(left) - getAssignmentRate(right));
  }

  return list.sort((left, right) => new Date(right.created_at || 0) - new Date(left.created_at || 0));
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
const selectedAverageScore = computed(() => {
  return assessmentSummary.value?.average_score ?? '-';
});
const selectedPassRate = computed(() => {
  return assessmentSummary.value ? `${assessmentSummary.value.pass_rate}%` : '-';
});
const keywordQuestionCount = computed(() => keywordSummary.value.reduce((sum, item) => sum + item.count, 0));
const topKeywordLabels = computed(() => keywordSummary.value.slice(0, 3).map((item) => item.keyword));
const keywordStudentCoverage = computed(() => {
  const total = keywordSummary.value.reduce((sum, item) => sum + item.student_count, 0);
  return keywordSummary.value.length ? Math.round(total / keywordSummary.value.length) : 0;
});
const overviewKeywords = computed(() => questionOverview.value?.keywords || []);
const overviewStudents = computed(() => questionOverview.value?.students || []);
const visibleOverviewKeywords = computed(() => {
  if (isQuestionOverviewExpanded.value) {
    return overviewKeywords.value;
  }
  return overviewKeywords.value.slice(0, OVERVIEW_COLLAPSED_LIMIT);
});
const visibleOverviewStudents = computed(() => {
  if (isQuestionOverviewExpanded.value) {
    return overviewStudents.value;
  }
  return overviewStudents.value.slice(0, OVERVIEW_COLLAPSED_LIMIT);
});
const canToggleQuestionOverview = computed(() => {
  return (
    overviewKeywords.value.length > OVERVIEW_COLLAPSED_LIMIT
    || overviewStudents.value.length > OVERVIEW_COLLAPSED_LIMIT
  );
});
const overviewQuestionCount = computed(() => questionOverview.value?.total_question_count || 0);
const overviewStudentCount = computed(() => questionOverview.value?.student_count || 0);
const overviewKeywordCount = computed(() => questionOverview.value?.keyword_count || 0);
const overviewKeywordHits = computed(() => questionOverview.value?.total_keyword_hits || 0);
const pendingSubmissionCount = computed(() => submissions.value.filter((item) => !item.has_submission).length);
const noAiSubmissionCount = computed(() => submissions.value.filter((item) => !item.ai_usage_count).length);
const heavyAiSubmissionCount = computed(() => submissions.value.filter((item) => item.ai_usage_count >= 8).length);
const attentionSubmissionCount = computed(() => {
  return submissions.value.filter((item) => !item.has_submission || !item.ai_usage_count || item.ai_usage_count >= 8).length;
});
const filteredSubmissions = computed(() => {
  const filters = {
    all: () => true,
    pending: (item) => !item.has_submission,
    submitted: (item) => item.has_submission,
    file: (item) => Boolean(item.source_filename),
    noAi: (item) => !item.ai_usage_count,
    attention: (item) => !item.has_submission || !item.ai_usage_count || item.ai_usage_count >= 8,
  };
  const predicate = filters[submissionFilter.value] || filters.all;
  return submissions.value.filter(predicate);
});
const assessmentCompactSummary = computed(() => {
  if (!selectedAssignment.value) {
    return ['待选择作业'];
  }
  if (loadingAssessmentSummary.value) {
    return ['统计中'];
  }
  if (!loadedSections.assessment) {
    return ['查看详情后加载评估'];
  }
  if (!assessmentSummary.value?.assessed_count) {
    return ['暂无报告'];
  }
  return [
    `平均 ${selectedAverageScore.value}`,
    `达标 ${selectedPassRate.value}`,
    `关注 ${assessmentSummary.value.at_risk_count}`,
  ];
});
const overviewCompactSummary = computed(() => {
  if (loadingQuestionOverview.value) {
    return ['统计中'];
  }
  if (!loadedSections.overview) {
    return ['查看详情后加载总体问题'];
  }
  if (!overviewQuestionCount.value) {
    return ['暂无提问'];
  }
  return [
    `${overviewQuestionCount.value} 次提问`,
    `${overviewStudentCount.value} 名学生`,
    `${overviewKeywordCount.value} 个关键词`,
  ];
});
const keywordsCompactSummary = computed(() => {
  if (!selectedAssignment.value) {
    return ['待选择作业'];
  }
  if (loadingKeywordSummary.value) {
    return ['统计中'];
  }
  if (!loadedSections.keywords) {
    return ['查看详情后加载关键词'];
  }
  if (!keywordSummary.value.length) {
    return ['暂无关键词'];
  }
  return [
    `${keywordSummary.value.length} 个高频词`,
    topKeywordLabels.value.join('、'),
  ];
});
const currentMasteryLevel = computed(() => {
  if (!selectedAssignment.value) {
    return '待生成';
  }

  if (selectedCompletionRate.value >= 85) {
    return '掌握较好';
  }
  if (selectedCompletionRate.value >= 60) {
    return '基本掌握';
  }
  if (selectedCompletionRate.value >= 40) {
    return '需要巩固';
  }
  return '掌握较弱';
});
const currentMasteryGuidance = computed(() => {
  if (!selectedAssignment.value) {
    return '当前还没有选中作业。发布新作业时，建议在作业说明里写清教材页数、章节范围和知识点，这样系统后续才能更准确判断学生的知识掌握程度。';
  }

  return `基于当前作业的提交率 ${selectedCompletionRate.value}% 和学生提交情况，可将当前学生知识掌握程度暂评为“${currentMasteryLevel.value}”。建议在作业说明里补充教材页数，例如“第 3 章第 42-47 页”，这样后续统计会更准确。`;
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
    startAutoRefresh();
    setMessage('教师工作台已支持查看每位学生的 AI 使用分析。', 'success');
  } catch (error) {
    localStorage.removeItem('access_token');
    setMessage(error.message || '登录状态已失效。', 'error');
    window.setTimeout(goLogin, 600);
  }
});

onBeforeUnmount(() => {
  window.clearInterval(refreshTimer);
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
    selectedAssignmentId.value = null;
    submissions.value = [];
    keywordSummary.value = [];
    assessmentSummary.value = null;
    selectedStudentId.value = null;
    selectedSubmissionDetail.value = null;
    selectedKeywordDetail.value = null;
    showKeywordDetailModal.value = false;
    showFilePreviewModal.value = false;
  } finally {
    loadingAssignments.value = false;
  }
}

async function selectAssignment(assignmentId) {
  if (!assignments.value.some((item) => item.id === assignmentId)) {
    return;
  }

  selectedAssignmentId.value = assignmentId;
  selectedStudentId.value = null;
  selectedSubmissionDetail.value = null;
  keywordSummary.value = [];
  assessmentSummary.value = null;
  loadedSections.assessment = false;
  loadedSections.keywords = false;
  selectedKeywordDetail.value = null;
  showKeywordDetailModal.value = false;
  showFilePreviewModal.value = false;
  if (activeDrawer.value === 'submission') {
    activeDrawer.value = null;
  }
  await loadSubmissions(assignmentId);
  await Promise.all([
    !collapsedSections.assessment ? ensureSectionData('assessment') : Promise.resolve(),
    !collapsedSections.keywords ? ensureSectionData('keywords') : Promise.resolve(),
  ]);
}

function toggleAssignmentPicker() {
  assignmentPickerOpen.value = !assignmentPickerOpen.value;
}

async function selectAssignmentFromPicker(assignmentId) {
  await selectAssignment(assignmentId);
}

async function toggleCollapsedSection(sectionKey) {
  collapsedSections[sectionKey] = !collapsedSections[sectionKey];
  if (!collapsedSections[sectionKey]) {
    await ensureSectionData(sectionKey);
  }
}

async function openSectionDrawer(sectionKey) {
  if (!Object.prototype.hasOwnProperty.call(collapsedSections, sectionKey)) {
    return;
  }

  activeDrawer.value = sectionKey;
  collapsedSections[sectionKey] = false;
  await ensureSectionData(sectionKey);
}

function openSubmissionDrawer(studentId) {
  activeDrawer.value = 'submission';
  selectSubmission(studentId);
}

function closeDrawer() {
  if (activeDrawer.value && Object.prototype.hasOwnProperty.call(collapsedSections, activeDrawer.value)) {
    collapsedSections[activeDrawer.value] = true;
  }
  activeDrawer.value = null;
}

async function ensureSectionData(sectionKey) {
  if (sectionKey === 'overview' && !loadedSections.overview) {
    await loadQuestionOverview();
    return;
  }

  if (sectionKey === 'assessment' && selectedAssignmentId.value && !loadedSections.assessment) {
    await loadAssessmentSummary(selectedAssignmentId.value);
    return;
  }

  if (sectionKey === 'keywords' && selectedAssignmentId.value && !loadedSections.keywords) {
    await loadKeywordSummary(selectedAssignmentId.value);
  }
}

function getAssignmentRate(item) {
  if (!item?.student_count) {
    return 0;
  }
  return Math.round((item.submitted_count / item.student_count) * 100);
}

async function loadSubmissions(assignmentId, options = {}) {
  if (!assignmentId) {
    submissions.value = [];
    selectedStudentId.value = null;
    selectedSubmissionDetail.value = null;
    return;
  }

  loadingSubmissions.value = true;
  if (!options.preserveSelection) {
    selectedStudentId.value = null;
    selectedSubmissionDetail.value = null;
  }
  try {
    const data = await request(`/api/teacher/assignments/${assignmentId}/submissions`);
    if (selectedAssignmentId.value !== assignmentId) {
      return;
    }

    submissions.value = data;
    if (!data.length) {
      return;
    }
  } catch (error) {
    submissions.value = [];
    if (!options.preserveSelection) {
      selectedStudentId.value = null;
      selectedSubmissionDetail.value = null;
    }
    setMessage(error.message || '加载提交列表失败。', 'error');
  } finally {
    loadingSubmissions.value = false;
  }
}

async function loadKeywordSummary(assignmentId) {
  if (!assignmentId) {
    keywordSummary.value = [];
    loadedSections.keywords = false;
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
    loadedSections.keywords = true;
    loadingKeywordSummary.value = false;
  }
}

async function loadAssessmentSummary(assignmentId) {
  if (!assignmentId) {
    assessmentSummary.value = null;
    loadedSections.assessment = false;
    return;
  }

  loadingAssessmentSummary.value = true;
  try {
    const data = await request(`/api/teacher/assignments/${assignmentId}/assessment-summary`);
    if (selectedAssignmentId.value !== assignmentId) {
      return;
    }
    assessmentSummary.value = data;
  } catch (error) {
    assessmentSummary.value = null;
    setMessage(error.message || '加载学生评估统计失败。', 'error');
  } finally {
    loadedSections.assessment = true;
    loadingAssessmentSummary.value = false;
  }
}

async function loadQuestionOverview() {
  loadingQuestionOverview.value = true;
  try {
    questionOverview.value = await request('/api/teacher/question-overview');
    isQuestionOverviewExpanded.value = false;
  } catch (error) {
    questionOverview.value = null;
    isQuestionOverviewExpanded.value = false;
    setMessage(error.message || '加载总体问题统计失败。', 'error');
  } finally {
    loadedSections.overview = true;
    loadingQuestionOverview.value = false;
  }
}

function toggleQuestionOverview() {
  isQuestionOverviewExpanded.value = !isQuestionOverviewExpanded.value;
}

function startAutoRefresh() {
  window.clearInterval(refreshTimer);
  refreshTimer = window.setInterval(() => {
    refreshDashboard();
  }, TEACHER_REFRESH_INTERVAL_MS);
}

async function refreshDashboard() {
  if (refreshingDashboard || publishing.value || !token.value) {
    return;
  }

  refreshingDashboard = true;
  const currentAssignmentId = selectedAssignmentId.value;
  const currentStudentId = selectedStudentId.value;

  try {
    const [latestAssignments] = await Promise.all([
      request('/api/teacher/assignments'),
      loadedSections.overview || !collapsedSections.overview ? loadQuestionOverview() : Promise.resolve(),
    ]);

    assignments.value = latestAssignments;

    if (!currentAssignmentId) {
      return;
    }

    const assignmentStillExists = latestAssignments.some((item) => item.id === currentAssignmentId);
    if (!assignmentStillExists) {
      selectedAssignmentId.value = null;
      submissions.value = [];
      keywordSummary.value = [];
      assessmentSummary.value = null;
      selectedStudentId.value = null;
      selectedSubmissionDetail.value = null;
      return;
    }

    selectedAssignmentId.value = currentAssignmentId;
    await Promise.all([
      loadSubmissions(currentAssignmentId, { preserveSelection: true, silent: true }),
      loadedSections.keywords || !collapsedSections.keywords ? loadKeywordSummary(currentAssignmentId) : Promise.resolve(),
      loadedSections.assessment || !collapsedSections.assessment ? loadAssessmentSummary(currentAssignmentId) : Promise.resolve(),
    ]);

    if (currentStudentId) {
      selectedStudentId.value = currentStudentId;
      await loadSubmissionDetail(currentAssignmentId, currentStudentId, { silent: true });
    }
  } catch (error) {
    console.warn('Failed to refresh teacher dashboard', error);
  } finally {
    refreshingDashboard = false;
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
      setMessage(`正在查看 ${detail.student_name} 的提交、AI 使用情况与评估报告。`, 'success');
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

function insertPublishTemplate() {
  const template = [
    '教材页数：第__章第__页至第__页',
    `当前学生知识掌握程度：${currentMasteryLevel.value}`,
    '作业要求：',
  ].join('\n');

  const currentDescription = form.value.description.trim();
  form.value.description = currentDescription ? `${currentDescription}\n\n${template}` : template;
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
    await Promise.all([
      loadAssignments(),
      loadedSections.overview ? loadQuestionOverview() : Promise.resolve(),
    ]);
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
        <button
          class="sidebar-stat-card published-assignment-toggle"
          type="button"
          :aria-expanded="assignmentPickerOpen"
          aria-controls="published-assignment-picker"
          @click="toggleAssignmentPicker"
        >
          <span>已发布作业</span>
          <strong>{{ totalAssignments }}</strong>
          <small>{{ selectedAssignment ? selectedAssignment.title : '点击选择作业' }}</small>
          <i aria-hidden="true">{{ assignmentPickerOpen ? '收起' : '展开' }}</i>
        </button>

        <div
          v-if="assignmentPickerOpen"
          id="published-assignment-picker"
          class="sidebar-assignment-picker"
        >
          <div v-if="loadingAssignments" class="sidebar-assignment-empty">正在读取已发布作业...</div>
          <div v-else-if="!assignments.length" class="sidebar-assignment-empty">
            <strong>还没有作业</strong>
            <span>发布作业后可在这里选择。</span>
          </div>
          <template v-else>
            <div class="assignment-picker-tools">
              <input
                v-model.trim="assignmentSearch"
                type="search"
                placeholder="搜索作业"
                aria-label="搜索已发布作业"
              />
              <div class="assignment-filter-tabs" aria-label="作业筛选">
                <button
                  type="button"
                  :class="{ active: assignmentFilter === 'recent' }"
                  @click="assignmentFilter = 'recent'"
                >
                  最近
                </button>
                <button
                  type="button"
                  :class="{ active: assignmentFilter === 'low' }"
                  @click="assignmentFilter = 'low'"
                >
                  低提交
                </button>
                <button
                  type="button"
                  :class="{ active: assignmentFilter === 'current' }"
                  @click="assignmentFilter = 'current'"
                >
                  已选
                </button>
              </div>
            </div>

            <div v-if="!filteredAssignments.length" class="sidebar-assignment-empty">
              <strong>没有匹配作业</strong>
              <span>换个关键词或筛选条件。</span>
            </div>

            <button
              v-for="item in filteredAssignments"
              v-else
              :key="item.id"
              type="button"
              :class="['sidebar-assignment-option', { active: item.id === selectedAssignmentId }]"
              @click="selectAssignmentFromPicker(item.id)"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.submitted_count }}/{{ item.student_count }} 已提交 · 提交率 {{ getAssignmentRate(item) }}%</span>
            </button>
          </template>
        </div>

        <article class="sidebar-stat-card">
          <span>累计提交</span>
          <strong>{{ totalSubmissions }}</strong>
        </article>
        <article class="sidebar-stat-card">
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
          <div v-if="selectedAssignment" class="current-assignment-strip">
            <span>当前作业</span>
            <strong>{{ selectedSubmittedCount }}/{{ selectedStudentCount }} 已提交</strong>
            <small>{{ selectedCompletionRate }}% 完成</small>
          </div>
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

      <section :class="['panel assessment-board compact-panel', { 'is-collapsed': collapsedSections.assessment, 'is-drawer-open': activeDrawer === 'assessment' }]">
        <div class="section-head">
          <div>
            <p class="eyebrow">学生评估统计</p>
            <h2>{{ selectedAssignment ? '当前作业评估报告概览' : '请先选择一份作业' }}</h2>
          </div>
          <div class="section-head-actions">
            <span v-if="selectedAssignment" class="head-tag">
              {{ loadingAssessmentSummary ? '统计中' : `${assessmentSummary?.assessed_count || 0} 份报告` }}
            </span>
            <button
              class="collapse-button"
              type="button"
              @click="activeDrawer === 'assessment' ? closeDrawer() : openSectionDrawer('assessment')"
            >
              <span>{{ activeDrawer === 'assessment' ? '关闭' : '详情' }}</span>
              <b aria-hidden="true">{{ activeDrawer === 'assessment' ? '×' : '›' }}</b>
            </button>
          </div>
        </div>
        <div class="compact-panel-summary">
          <span v-for="item in assessmentCompactSummary" :key="item">{{ item }}</span>
        </div>

        <div v-if="!collapsedSections.assessment" class="collapsible-section-body">
          <div v-if="!selectedAssignment" class="empty-state compact-empty">
            <strong>等待选择作业</strong>
            <p>选中作业后，这里会统计学生提交评估报告的平均分、达标率和主要风险。</p>
          </div>

          <div v-else-if="loadingAssessmentSummary" class="empty-state compact-empty">
            <strong>正在生成评估统计</strong>
            <p>系统正在汇总当前作业已提交答案的评估报告。</p>
          </div>

          <div v-else-if="!assessmentSummary?.assessed_count" class="empty-state compact-empty">
            <strong>暂无可统计报告</strong>
            <p>学生提交答案后，这里会显示平均分、达标率和常见不足。</p>
          </div>

          <div v-else class="assessment-board-body">
            <div class="assessment-stat-grid">
              <article class="assessment-stat-card">
                <span>平均分</span>
                <strong>{{ selectedAverageScore }}</strong>
                <small>已评估 {{ assessmentSummary.assessed_count }}/{{ assessmentSummary.submitted_count }} 份</small>
              </article>
              <article class="assessment-stat-card">
                <span>达标率</span>
                <strong>{{ selectedPassRate }}</strong>
                <small>{{ assessmentSummary.pass_count }} 人达到 60 分以上</small>
              </article>
              <article class="assessment-stat-card">
                <span>最低分</span>
                <strong>{{ assessmentSummary.lowest_score }}</strong>
                <small>最高分 {{ assessmentSummary.highest_score }}</small>
              </article>
              <article class="assessment-stat-card">
                <span>需重点关注</span>
                <strong>{{ assessmentSummary.at_risk_count }}</strong>
                <small>低于 60 分或报告等级存疑</small>
              </article>
            </div>

            <div class="assessment-insight-grid">
              <article class="assessment-insight-card">
                <div class="assessment-card-head">
                  <strong>等级分布</strong>
                  <span>{{ Object.keys(assessmentSummary.level_counts).length }} 类</span>
                </div>
                <div class="assessment-chip-list">
                  <span
                    v-for="(count, label) in assessmentSummary.level_counts"
                    :key="label"
                    class="assessment-chip"
                  >
                    {{ label }} · {{ count }}
                  </span>
                </div>
              </article>

              <article class="assessment-insight-card">
                <div class="assessment-card-head">
                  <strong>常见风险</strong>
                  <span>{{ assessmentSummary.risk_flag_counts.length }} 项</span>
                </div>
                <div v-if="assessmentSummary.risk_flag_counts.length" class="assessment-chip-list">
                  <span
                    v-for="item in assessmentSummary.risk_flag_counts"
                    :key="item.flag"
                    class="assessment-chip"
                  >
                    {{ item.flag }} · {{ item.count }}
                  </span>
                </div>
                <p v-else>暂无明显风险标签。</p>
              </article>
            </div>

          </div>
        </div>
      </section>

      <section :class="['panel overview-board compact-panel', { 'is-collapsed': collapsedSections.overview, 'is-drawer-open': activeDrawer === 'overview' }]">
        <div class="section-head">
          <div>
            <p class="eyebrow">总体问题统计</p>
            <h2>全部作业里的学生提问</h2>
          </div>
          <div class="section-head-actions">
            <span class="head-tag">
              {{ loadingQuestionOverview ? '统计中' : `${overviewQuestionCount} 次提问` }}
            </span>
            <button
              class="collapse-button"
              type="button"
              @click="activeDrawer === 'overview' ? closeDrawer() : openSectionDrawer('overview')"
            >
              <span>{{ activeDrawer === 'overview' ? '关闭' : '详情' }}</span>
              <b aria-hidden="true">{{ activeDrawer === 'overview' ? '×' : '›' }}</b>
            </button>
          </div>
        </div>
        <div class="compact-panel-summary">
          <span v-for="item in overviewCompactSummary" :key="item">{{ item }}</span>
        </div>

        <div v-if="!collapsedSections.overview" class="collapsible-section-body">
          <div v-if="loadingQuestionOverview" class="empty-state compact-empty">
            <strong>正在整理总体问题统计</strong>
            <p>系统正在汇总全部作业下学生对话里的提问次数和关键词。</p>
          </div>

          <div v-else-if="!overviewQuestionCount" class="empty-state compact-empty">
            <strong>还没有可统计的提问</strong>
            <p>学生开始在作业对话里提问后，这里会展示整体提问次数、关键词次数和学生提问排行。</p>
          </div>

          <div v-else class="overview-board-body">
            <div class="keyword-overview-grid overview-stat-grid">
              <article class="keyword-overview-card">
                <span>总体提问次数</span>
                <strong>{{ overviewQuestionCount }}</strong>
                <small>全部作业下的学生 AI 提问轮次</small>
              </article>
              <article class="keyword-overview-card">
                <span>提问学生数</span>
                <strong>{{ overviewStudentCount }}</strong>
                <small>产生过提问记录的学生人数</small>
              </article>
              <article class="keyword-overview-card">
                <span>关键词总数</span>
                <strong>{{ overviewKeywordCount }}</strong>
                <small>从学生问题中提取出的标签数量</small>
              </article>
              <article class="keyword-overview-card">
                <span>关键词命中</span>
                <strong>{{ overviewKeywordHits }}</strong>
                <small>按每轮提问去重后的累计命中次数</small>
              </article>
            </div>

            <div class="overview-table-grid">
              <article class="overview-table-card">
                <div class="overview-table-head">
                  <div>
                    <p class="eyebrow">关键词次数</p>
                    <h3>高频问题关键词</h3>
                  </div>
                  <span class="head-tag">{{ overviewKeywords.length }} 项</span>
                </div>

                <div class="overview-table-wrap">
                  <table class="overview-table">
                    <thead>
                      <tr>
                        <th>关键词</th>
                        <th>次数</th>
                        <th>学生数</th>
                        <th>样例</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in visibleOverviewKeywords" :key="item.keyword">
                        <td><strong>{{ item.keyword }}</strong></td>
                        <td>{{ item.count }}</td>
                        <td>{{ item.student_count }}</td>
                        <td>{{ item.sample_prompts?.[0] || '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </article>

              <article class="overview-table-card">
                <div class="overview-table-head">
                  <div>
                    <p class="eyebrow">学生问题次数</p>
                    <h3>提问学生排行</h3>
                  </div>
                  <span class="head-tag">{{ overviewStudents.length }} 名</span>
                </div>

                <div class="overview-table-wrap">
                  <table class="overview-table">
                    <thead>
                      <tr>
                        <th>学生</th>
                        <th>问题次数</th>
                        <th>涉及作业</th>
                        <th>最近提问</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in visibleOverviewStudents" :key="item.student_id">
                        <td>
                          <strong>{{ item.student_name }}</strong>
                          <small>{{ item.student_account }}</small>
                        </td>
                        <td>{{ item.question_count }}</td>
                        <td>{{ item.assignment_count }}</td>
                        <td>{{ formatTime(item.last_asked_at) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </article>
            </div>

            <div v-if="canToggleQuestionOverview" class="overview-toggle-row">
              <button class="overview-toggle-button" type="button" @click="toggleQuestionOverview">
                {{ isQuestionOverviewExpanded ? '收起总体问题统计' : '展开全部问题统计' }}
              </button>
              <span>
                当前显示 {{ visibleOverviewKeywords.length }}/{{ overviewKeywords.length }} 个关键词，
                {{ visibleOverviewStudents.length }}/{{ overviewStudents.length }} 名学生
              </span>
            </div>
          </div>
        </div>
      </section>

      <section :class="['panel keyword-board compact-panel', { 'is-collapsed': collapsedSections.keywords, 'is-drawer-open': activeDrawer === 'keywords' }]">
        <div class="section-head">
          <div>
            <p class="eyebrow">问题关键词</p>
            <h2>{{ selectedAssignment ? '本次作业里学生最常问的问题' : '请先选择一份作业' }}</h2>
          </div>
          <div class="section-head-actions">
            <span v-if="selectedAssignment" class="head-tag">
              {{ loadingKeywordSummary ? '统计中' : `${keywordSummary.length} 个高频词` }}
            </span>
            <button
              class="collapse-button"
              type="button"
              @click="activeDrawer === 'keywords' ? closeDrawer() : openSectionDrawer('keywords')"
            >
              <span>{{ activeDrawer === 'keywords' ? '关闭' : '详情' }}</span>
              <b aria-hidden="true">{{ activeDrawer === 'keywords' ? '×' : '›' }}</b>
            </button>
          </div>
        </div>
        <div class="compact-panel-summary">
          <span v-for="item in keywordsCompactSummary" :key="item">{{ item }}</span>
        </div>

        <div v-if="!collapsedSections.keywords" class="collapsible-section-body">
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
        </div>
      </section>

      <section class="workspace-grid">
        <article class="panel submission-card">
          <div class="section-head">
            <div>
              <p class="eyebrow">学生提交</p>
              <h2>{{ selectedAssignment ? '点击学生查看提交与 AI 使用情况' : '请先选择一份作业' }}</h2>
            </div>
            <span v-if="selectedAssignment" class="head-tag">{{ selectedSubmittedCount }}/{{ selectedStudentCount }} 已提交</span>
          </div>
          <div v-if="selectedAssignment" class="submission-filter-tabs" aria-label="提交筛选">
            <button type="button" :class="{ active: submissionFilter === 'all' }" @click="submissionFilter = 'all'">
              全部 {{ submissions.length }}
            </button>
            <button type="button" :class="{ active: submissionFilter === 'pending' }" @click="submissionFilter = 'pending'">
              未提交 {{ pendingSubmissionCount }}
            </button>
            <button type="button" :class="{ active: submissionFilter === 'submitted' }" @click="submissionFilter = 'submitted'">
              已提交 {{ selectedAnsweredCount }}
            </button>
            <button type="button" :class="{ active: submissionFilter === 'file' }" @click="submissionFilter = 'file'">
              附件 {{ selectedWithFileCount }}
            </button>
            <button type="button" :class="{ active: submissionFilter === 'noAi' }" @click="submissionFilter = 'noAi'">
              无 AI {{ noAiSubmissionCount }}
            </button>
            <button type="button" :class="{ active: submissionFilter === 'attention' }" @click="submissionFilter = 'attention'">
              需关注 {{ attentionSubmissionCount }}
            </button>
          </div>

          <div v-if="!selectedAssignment" class="empty-state">
            <strong>尚未选择作业</strong>
            <p>在左侧选择作业。</p>
          </div>

          <div v-else-if="loadingSubmissions" class="empty-state">
            <strong>正在加载提交列表</strong>
            <p>系统正在读取当前作业的学生提交记录。</p>
          </div>

          <div v-else-if="!submissions.length" class="empty-state">
            <strong>暂无学生记录</strong>
            <p>暂无可展示学生。</p>
          </div>

          <div v-else-if="!filteredSubmissions.length" class="empty-state">
            <strong>没有匹配学生</strong>
            <p>切换筛选条件查看。</p>
          </div>

          <div v-else class="submission-list">
            <button
              v-for="item in filteredSubmissions"
              :key="item.student_id"
              type="button"
              :class="['submission-item', item.has_submission ? 'is-submitted' : 'is-pending', { active: item.student_id === selectedStudentId }]"
              @click="openSubmissionDrawer(item.student_id)"
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

        <article :class="['panel detail-card', { 'is-drawer-open': activeDrawer === 'submission' }]">
          <div class="section-head">
            <div>
              <p class="eyebrow">提交详情</p>
              <h2>{{ selectedSubmissionSummary ? selectedSubmissionSummary.student_name : '请选择一个学生' }}</h2>
            </div>
            <div class="section-head-actions">
              <span v-if="selectedSubmissionSummary" class="head-tag">{{ selectedSubmissionSummary.has_submission ? '可查看全文' : '暂无提交' }}</span>
              <button class="drawer-close-button" type="button" @click="closeDrawer">关闭</button>
            </div>
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

            <section v-if="selectedSubmissionDetail.assessment_report" class="assessment-panel">
              <div class="answer-head">
                <span>完整评估报告</span>
                <small>
                  得分 {{ selectedSubmissionDetail.assessment_report.score }}
                  · {{ selectedSubmissionDetail.assessment_report.label }}
                </small>
              </div>

              <div class="assessment-tag-row">
                <span
                  v-for="flag in selectedSubmissionDetail.assessment_report.risk_flags"
                  :key="flag"
                  class="usage-tag"
                >
                  {{ flag }}
                </span>
              </div>

              <div class="assessment-metric-grid">
                <article
                  v-for="(value, key) in selectedSubmissionDetail.assessment_report.metrics"
                  :key="key"
                  class="assessment-metric-card"
                >
                  <span>{{ key }}</span>
                  <strong>{{ value ?? '未提供' }}</strong>
                </article>
              </div>

              <div v-if="selectedSubmissionDetail.assessment_report.supporting_chunks.length" class="assessment-evidence">
                <span class="file-panel-label">主要教材证据</span>
                <article
                  v-for="item in selectedSubmissionDetail.assessment_report.supporting_chunks"
                  :key="item.chunk_id"
                  class="assessment-evidence-item"
                >
                  <strong>{{ item.chunk_id }} · {{ item.chapter || '未识别章节' }}</strong>
                  <small>页码 {{ item.page_start }}-{{ item.page_end }} · 相关度 {{ item.combined_score }}</small>
                  <p>{{ item.snippet }}</p>
                </article>
              </div>

              <details class="assessment-markdown" open>
                <summary>查看 Markdown 报告全文</summary>
                <pre class="answer-content">{{ selectedSubmissionDetail.assessment_report.report_markdown }}</pre>
              </details>
            </section>

            <section v-else-if="selectedSubmissionDetail.has_submission" class="assessment-panel">
              <div class="answer-head">
                <span>完整评估报告</span>
                <small>暂不可用</small>
              </div>
              <div class="usage-empty">
                <strong>评估报告暂未生成</strong>
                <p>当前提交可以查看正文，但评估模型暂时没有返回报告。</p>
              </div>
            </section>

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

    <button
      v-if="activeDrawer"
      class="drawer-backdrop"
      type="button"
      aria-label="关闭详情面板"
      @click="closeDrawer"
    ></button>

    <div v-if="showPublishModal" class="modal-overlay" @click.self="closePublishModal">
      <div class="modal-card panel publish-modal">
        <div class="section-head modal-head">
          <div>
            <p class="eyebrow">发布作业</p>
            <h2>新建一份作业</h2>
          </div>
          <button class="icon-button" type="button" @click="closePublishModal">×</button>
        </div>

        <section class="publish-note-card">
          <div class="publish-note-head">
            <div>
              <p class="eyebrow">当前学生知识掌握程度</p>
              <h3>{{ currentMasteryLevel }}</h3>
            </div>
            <span class="head-tag">建议写明教材页数</span>
          </div>
          <p>{{ currentMasteryGuidance }}</p>
          <button class="ghost-button" type="button" @click="insertPublishTemplate">插入描述模板</button>
        </section>

        <label class="field">
          <span>作业标题</span>
          <input v-model="form.title" type="text" maxlength="120" placeholder="例如：数据结构实验一" />
        </label>

        <label class="field">
          <span>作业说明</span>
          <textarea
            v-model="form.description"
            rows="6"
            maxlength="4000"
            placeholder="填写作业要求、评分说明或提交约束，最好注明教材页数，例如：第3章第42-47页。"
          ></textarea>
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

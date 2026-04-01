<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import {
  activateSession,
  createSession,
  fetchMe,
  fetchSessionHistory,
  fetchSessionState,
  fetchSessions,
  login,
  register,
  runAnalysis,
} from "./api";
import type {
  AnalysisResponse,
  HistoryItem,
  SessionItem,
  SessionStateResponse,
  UserProfile,
} from "./types";

const DEFAULT_USER_GOAL =
  "我想找上海或杭州的 Java 后端 / AI 应用开发实习，希望岗位和 LangGraph、多智能体、后端开发有一定关联。";
const DEFAULT_MESSAGE = "请帮我分析这些岗位，并给出投递建议。";

const token = ref<string>(localStorage.getItem("job_assistant_token") || "");
const profile = ref<UserProfile | null>(null);
const sessions = ref<SessionItem[]>([]);
const selectedThreadId = ref("");
const sessionState = ref<SessionStateResponse | null>(null);
const lastAnalysis = ref<AnalysisResponse | null>(null);
const historyRows = ref<HistoryItem[]>([]);
const loading = ref(false);
const errorMessage = ref("");
const successMessage = ref("");
const authMode = ref<"login" | "register">("login");

const authForm = reactive({
  account: "",
  nickname: "",
  password: "",
});

const analysisForm = reactive({
  userGoal: DEFAULT_USER_GOAL,
  message: DEFAULT_MESSAGE,
  maxOptimizationRounds: 1,
  resumeMode: "sample",
  resumeText: "",
  resumeFile: null as File | null,
});

const historyLimit = ref(10);

const displayValues = computed<Record<string, any>>(() => {
  if (lastAnalysis.value?.result) return lastAnalysis.value.result;
  if (sessionState.value?.values) return sessionState.value.values;
  return {};
});

const currentMatches = computed(() => {
  const values = displayValues.value;
  const currentRound = values.optimization_round || 0;
  return (values.matches || []).filter((item: any) => (item.review_round || 0) === currentRound);
});

const finalReport = computed(() => displayValues.value.final_report || "");
const shortlist = computed(() => displayValues.value.shortlist || []);
const revisionNotes = computed(() => displayValues.value.revision_notes || []);
const analyses = computed(() => displayValues.value.analyses || []);

function setSuccess(message: string) {
  successMessage.value = message;
  errorMessage.value = "";
}

function setError(message: string) {
  errorMessage.value = message;
  successMessage.value = "";
}

async function bootstrap() {
  if (!token.value) return;
  try {
    profile.value = await fetchMe(token.value);
    await loadSessions();
    if (selectedThreadId.value) {
      await loadSessionState();
    }
  } catch (error: any) {
    logout();
    setError(error.message || "登录状态失效，请重新登录。");
  }
}

async function loadSessions() {
  if (!token.value) return;
  const response = await fetchSessions(token.value);
  sessions.value = response.sessions;
  selectedThreadId.value = response.active_thread_id || response.sessions[0]?.thread_id || "";
}

async function loadSessionState() {
  if (!token.value || !selectedThreadId.value) return;
  sessionState.value = await fetchSessionState(token.value, selectedThreadId.value);
}

async function loadHistory() {
  if (!token.value || !selectedThreadId.value) return;
  historyRows.value = await fetchSessionHistory(token.value, selectedThreadId.value, historyLimit.value);
  setSuccess("已读取历史快照。");
}

async function handleAuth() {
  loading.value = true;
  try {
    if (authMode.value === "login") {
      const response = await login({
        account: authForm.account,
        password: authForm.password,
      });
      if (!response.ok || !response.token || !response.profile) {
        throw new Error(response.message || "登录失败");
      }
      token.value = response.token;
      localStorage.setItem("job_assistant_token", response.token);
      profile.value = response.profile;
      setSuccess(response.message);
    } else {
      const response = await register({
        account: authForm.account,
        nickname: authForm.nickname,
        password: authForm.password,
      });
      if (!response.ok || !response.token || !response.profile) {
        throw new Error(response.message || "注册失败");
      }
      token.value = response.token;
      localStorage.setItem("job_assistant_token", response.token);
      profile.value = response.profile;
      setSuccess(response.message);
    }
    authForm.password = "";
    await loadSessions();
    await loadSessionState();
  } catch (error: any) {
    setError(error.message || "认证失败");
  } finally {
    loading.value = false;
  }
}

async function handleCreateSession() {
  if (!token.value) return;
  loading.value = true;
  try {
    const response = await createSession(token.value);
    selectedThreadId.value = response.active_thread_id;
    await loadSessions();
    sessionState.value = null;
    lastAnalysis.value = null;
    historyRows.value = [];
    setSuccess("已创建新会话。");
  } catch (error: any) {
    setError(error.message || "创建会话失败");
  } finally {
    loading.value = false;
  }
}

async function handleActivateSession(threadId: string) {
  if (!token.value) return;
  loading.value = true;
  try {
    await activateSession(token.value, threadId);
    selectedThreadId.value = threadId;
    await loadSessions();
    await loadSessionState();
    historyRows.value = [];
    lastAnalysis.value = null;
    setSuccess("已切换会话。");
  } catch (error: any) {
    setError(error.message || "切换会话失败");
  } finally {
    loading.value = false;
  }
}

async function handleRun(continueSession = false) {
  if (!token.value || !selectedThreadId.value) return;
  loading.value = true;
  try {
    const resumeText =
      analysisForm.resumeMode === "paste" ? analysisForm.resumeText.trim() : "";
    const resumeFile =
      analysisForm.resumeMode === "upload" ? analysisForm.resumeFile : null;
    const response = await runAnalysis(token.value, {
      threadId: selectedThreadId.value,
      continueSession,
      userGoal: analysisForm.userGoal.trim() || DEFAULT_USER_GOAL,
      message: analysisForm.message.trim() || DEFAULT_MESSAGE,
      resumeText: resumeText || undefined,
      resumeFile,
      maxOptimizationRounds: Number(analysisForm.maxOptimizationRounds) || 1,
    });
    lastAnalysis.value = response;
    await loadSessionState();
    await loadSessions();
    setSuccess(continueSession ? "已基于历史会话继续分析。" : "分析完成。");
  } catch (error: any) {
    setError(error.message || "分析失败");
  } finally {
    loading.value = false;
  }
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  analysisForm.resumeFile = input.files?.[0] || null;
}

function logout() {
  token.value = "";
  profile.value = null;
  sessions.value = [];
  selectedThreadId.value = "";
  sessionState.value = null;
  lastAnalysis.value = null;
  historyRows.value = [];
  localStorage.removeItem("job_assistant_token");
  setSuccess("已退出登录。");
}

onMounted(() => {
  bootstrap();
});
</script>

<template>
  <div class="app-shell">
    <template v-if="!profile">
      <main class="auth-layout">
        <section class="hero-card">
          <p class="eyebrow">Vue + FastAPI Upgrade</p>
          <h1>把 LangGraph 多智能体求职助手升级成前后端分离项目。</h1>
          <p class="subtitle">
            现在前端负责账户、会话、上传和展示，后端负责 LangGraph 工作流、SQLite checkpoint 和分析接口。
          </p>
          <div class="hero-grid">
            <div class="metric-card">
              <span>后端</span>
              <strong>FastAPI</strong>
            </div>
            <div class="metric-card">
              <span>前端</span>
              <strong>Vue 3 + Vite</strong>
            </div>
            <div class="metric-card">
              <span>状态持久化</span>
              <strong>SQLite checkpoint</strong>
            </div>
            <div class="metric-card">
              <span>核心能力</span>
              <strong>Command / Send / 子图</strong>
            </div>
          </div>
        </section>

        <section class="auth-card">
          <div class="tab-switch">
            <button :class="{ active: authMode === 'login' }" @click="authMode = 'login'">登录</button>
            <button :class="{ active: authMode === 'register' }" @click="authMode = 'register'">注册</button>
          </div>

          <div class="field">
            <label>账号</label>
            <input v-model="authForm.account" placeholder="例如 lichunfeng" />
          </div>

          <div class="field" v-if="authMode === 'register'">
            <label>昵称</label>
            <input v-model="authForm.nickname" placeholder="页面中显示的名字" />
          </div>

          <div class="field">
            <label>密码</label>
            <input v-model="authForm.password" type="password" placeholder="至少 6 位" />
          </div>

          <button class="primary-button" :disabled="loading" @click="handleAuth">
            {{ loading ? "处理中..." : authMode === "login" ? "进入工作台" : "注册并进入" }}
          </button>

          <p v-if="successMessage" class="feedback success">{{ successMessage }}</p>
          <p v-if="errorMessage" class="feedback error">{{ errorMessage }}</p>
        </section>
      </main>
    </template>

    <template v-else>
      <aside class="sidebar">
        <div class="profile-panel">
          <div class="badge">Workspace</div>
          <h2>{{ profile.nickname }}</h2>
          <p>{{ profile.account }}</p>
          <small>活跃会话：{{ selectedThreadId || "未选择" }}</small>
        </div>

        <div class="sidebar-section">
          <div class="section-head">
            <h3>我的会话</h3>
            <button class="ghost-button" :disabled="loading" @click="handleCreateSession">新建</button>
          </div>
          <div class="session-list">
            <button
              v-for="session in sessions"
              :key="session.thread_id"
              class="session-item"
              :class="{ active: selectedThreadId === session.thread_id }"
              @click="handleActivateSession(session.thread_id)"
            >
              <strong>{{ session.label }}</strong>
              <span>{{ session.updated_at }}</span>
            </button>
          </div>
        </div>

        <div class="sidebar-section">
          <div class="section-head">
            <h3>读取会话</h3>
          </div>
          <div class="toolbar">
            <button class="ghost-button" :disabled="loading" @click="loadSessionState">当前状态</button>
            <button class="ghost-button" :disabled="loading" @click="loadHistory">历史快照</button>
          </div>
        </div>

        <div class="sidebar-section">
          <button class="danger-button" @click="logout">退出登录</button>
        </div>
      </aside>

      <main class="workspace">
        <header class="workspace-header">
          <div>
            <p class="eyebrow">Vue Workspace</p>
            <h1>LangGraph 多智能体求职工作台</h1>
            <p class="subtitle">
              当前会话：{{ selectedThreadId || "未选择" }}。在这里提交求职目标、简历和消息，后端会调用 LangGraph 状态图完成分析。
            </p>
          </div>
        </header>

        <div v-if="successMessage" class="banner success">{{ successMessage }}</div>
        <div v-if="errorMessage" class="banner error">{{ errorMessage }}</div>

        <section class="content-grid">
          <article class="panel">
            <div class="section-head">
              <h2>运行分析</h2>
            </div>

            <div class="field">
              <label>求职目标</label>
              <textarea v-model="analysisForm.userGoal" rows="4"></textarea>
            </div>

            <div class="field">
              <label>用户消息</label>
              <input v-model="analysisForm.message" />
            </div>

            <div class="field">
              <label>最大简历优化轮次</label>
              <input v-model="analysisForm.maxOptimizationRounds" type="number" min="0" max="5" />
            </div>

            <div class="field">
              <label>简历输入方式</label>
              <div class="radio-row">
                <label><input v-model="analysisForm.resumeMode" value="sample" type="radio" /> 示例简历</label>
                <label><input v-model="analysisForm.resumeMode" value="paste" type="radio" /> 粘贴文本</label>
                <label><input v-model="analysisForm.resumeMode" value="upload" type="radio" /> 上传文件</label>
              </div>
            </div>

            <div v-if="analysisForm.resumeMode === 'paste'" class="field">
              <label>粘贴简历</label>
              <textarea v-model="analysisForm.resumeText" rows="10"></textarea>
            </div>

            <div v-if="analysisForm.resumeMode === 'upload'" class="field">
              <label>上传简历文件（txt / md / pdf）</label>
              <input type="file" accept=".txt,.md,.pdf" @change="onFileChange" />
              <small v-if="analysisForm.resumeFile">已选择：{{ analysisForm.resumeFile.name }}</small>
            </div>

            <div class="toolbar">
              <button class="primary-button" :disabled="loading || !selectedThreadId" @click="handleRun(false)">
                {{ loading ? "分析中..." : "启动新分析" }}
              </button>
              <button class="ghost-button" :disabled="loading || !selectedThreadId" @click="handleRun(true)">
                继续当前会话
              </button>
            </div>
          </article>

          <article class="panel">
            <div class="section-head">
              <h2>会话摘要</h2>
            </div>

            <div class="metric-grid">
              <div class="metric-card">
                <span>岗位数</span>
                <strong>{{ sessionState?.summary.jobs_count ?? 0 }}</strong>
              </div>
              <div class="metric-card">
                <span>分析数</span>
                <strong>{{ sessionState?.summary.analyses_count ?? 0 }}</strong>
              </div>
              <div class="metric-card">
                <span>匹配数</span>
                <strong>{{ sessionState?.summary.matches_count ?? 0 }}</strong>
              </div>
              <div class="metric-card">
                <span>优化轮次</span>
                <strong>{{ sessionState?.summary.optimization_round ?? 0 }}</strong>
              </div>
            </div>

            <div class="field">
              <label>当前求职目标</label>
              <div class="display-box">{{ sessionState?.summary.user_goal || "暂无会话摘要" }}</div>
            </div>

            <div class="field">
              <label>推荐岗位</label>
              <div class="chip-row">
                <span v-for="item in (sessionState?.summary.shortlist || [])" :key="item" class="chip">{{ item }}</span>
              </div>
            </div>
          </article>
        </section>

        <section class="content-grid">
          <article class="panel">
            <div class="section-head">
              <h2>最终建议</h2>
            </div>
            <div class="report-box">
              {{ finalReport || "当前还没有最终报告。请先运行分析或继续会话。" }}
            </div>
          </article>

          <article class="panel">
            <div class="section-head">
              <h2>历史快照</h2>
              <input v-model="historyLimit" type="number" min="1" max="50" />
            </div>
            <div v-if="historyRows.length === 0" class="display-box">还没有读取历史快照。</div>
            <div v-else class="history-list">
              <div v-for="item in historyRows" :key="item.checkpoint_id" class="history-item">
                <strong>{{ item.created_at || "未知时间" }}</strong>
                <span>step={{ item.step ?? "-" }} / source={{ item.source ?? "-" }}</span>
                <span>next={{ item.next.join(", ") || "END" }}</span>
                <span>analyses={{ item.analyses_count }} / matches={{ item.matches_count }}</span>
              </div>
            </div>
          </article>
        </section>

        <section class="content-grid">
          <article class="panel">
            <div class="section-head">
              <h2>岗位分析</h2>
            </div>
            <div v-if="analyses.length === 0" class="display-box">当前还没有岗位分析。</div>
            <div v-else class="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>岗位 ID</th>
                    <th>城市</th>
                    <th>摘要</th>
                    <th>推荐理由</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in analyses" :key="item.job_id">
                    <td>{{ item.job_id }}</td>
                    <td>{{ item.city }}</td>
                    <td>{{ item.summary }}</td>
                    <td>{{ item.recommendation_reason }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>

          <article class="panel">
            <div class="section-head">
              <h2>当前轮匹配结果</h2>
            </div>
            <div v-if="currentMatches.length === 0" class="display-box">当前还没有匹配结果。</div>
            <div v-else class="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>岗位 ID</th>
                    <th>分数</th>
                    <th>结论</th>
                    <th>投递策略</th>
                    <th>短板</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in currentMatches" :key="`${item.job_id}-${item.review_round}`">
                    <td>{{ item.job_id }}</td>
                    <td>{{ item.score }}</td>
                    <td>{{ item.verdict }}</td>
                    <td>{{ item.application_strategy }}</td>
                    <td>{{ (item.gaps || []).join("；") }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </article>
        </section>

        <section class="panel">
          <div class="section-head">
            <h2>简历优化记录</h2>
          </div>
          <div v-if="revisionNotes.length === 0" class="display-box">当前没有简历优化记录。</div>
          <div v-else class="chip-row">
            <span v-for="(note, idx) in revisionNotes" :key="idx" class="chip chip-accent">{{ note }}</span>
          </div>
        </section>
      </main>
    </template>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
  color: #1f2937;
}

.auth-layout {
  width: 100%;
  padding: 3rem;
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 2rem;
}

.hero-card,
.auth-card,
.panel,
.profile-panel,
.sidebar-section {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(229, 231, 235, 0.9);
  border-radius: 24px;
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.08);
}

.hero-card,
.auth-card,
.panel {
  padding: 1.5rem;
}

.eyebrow,
.badge {
  display: inline-block;
  padding: 0.3rem 0.65rem;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.1);
  color: #0f766e;
  font-size: 0.8rem;
  font-weight: 700;
  margin-bottom: 1rem;
}

.hero-card h1,
.workspace-header h1 {
  font-size: clamp(2rem, 4vw, 3.1rem);
  line-height: 1.1;
  margin: 0 0 1rem;
}

.subtitle {
  color: #6b7280;
  line-height: 1.8;
}

.hero-grid,
.metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  margin-top: 1.2rem;
}

.metric-card {
  background: #fafaf9;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  padding: 1rem;
}

.metric-card span {
  display: block;
  color: #6b7280;
  margin-bottom: 0.35rem;
}

.metric-card strong {
  font-size: 1.3rem;
}

.tab-switch {
  display: flex;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.tab-switch button,
.primary-button,
.ghost-button,
.danger-button,
.session-item {
  border: none;
  border-radius: 16px;
  padding: 0.8rem 1rem;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.tab-switch button {
  flex: 1;
  background: #f3f4f6;
  color: #374151;
}

.tab-switch button.active {
  background: linear-gradient(135deg, #0f766e, #14b8a6);
  color: white;
}

.primary-button {
  background: linear-gradient(135deg, #0f766e, #14b8a6);
  color: white;
  width: 100%;
}

.ghost-button {
  background: #f8fafc;
  color: #0f172a;
  border: 1px solid #dbe3ea;
}

.danger-button {
  background: #fee2e2;
  color: #b91c1c;
  width: 100%;
}

.primary-button:hover,
.ghost-button:hover,
.danger-button:hover,
.session-item:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.08);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  margin-bottom: 1rem;
}

.field label {
  font-size: 0.92rem;
  font-weight: 700;
}

.field input,
.field textarea,
.section-head input {
  width: 100%;
  border: 1px solid #dbe3ea;
  border-radius: 16px;
  padding: 0.85rem 1rem;
  background: #fbfcfd;
}

.feedback,
.banner {
  margin-top: 0.9rem;
  border-radius: 16px;
  padding: 0.8rem 1rem;
}

.success {
  background: #dcfce7;
  color: #166534;
}

.error {
  background: #fee2e2;
  color: #991b1b;
}

.sidebar {
  width: 310px;
  border-right: 1px solid rgba(229, 231, 235, 0.9);
  padding: 1.2rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.profile-panel,
.sidebar-section {
  padding: 1rem;
}

.profile-panel h2 {
  margin: 0 0 0.35rem;
}

.profile-panel p,
.profile-panel small {
  color: #6b7280;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}

.section-head h2,
.section-head h3 {
  margin: 0;
}

.workspace {
  flex: 1;
  padding: 1.6rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.content-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.toolbar {
  display: flex;
  gap: 0.75rem;
}

.toolbar > * {
  flex: 1;
}

.session-list,
.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.session-item {
  text-align: left;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  border: 1px solid transparent;
}

.session-item.active {
  border-color: #14b8a6;
  background: #ecfeff;
}

.session-item span {
  color: #6b7280;
  font-size: 0.85rem;
}

.display-box,
.report-box,
.history-item {
  background: #fafaf9;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 1rem;
}

.report-box {
  min-height: 220px;
  white-space: pre-wrap;
  line-height: 1.85;
}

.history-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.chip {
  display: inline-flex;
  padding: 0.35rem 0.7rem;
  border-radius: 999px;
  background: #f1f5f9;
  border: 1px solid #dbe3ea;
}

.chip-accent {
  background: rgba(15, 118, 110, 0.1);
  color: #0f766e;
}

.radio-row {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.table-wrapper {
  overflow: auto;
  border-radius: 18px;
  border: 1px solid #e5e7eb;
}

table {
  width: 100%;
  border-collapse: collapse;
  min-width: 640px;
}

thead {
  background: #f8fafc;
}

th,
td {
  padding: 0.9rem 1rem;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
}

@media (max-width: 1100px) {
  .auth-layout,
  .content-grid {
    grid-template-columns: 1fr;
  }

  .app-shell {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid rgba(229, 231, 235, 0.9);
  }
}
</style>

import type {
  AnalysisResponse,
  AuthResponse,
  HistoryItem,
  SessionItem,
  SessionStateResponse,
  UserProfile,
} from "./types";

const API_BASE = "/api";

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers || {});
  if (!(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const data = await response.json();
      message = data.detail || data.message || message;
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export function register(payload: {
  account: string;
  nickname: string;
  password: string;
}): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function login(payload: {
  account: string;
  password: string;
}): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchMe(token: string): Promise<UserProfile> {
  return request<UserProfile>("/auth/me", {}, token);
}

export async function fetchSessions(token: string): Promise<{
  active_thread_id: string;
  sessions: SessionItem[];
}> {
  return request("/sessions", {}, token);
}

export async function createSession(token: string): Promise<{ ok: boolean; active_thread_id: string }> {
  return request("/sessions", { method: "POST" }, token);
}

export async function activateSession(
  token: string,
  threadId: string,
): Promise<{ ok: boolean; active_thread_id: string }> {
  return request(`/sessions/${threadId}/activate`, { method: "POST" }, token);
}

export function fetchSessionState(token: string, threadId: string): Promise<SessionStateResponse> {
  return request<SessionStateResponse>(`/sessions/${threadId}`, {}, token);
}

export function fetchSessionHistory(
  token: string,
  threadId: string,
  limit = 10,
): Promise<HistoryItem[]> {
  return request<HistoryItem[]>(`/sessions/${threadId}/history?limit=${limit}`, {}, token);
}

export function runAnalysis(
  token: string,
  payload: {
    threadId: string;
    continueSession: boolean;
    userGoal: string;
    message: string;
    resumeText?: string;
    maxOptimizationRounds: number;
    resumeFile?: File | null;
  },
): Promise<AnalysisResponse> {
  const formData = new FormData();
  formData.append("thread_id", payload.threadId);
  formData.append("continue_session", String(payload.continueSession));
  formData.append("user_goal", payload.userGoal);
  formData.append("message", payload.message);
  formData.append("max_optimization_rounds", String(payload.maxOptimizationRounds));
  if (payload.resumeText) {
    formData.append("resume_text", payload.resumeText);
  }
  if (payload.resumeFile) {
    formData.append("resume_file", payload.resumeFile);
  }

  return request<AnalysisResponse>("/analysis/run", {
    method: "POST",
    body: formData,
  }, token);
}

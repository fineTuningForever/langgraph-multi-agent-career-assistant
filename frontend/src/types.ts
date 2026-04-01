export interface UserProfile {
  account: string;
  nickname: string;
  created_at: string;
  last_login_at: string;
  active_thread_id: string;
  sessions: SessionItem[];
}

export interface SessionItem {
  thread_id: string;
  label: string;
  created_at: string;
  updated_at: string;
}

export interface SessionSummary {
  user_goal: string;
  jobs_count: number;
  analyses_count: number;
  matches_count: number;
  optimization_round: number;
  has_final_report: boolean;
  shortlist: string[];
  revision_notes: string[];
}

export interface SessionStateResponse {
  thread_id: string;
  values: Record<string, any>;
  summary: SessionSummary;
}

export interface HistoryItem {
  created_at: string;
  next: string[];
  step: number | null;
  source: string | null;
  analyses_count: number;
  matches_count: number;
  optimization_round: number;
  has_final_report: boolean;
  checkpoint_id: string;
}

export interface AnalysisResponse {
  thread_id: string;
  result: Record<string, any>;
  summary: SessionSummary;
}

export interface AuthResponse {
  ok: boolean;
  message: string;
  token?: string | null;
  profile?: UserProfile | null;
}

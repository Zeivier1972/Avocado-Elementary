// Minimal API client. Base URL comes from NEXT_PUBLIC_API_URL (set per env).
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const TOKEN_KEY = "avocado_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  window.localStorage.removeItem(TOKEN_KEY);
}

async function req(path: string, opts: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...opts, headers });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(`${res.status}: ${msg}`);
  }
  return res.json();
}

export async function login(email: string, password: string) {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) throw new Error("Invalid email or password");
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

export const api = {
  me: () => req("/auth/me"),
  teacherDashboard: () => req("/dashboard/teacher"),
  principalDashboard: () => req("/dashboard/principal"),
  groups: () => req("/di/groups"),
  generatePlan: (groupId: string) =>
    req(`/di/groups/${groupId}/plan`, { method: "POST" }),
  importAssessment: (form: FormData) =>
    req("/assessments/import", { method: "POST", body: form }),
  coachDashboard: () => req("/coach/dashboard"),
  pacingTopic: (topicId: string) => req(`/pacing/${topicId}`),
  generateAgenda: (topicId: string) =>
    req(`/coach/agenda/${topicId}`, { method: "POST" }),
  generateGuide: (topicId: string) =>
    req(`/coach/guide/${topicId}`, { method: "POST" }),
  schoolSummary: () => req("/admin/school/summary"),
  importRoster: (form: FormData) =>
    req("/admin/roster/import", { method: "POST", body: form }),
  importExcel: (form: FormData) =>
    req("/admin/import/excel", { method: "POST", body: form }),
  reportsOverview: () => req("/reports/overview"),
  gradeReport: (grade: string) => req(`/reports/grade/${grade}`),
  fastAnalysis: (grade: string, subject: string, period: string) =>
    req(`/reports/fast/${grade}?subject=${subject}&period=${period}`),
  aiCheck: () => req("/coach/ai-check"),
  assistant: (message: string, history: any[]) =>
    req("/coach/assistant", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    }),
};

// Download the planning guide as a Word document (blob, not JSON).
export async function downloadGuideDocx(guide: any) {
  const token = getToken();
  const res = await fetch(`${API_URL}/coach/guide/export/docx`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(guide),
  });
  if (!res.ok) throw new Error("Export failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = (guide.title || "planning-guide").replace(/[^\w]+/g, "_") + ".docx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

const COACH_ROLES = [
  "math_coach",
  "reading_coach",
  "instructional_coach",
  "principal",
  "ap",
  "district_admin",
];

export function homeForRole(role: string): string {
  return COACH_ROLES.includes(role) ? "/coach" : "/dashboard";
}

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

// Shared grade selection so the analytics cluster (Reports · Analysis ·
// Assessments · Goal) stays on the same grade as you move between them.
const GRADE_KEY = "avocado_grade";
export function getSharedGrade(fallback = "3"): string {
  if (typeof window === "undefined") return fallback;
  try {
    return window.localStorage.getItem(GRADE_KEY) || fallback;
  } catch {
    return fallback;
  }
}
export function setSharedGrade(g: string) {
  try {
    window.localStorage.setItem(GRADE_KEY, g);
  } catch {
    /* ignore */
  }
}

async function req(path: string, opts: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(opts.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...opts, headers });
  // Session expired / invalid token: clear it and send the user to sign in
  // again instead of surfacing a raw "401 Invalid token" on every action.
  if (res.status === 401 && token) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/?expired=1";
    }
    throw new Error("Your session expired — please sign in again.");
  }
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
  health: () => req("/health"),
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
  schoolGoal: () => req("/reports/school-goal"),
  gradeReport: (grade: string) => req(`/reports/grade/${grade}`),
  fastAnalysis: (grade: string, subject: string, period: string) =>
    req(`/reports/fast/${grade}?subject=${subject}&period=${period}`),
  teachers: () => req("/reports/teachers"),
  teacherReport: (id: string) => req(`/reports/teacher/${id}`),
  goalAnalysis: (grade: string) => req(`/reports/goal-analysis/${grade}`),
  guideSummary: (id: string) => req(`/coach/guides/${id}/summary`),
  getFramework: () => req("/coach/framework"),
  frameworkForTopic: (body: any) =>
    req("/coach/framework/for-topic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  frameworkApplications: (grade?: string) =>
    req(`/coach/framework/applications${grade ? `?grade=${grade}` : ""}`),
  deleteFrameworkApplication: (id: string) =>
    req(`/coach/framework/applications/${id}`, { method: "DELETE" }),
  getCollab: () => req("/coach/collab"),
  loadCollab: () => req("/coach/collab/load", { method: "POST" }),
  setCollabWeek: (week: string) =>
    req(`/coach/collab/set-week?week=${week}`, { method: "POST" }),
  updateCollab: (id: string, body: any) =>
    req(`/coach/collab/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteCollab: (id: string) =>
    req(`/coach/collab/${id}`, { method: "DELETE" }),
  getSchedule: () => req("/coach/schedule"),
  getVisitPlan: (kind: string, minutes: number, grade: string) =>
    req(
      `/coach/schedule/visit-plan?kind=${kind}&minutes=${minutes}${
        grade ? `&grade=${encodeURIComponent(grade)}` : ""
      }`
    ),
  importSchedule: (form: FormData) =>
    req("/coach/schedule/import", { method: "POST", body: form }),
  getTier2: (grade = "") =>
    req(`/coach/tier2${grade ? `?grade=${encodeURIComponent(grade)}` : ""}`),
  diFocus: (grade: string, standard: string, formId = "") =>
    req(
      `/coach/di-focus?grade=${encodeURIComponent(grade)}&standard=${encodeURIComponent(
        standard
      )}${formId ? `&form_id=${encodeURIComponent(formId)}` : ""}`
    ),
  getStaff: () => req("/coach/staff"),
  importStaff: (form: FormData) =>
    req("/coach/staff/import", { method: "POST", body: form }),
  getTopicTests: () => req("/coach/assessments"),
  getTopicTest: (id: string) => req(`/coach/assessments/${id}`),
  importTopicTest: (form: FormData) =>
    req("/coach/assessments/import", { method: "POST", body: form }),
  deleteTopicTest: (id: string) =>
    req(`/coach/assessments/${id}`, { method: "DELETE" }),
  getResults: (id: string) => req(`/coach/assessments/${id}/results`),
  importResults: (id: string, form: FormData) =>
    req(`/coach/assessments/${id}/results`, { method: "POST", body: form }),
  coachHome: () => req("/coach/home"),
  teacherHub: (id: string) => req(`/coach/teacher/${id}/hub`),
  teacherNotes: (id: string) => req(`/coach/teacher/${id}/notes`),
  addTeacherNote: (id: string, body: any) =>
    req(`/coach/teacher/${id}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  toggleNote: (id: string) => req(`/coach/notes/${id}`, { method: "PATCH" }),
  deleteNote: (id: string) => req(`/coach/notes/${id}`, { method: "DELETE" }),
  keyDates: (category?: string) =>
    req(`/coach/dates${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  addKeyDate: (body: any) =>
    req("/coach/dates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteKeyDate: (id: string) =>
    req(`/coach/dates/${id}`, { method: "DELETE" }),
  resetRoster: () => req("/admin/roster/reset", { method: "POST" }),
  deletePacingTopic: (id: string) =>
    req(`/coach/pacing/${id}`, { method: "DELETE" }),
  reloadPacing: () => req("/coach/pacing/reload", { method: "POST" }),
  clearTopics: (grade: string) =>
    req("/coach/pacing/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ grade_level: grade }),
    }),
  assessmentSchedule: (grade: string) =>
    req(`/coach/calendar/assessment-schedule?grade=${encodeURIComponent(grade)}`),
  calendarFromDocument: (id: string, yearStart?: number) =>
    req(`/coach/calendar/from-document/${id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year_start: yearStart || null }),
    }),
  createTopic: (body: any) =>
    req("/coach/pacing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  gradeStandards: (grade: string) =>
    req(`/coach/standards?grade=${encodeURIComponent(grade)}`),
  listDocuments: (grade: string) =>
    req(`/coach/documents?grade_level=${encodeURIComponent(grade)}`),
  uploadDocument: (form: FormData) =>
    req("/coach/documents", { method: "POST", body: form }),
  deleteDocument: (id: string) =>
    req(`/coach/documents/${id}`, { method: "DELETE" }),
  generateGuideFromDoc: (id: string) =>
    req(`/coach/documents/${id}/generate-guide`, { method: "POST" }),
  pacingFromDocument: (form: FormData) =>
    req("/coach/pacing/from-document", { method: "POST", body: form }),
  listGuides: (grade: string) =>
    req(`/coach/guides?grade_level=${encodeURIComponent(grade)}`),
  getGuide: (id: string) => req(`/coach/guides/${id}`),
  deleteGuide: (id: string) =>
    req(`/coach/guides/${id}`, { method: "DELETE" }),
  simplifyGuide: (id: string) =>
    req(`/coach/guides/${id}/simplify`, { method: "POST" }),
  getCalendar: (grade: string, subject = "MATH", start = "", end = "") =>
    req(
      `/coach/calendar?grade=${encodeURIComponent(grade)}&subject=${subject}` +
        (start ? `&start=${start}` : "") +
        (end ? `&end=${end}` : "")
    ),
  generateCalendar: (body: any) =>
    req("/coach/calendar/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  addCalendarEntry: (body: any) =>
    req("/coach/calendar/entry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  appendCalendarTopic: (body: {
    grade_level: string;
    subject?: string;
    topic_code?: string;
    start_date?: string;
  }) =>
    req("/coach/calendar/append-topic", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteCalendarEntry: (id: string) =>
    req(`/coach/calendar/entry/${id}`, { method: "DELETE" }),
  aiCheck: () => req("/coach/ai-check"),
  assistant: (message: string, history: any[]) =>
    req("/coach/assistant", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    }),
  assistantHistory: () => req("/coach/assistant/history"),
  clearAssistant: () => req("/coach/assistant/history", { method: "DELETE" }),
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

// Download the Coach One-Pager for a saved guide as a Word document (blob).
export async function downloadGuideSummaryDocx(id: string, title?: string) {
  const token = getToken();
  const res = await fetch(`${API_URL}/coach/guides/${id}/summary.docx`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  if (!res.ok) throw new Error("Export failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = ((title || "coach-one-pager").replace(/[^\w]+/g, "_")) + "_OnePager.docx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Download the teacher planning-template walkout for a saved guide (Word blob).
// Pass example=true for a filled sample.
export async function downloadPlanningTemplateDocx(
  id: string,
  title?: string,
  example = false
) {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(
      `${API_URL}/coach/guides/${id}/template.docx${example ? "?example=1" : ""}`,
      { headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } }
    );
  } catch (e) {
    throw new Error(
      `Could not reach the server (${(e as Error).message}). API URL: ${API_URL}`
    );
  }
  if (!res.ok) {
    let body = "";
    try {
      body = await res.text();
    } catch {
      /* ignore */
    }
    throw new Error(`Server ${res.status}: ${body.slice(0, 300) || "no detail"}`);
  }
  const blob = await res.blob();
  if (!blob.size) throw new Error("The server returned an empty file.");
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download =
    ((title || "planning-template").replace(/[^\w]+/g, "_")) +
    (example ? "_PlanningTemplate_Example.docx" : "_PlanningTemplate.docx");
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Download the color-coded Math Goal Analysis as an Excel report (blob).
export async function downloadGoalAnalysisXlsx(grade: string) {
  const token = getToken();
  const res = await fetch(`${API_URL}/reports/goal-analysis/${grade}.xlsx`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  if (!res.ok) throw new Error("Export failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `MathGoalAnalysis_Grade${grade}.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Download the ready-to-fill results template for a topic test (blob).
export async function downloadResultsTemplate(id: string) {
  const token = getToken();
  const res = await fetch(
    `${API_URL}/coach/assessments/${id}/results-template.xlsx`,
    { headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) } }
  );
  if (!res.ok) throw new Error("Template download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `results-template.xlsx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Download an uploaded planning document (blob).
export async function downloadDocument(id: string, filename: string) {
  const token = getToken();
  const res = await fetch(`${API_URL}/coach/documents/${id}/download`, {
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  if (!res.ok) throw new Error("Download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "document";
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
  return COACH_ROLES.includes(role) ? "/home" : "/dashboard";
}

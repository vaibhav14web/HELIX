const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new ApiError(res.status, text)
  }
  return res.json()
}

// ── Types ──

export interface HealthResponse {
  status: string
  modules: string[]
  state: string
}

export interface ConversationStoreRequest {
  session_id: string
  role: string
  content: string
  companion_id?: string
}

export interface ChatResponse {
  response: string
  session_id: string
}

export interface ConversationEntry {
  session_id: string
  role: string
  content: string
  timestamp: string
  companion_id: string
}

export interface ConversationHistory {
  session_id: string
  entries: ConversationEntry[]
}

export interface SessionRequest {
  session_id: string
}

export interface ProjectRequest {
  session_id: string
  project: string
}

export interface ContextResponse {
  session_id: string
  context: Record<string, unknown>
}

export interface SystemProfile {
  username: string
  hostname: string
}

export interface SystemStats {
  conversations: number
  preferences: number
  explanations: number
  permissions_historical: number
  pending_permissions: number
}

export interface SpeakResponse {
  status: string
  session_id: string
  audio: string | null
}

export interface VoiceCommandResponse {
  text: string
  response: string
  session_id: string
  audio: string | null
}

export interface VoiceTranscribeResponse {
  text: string
  session_id: string
}

export interface PermissionRequestPayload {
  action: string
  reasoning: string
  benefits?: string[]
  risks?: string[]
  alternatives?: string[]
  source_module?: string
  resources?: string[]
  scope?: string
  level?: string
}

export interface PermissionResponse {
  id: string
  action: string
  status?: string
  reasoning: string
  benefits: string[]
  risks: string[]
  alternatives: string[]
  resources?: string[]
  source_module: string
  created_at: string
  scope?: string
  level?: string
  decided_at?: string
}

export interface WorkContextResponse {
  session_id: string
  context: Record<string, unknown> | null
}

export interface WorkTasksResponse {
  session_id: string
  tasks: string[]
}

export interface ScratchpadResponse {
  session_id: string
  content: string
}

export interface PreferenceEntry {
  key: string
  value: unknown
  category: string
  source: string
}

export interface PreferencesResponse {
  category: string | null
  entries: PreferenceEntry[]
}

export interface ExplainLogRequest {
  action: string
  reasoning: string
  benefits?: string[]
  risks?: string[]
  alternatives?: string[]
  rationale?: string
  source_module?: string
  outcome?: string
}

export interface StateResponse {
  state: string
}

export interface ProductivityPattern {
  action: string
  category: string
  description: string
  frequency: number
  first_observed: string
  last_observed: string
  suggested: boolean
  automated: boolean
}

export interface ProductivitySuggestion {
  suggestion_id: string
  action: string
  title: string
  description: string
  workflow: Record<string, unknown>
  status: string
  created_at: string
}

export interface LogRecord {
  timestamp: string | null
  level: string
  module: string
  message: string
}

// ── API functions ──

export const api = {
  health: () => request<HealthResponse>('/health'),

  session: {
    start: (session_id: string) => request<{ session_id: string }>('/session/start', {
      method: 'POST',
      body: JSON.stringify({ session_id }),
    }),
    end: (session_id: string) => request<{ session_id: string }>('/session/end', {
      method: 'POST',
      body: JSON.stringify({ session_id }),
    }),
  },

  conversation: {
    store: (payload: ConversationStoreRequest) =>
      request<{ session_id: string; role: string }>('/conversation/store', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  },

  chat: {
    send: (message: string, session_id = 'default') => request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id }),
    }),
    stop: (session_id = 'default') => request<{ status: string }>('/chat/stop', {
      method: 'POST',
      body: JSON.stringify({ session_id }),
    }),
    history: (session_id: string, limit = 50) =>
      request<ConversationHistory>(`/conversation/${session_id}?limit=${limit}`),
    search: (query: string, limit = 10) =>
      request<{ query: string; results: ConversationEntry[] }>(`/conversation/search?query=${encodeURIComponent(query)}&limit=${limit}`),
    sessions: () => request<{ sessions: string[] }>('/conversation/sessions'),
  },

  voice: {
    speak: (text: string, session_id = 'default') => request<SpeakResponse>('/speak', {
      method: 'POST',
      body: JSON.stringify({ text, session_id }),
    }),
    command: async (file: Blob, session_id = 'default'): Promise<VoiceCommandResponse> => {
      const form = new FormData()
      form.append('file', file, 'audio.webm')
      form.append('session_id', session_id)
      const res = await fetch(`${API_BASE}/voice/command`, { method: 'POST', body: form })
      if (!res.ok) throw new ApiError(res.status, await res.text())
      return res.json()
    },
    transcribe: async (file: Blob, session_id = 'default'): Promise<VoiceTranscribeResponse> => {
      const form = new FormData()
      form.append('file', file, 'audio.webm')
      form.append('session_id', session_id)
      const res = await fetch(`${API_BASE}/voice/transcribe`, { method: 'POST', body: form })
      if (!res.ok) throw new ApiError(res.status, await res.text())
      return res.json()
    },
    interrupt: () => request<{ status: string }>('/voice/interrupt', {
      method: 'POST',
    }),
  },

  project: {
    set: (session_id: string, project: string) => request<{ session_id: string; project: string }>('/project/set', {
      method: 'POST',
      body: JSON.stringify({ session_id, project }),
    }),
  },

  context: {
    aggregated: (session_id: string, force = false) =>
      request<ContextResponse>(`/context/aggregated/${session_id}?force=${force}`),
  },

  work: {
    addTask: (session_id: string, task: string) => request<{ session_id: string; task: string }>('/work/task/add', {
      method: 'POST',
      body: JSON.stringify({ session_id, task }),
    }),
    context: (session_id: string) => request<WorkContextResponse>(`/work/context/${session_id}`),
    updateContext: (session_id: string, updates: Record<string, unknown>) =>
      request<{ session_id: string }>('/work/context/update', {
        method: 'POST',
        body: JSON.stringify({ session_id, updates }),
      }),
    scratchpad: {
      save: (session_id: string, content: string) =>
        request<{ session_id: string }>('/work/scratchpad/save', {
          method: 'POST',
          body: JSON.stringify({ session_id, content }),
        }),
      get: (session_id: string) => request<ScratchpadResponse>(`/work/scratchpad/${session_id}`),
    },
    tasks: (session_id: string) => request<WorkTasksResponse>(`/work/tasks/${session_id}`),
    sessions: () => request<{ sessions: any[] }>('/work/sessions'),
  },

  preferences: {
    store: (key: string, value: unknown, category?: string, source?: string) =>
      request<{ key: string }>('/preference/store', {
        method: 'POST',
        body: JSON.stringify({ key, value, category, source }),
      }),
    get: (key: string) => request<{ key: string; entry: PreferenceEntry | null }>(`/preference/${key}`),
    getAll: (category?: string) =>
      request<PreferencesResponse>(`/preferences${category ? `?category=${encodeURIComponent(category)}` : ''}`),
  },

  permissions: {
    request: (payload: PermissionRequestPayload) =>
      request<PermissionResponse>('/permission/request', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    grant: (id: string) => request<{ id: string; status: string }>('/permission/grant', {
      method: 'POST',
      body: JSON.stringify({ id }),
    }),
    deny: (id: string) => request<{ id: string; status: string }>('/permission/deny', {
      method: 'POST',
      body: JSON.stringify({ id }),
    }),
    history: () => request<{ history: PermissionResponse[] }>('/permission/history'),
    patterns: () => request<{ patterns: string[] }>('/permission/patterns'),
    pending: () => request<{ pending: PermissionResponse[] }>('/permission/pending'),
    addAutoApprove: (pattern: string) => request<{ pattern: string; status: string }>('/permission/auto-approve', {
      method: 'POST',
      body: JSON.stringify({ pattern }),
    }),
    removeAutoApprove: (pattern: string) => request<{ pattern: string; status: string }>(`/permission/auto-approve?pattern=${encodeURIComponent(pattern)}`, {
      method: 'DELETE',
    }),
  },

  explain: {
    log: (payload: ExplainLogRequest) =>
      request<{ action: string }>('/memory/explain/log', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
    query: (payload: { decision_id?: string; action?: string; limit?: number }) =>
      request<{ records: unknown[] }>('/memory/explain/query', {
        method: 'POST',
        body: JSON.stringify(payload),
      }),
  },

  productivity: {
    patterns: () => request<{ patterns: ProductivityPattern[] }>('/productivity/patterns'),
    suggestions: (status?: string) =>
      request<{ suggestions: ProductivitySuggestion[] }>(
        `/productivity/suggestions${status ? `?status=${encodeURIComponent(status)}` : ''}`
      ),
    accept: (suggestion_id: string) => request<{ status: string }>('/productivity/suggestion/accept', {
      method: 'POST',
      body: JSON.stringify({ suggestion_id }),
    }),
    dismiss: (suggestion_id: string) => request<{ status: string }>('/productivity/suggestion/dismiss', {
      method: 'POST',
      body: JSON.stringify({ suggestion_id }),
    }),
  },

  system: {
    profile: () => request<SystemProfile>('/system/profile'),
    stats: () => request<SystemStats>('/stats/system'),
    logs: (level?: string, limit = 100) =>
      request<{ logs: LogRecord[] }>(
        `/logs?limit=${limit}${level ? `&level=${encodeURIComponent(level)}` : ''}`
      ),
  },

  state: () => request<StateResponse>('/state'),
}

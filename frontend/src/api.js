const BASE = '/api';

let accessToken = null;
let onAuthError = null;

export function setToken(token) {
  accessToken = token;
}

export function getToken() {
  return accessToken;
}

export function setAuthErrorHandler(handler) {
  onAuthError = handler;
}

async function request(path, options = {}) {
  const isAuthenticatedRequest = Boolean(accessToken && !options.noAuth);
  const headers = {
    ...(options.headers || {}),
  };

  if (accessToken && !options.noAuth) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (res.status === 401 && onAuthError && isAuthenticatedRequest) {
    onAuthError();
    throw new Error('Unauthorized');
  }

  if (res.status === 204) return null;

  const contentType = res.headers.get('content-type') || '';
  let data;
  if (contentType.includes('application/json')) {
    data = await res.json();
  } else {
    const text = await res.text();
    data = text ? { detail: text.slice(0, 500) } : {};
  }

  if (!res.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map(item => item.msg || String(item)).join('; ')
      : data.detail;
    const error = new Error(detail || `Request failed: ${res.status}`);
    error.status = res.status;
    throw error;
  }

  return data;
}

// Auth
export const auth = {
  login: (email, password) =>
    request('/auth/login', {
      method: 'POST',
      body: { email, password },
      noAuth: true,
    }),
  refresh: () =>
    request('/auth/refresh', { method: 'POST', noAuth: true }),

  needsSetup: () =>
    request('/auth/needs-setup', { noAuth: true }),
  setup: (email, password, displayName) =>
    request('/auth/setup', {
      method: 'POST',
      body: { email, password, display_name: displayName },
      noAuth: true,
    }),
  logout: () =>
    request('/auth/logout', { method: 'POST' }),
  me: () =>
    request('/auth/me'),
  changePassword: (currentPassword, newPassword) =>
    request('/auth/change-password', {
      method: 'POST',
      body: {
        current_password: currentPassword,
        new_password: newPassword,
      },
    }),
  listUsers: () =>
    request('/auth/users'),
  createUser: (data) =>
    request('/auth/users', { method: 'POST', body: data }),
  updateUser: (id, data) =>
    request(`/auth/users/${id}`, { method: 'PATCH', body: data }),
};

// Engagements
export const engagements = {
  list: () =>
    request('/engagements'),
  get: (id) =>
    request(`/engagements/${id}`),
  create: (data) =>
    request('/engagements', { method: 'POST', body: data }),
  update: (id, data) =>
    request(`/engagements/${id}`, { method: 'PUT', body: data }),
  delete: (id) =>
    request(`/engagements/${id}`, { method: 'DELETE' }),
  analytics: () =>
    request('/engagements/analytics'),
};

// Findings
export const findings = {
  list: (engId) =>
    request(`/engagements/${engId}/findings`),
  create: (engId, data) =>
    request(`/engagements/${engId}/findings`, { method: 'POST', body: data }),
  update: (engId, findingId, data) =>
    request(`/engagements/${engId}/findings/${findingId}`, { method: 'PUT', body: data }),
  delete: (engId, findingId) =>
    request(`/engagements/${engId}/findings/${findingId}`, { method: 'DELETE' }),
  bulk: (engId, findingIds, action, value = null) =>
    request(`/engagements/${engId}/findings/bulk`, {
      method: 'POST',
      body: { finding_ids: findingIds, action, value },
    }),
};

// Analysis
export const analysis = {
  listScans: (engId) =>
    request(`/engagements/${engId}/scans`),
  uploadScan: (engId, file, scanType) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/engagements/${engId}/upload-scan?scan_type=${scanType}`, {
      method: 'POST',
      body: form,
    });
  },
  deleteScan: (engId, scanId) =>
    request(`/engagements/${engId}/scans/${scanId}`, { method: 'DELETE' }),
  run: (engId) =>
    request(`/engagements/${engId}/analyze`, { method: 'POST' }),
  correlate: (engId) =>
    request(`/engagements/${engId}/correlate`, { method: 'POST' }),
};

// Attack Paths
export const attackPaths = {
  list: (engId) =>
    request(`/engagements/${engId}/attack-paths`),
  generate: (engId) =>
    request(`/engagements/${engId}/attack-paths`, { method: 'POST' }),
  clear: (engId) =>
    request(`/engagements/${engId}/attack-paths`, { method: 'DELETE' }),
};

// Reports
export const reports = {
  list: (engId) =>
    request(`/engagements/${engId}/reports`),
  generate: (engId, format = 'md', templateId = null, useAI = false) => {
    let url = `/engagements/${engId}/reports?format=${format}&use_ai=${useAI}`;
    if (templateId) url += `&template_id=${templateId}`;
    return request(url, { method: 'POST' });
  },
  delete: (reportId) =>
    request(`/reports/${reportId}`, { method: 'DELETE' }),
  download: async (reportId, reportFormat, reportTitle) => {
    const ext = reportFormat || 'md';
    const safeName = (reportTitle || 'report').replace(/[^a-zA-Z0-9 _-]/g, '');
    const url = `/api/reports/${reportId}/download`;
    // Fetch as blob and save via object URL
    const res = await fetch(url, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      credentials: 'include',
    });
    if (!res.ok) throw new Error('Download failed');
    const blob = await res.blob();
    // Create a File from the blob and use saveAs-style approach
    const file = new File([blob], `${safeName}.${ext}`, { type: blob.type });
    // Try navigator.msSaveOrOpenBlob (IE/Edge legacy) 
    if (window.navigator && window.navigator.msSaveOrOpenBlob) {
      window.navigator.msSaveOrOpenBlob(file, `${safeName}.${ext}`);
      return;
    }
    // Try showSaveFilePicker (modern browsers)
    if (window.showSaveFilePicker) {
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: `${safeName}.${ext}`,
          types: [{ accept: { 'application/octet-stream': [`.${ext}`] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        return;
      } catch (e) {
        if (e.name === 'AbortError') return;
      }
    }
    // Fallback: blob URL + anchor click
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `${safeName}.${ext}`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(blobUrl); }, 1000);
  },
};

// System
export const system = {
  health: () =>
    request('/health', { noAuth: true }),
  versionCheck: () =>
    request('/version-check'),
  diagnostics: () =>
    request('/system/diagnostics'),
  listBackups: () =>
    request('/system/backups'),
  createBackup: () =>
    request('/system/backups', { method: 'POST' }),
  deleteBackup: (filename) =>
    request(`/system/backups/${encodeURIComponent(filename)}`, { method: 'DELETE' }),
  downloadBackup: async (filename) => {
    const res = await fetch(`/api/system/backups/${encodeURIComponent(filename)}`, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      credentials: 'include',
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Backup download failed');
    }
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = blobUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    setTimeout(() => {
      document.body.removeChild(anchor);
      URL.revokeObjectURL(blobUrl);
    }, 1000);
  },
};

// Evidence Attachments
export const evidence = {
  list: (engId, findingId) =>
    request(`/engagements/${engId}/findings/${findingId}/evidence`),
  upload: (engId, findingId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/engagements/${engId}/findings/${findingId}/evidence`, {
      method: 'POST',
      body: form,
    });
  },
  delete: (engId, findingId, attachmentId) =>
    request(`/engagements/${engId}/findings/${findingId}/evidence/${attachmentId}`, { method: 'DELETE' }),
  objectUrl: async (url) => {
    const res = await fetch(url, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      credentials: 'include',
    });
    if (!res.ok) throw new Error('Unable to load evidence file');
    return URL.createObjectURL(await res.blob());
  },
};

// Settings / Custom Prompts
export const appSettings = {
  getPrompts: () =>
    request('/settings/prompts'),
  updatePrompt: (key, value) =>
    request(`/settings/prompts/${key}`, { method: 'PUT', body: { value } }),
  resetPrompt: (key) =>
    request(`/settings/prompts/${key}/reset`, { method: 'POST' }),
  getProvider: () =>
    request('/settings/provider'),
  updateProvider: (data) =>
    request('/settings/provider', { method: 'PUT', body: data }),
  localModelStatus: () =>
    request('/settings/local-model/status'),
};

// AI Assistant
export const assistant = {
  chat: (message, engagementId = null) =>
    request('/assistant/chat', {
      method: 'POST',
      body: { message, engagement_id: engagementId },
    }),
};

// Report Templates
export const reportTemplates = {
  list: () => request('/report-templates'),
  create: (formData) =>
    fetch(`${BASE}/report-templates`, {
      method: 'POST',
      headers: accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {},
      credentials: 'include',
      body: formData,
    }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || r.statusText); return r.json(); }),
  update: (id, formData) =>
    fetch(`${BASE}/report-templates/${id}`, {
      method: 'PUT',
      headers: accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {},
      credentials: 'include',
      body: formData,
    }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || r.statusText); return r.json(); }),
  delete: (id) => request(`/report-templates/${id}`, { method: 'DELETE' }),
  logoUrl: (id) => `${BASE}/report-templates/${id}/logo`,
};

// Checklists
export const checklists = {
  methodologies: () =>
    request('/methodologies'),
  list: (engId) =>
    request(`/engagements/${engId}/checklists`),
  populate: (engId, methodology) =>
    request(`/engagements/${engId}/checklists/${methodology}`, { method: 'POST' }),
  update: (engId, itemId, status, notes) =>
    request(`/engagements/${engId}/checklists/${itemId}`, { method: 'PUT', body: { status, notes } }),
  clear: (engId, methodology) =>
    request(`/engagements/${engId}/checklists/${methodology}`, { method: 'DELETE' }),
  progress: (engId) =>
    request(`/engagements/${engId}/checklists/progress`),
};

// Jobs / Tool Runner
export const jobs = {
  presets: () =>
    request('/jobs/presets'),
  list: (engId) =>
    request(`/jobs?engagement_id=${engId}`),
  get: (jobId) =>
    request(`/jobs/${jobId}`),
  create: (engId, tool, command) =>
    request('/jobs', { method: 'POST', body: { engagement_id: engId, tool, command } }),
  stop: (jobId) =>
    request(`/jobs/${jobId}/stop`, { method: 'POST' }),
  delete: (jobId) =>
    request(`/jobs/${jobId}`, { method: 'DELETE' }),
};

// Active Directory
export const ad = {
  listImports: (engId) =>
    request(`/engagements/${engId}/ad/imports`),
  import: (engId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/engagements/${engId}/ad/import`, { method: 'POST', body: form });
  },
  deleteImport: (engId, importId) =>
    request(`/engagements/${engId}/ad/imports/${importId}`, { method: 'DELETE' }),
  summary: (engId) =>
    request(`/engagements/${engId}/ad/summary`),
  paths: (engId) =>
    request(`/engagements/${engId}/ad/paths`),
  analyze: (engId) =>
    request(`/engagements/${engId}/ad/analyze`, { method: 'POST' }),
};

// Export / Import
export const exportImport = {
  export: async (engId) => {
    const res = await fetch(`${BASE}/engagements/${engId}/export`, {
      headers: accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {},
      credentials: 'include',
    });
    if (!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const cd = res.headers.get('content-disposition') || '';
    const filename = cd.split('filename=')[1]?.replace(/"/g, '') || 'engagement_export.json';
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
  import: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/engagements/import', { method: 'POST', body: form });
  },
};

// Knowledge Base
export const knowledge = {
  stats: () => request('/knowledge/stats'),
  list: (params = '') => request(`/knowledge${params ? '?' + params : ''}`),
  trending: (category) => request(`/knowledge/trending${category ? '?category=' + category : ''}`),
  getEntry: (id) => request(`/knowledge/entries/${id}`),
  updateEntry: (id, data) => request(`/knowledge/entries/${id}`, { method: 'PATCH', body: data }),
  clients: () => request('/knowledge/clients'),
  clientProfile: (name) => request(`/knowledge/clients/${encodeURIComponent(name)}/profile`),
  similar: (engId) => request(`/knowledge/engagements/${engId}/similar`),
  recommendations: (engId) => request(`/knowledge/engagements/${engId}/recommendations`),
  indexEngagement: (engId) => request(`/knowledge/index/${engId}`, { method: 'POST' }),
  indexAll: () => request('/knowledge/index-all', { method: 'POST' }),
};

// Gap Analysis
export const gapAnalysis = {
  run: (engId, methodology = 'ptes') =>
    request(`/engagements/${engId}/gap-analysis?methodology=${methodology}`, { method: 'POST' }),
  methodologies: (engId) =>
    request(`/engagements/${engId}/gap-analysis/methodologies`),
};

// Attack Narratives
export const narratives = {
  generatePaths: (engId) =>
    request(`/engagements/${engId}/narrative/paths`, { method: 'POST' }),
  generateFull: (engId) =>
    request(`/engagements/${engId}/narrative/full`, { method: 'POST' }),
  getPaths: (engId) =>
    request(`/engagements/${engId}/narrative/paths`),
  saveFull: (engId, data) =>
    request(`/engagements/${engId}/narrative/full/save`, { method: 'POST', body: data }),
  getSaved: (engId) =>
    request(`/engagements/${engId}/narrative/full`),
  deleteFull: (engId) =>
    request(`/engagements/${engId}/narrative/full`, { method: 'DELETE' }),
};


const BASE = '/api';

async function request(path, options = {}) {
  const headers = {
    ...(options.headers || {}),
  };

  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.body);
  }

  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  });

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
  history: (engId, findingId) =>
    request(`/engagements/${engId}/findings/${findingId}/history`),
  duplicateCheck: (engId, title, affectedHosts = '') =>
    request(`/engagements/${engId}/findings/duplicate-check`, {
      method: 'POST',
      body: { title, affected_hosts: affectedHosts || null },
    }),
};

// Analysis
export const analysis = {
  listScans: (engId) =>
    request(`/engagements/${engId}/scans`),
  preview: (engId, scanIds = null) =>
    request(`/engagements/${engId}/analysis-preview`, {
      method: 'POST',
      ...(scanIds ? { body: { scan_ids: scanIds } } : {}),
    }),
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
  run: (engId, scanIds = null) =>
    request(`/engagements/${engId}/analyze`, {
      method: 'POST',
      ...(scanIds ? { body: { scan_ids: scanIds } } : {}),
    }),
  listDrafts: (engId, status = 'pending') =>
    request(`/engagements/${engId}/ai-drafts?status=${encodeURIComponent(status)}`),
  acceptDraft: (engId, draftId, edits = null) =>
    request(`/engagements/${engId}/ai-drafts/${draftId}/accept`, {
      method: 'POST',
      ...(edits ? { body: edits } : {}),
    }),
  rejectDraft: (engId, draftId) =>
    request(`/engagements/${engId}/ai-drafts/${draftId}/reject`, { method: 'POST' }),
  reviewDrafts: (engId, draftIds, action) =>
    request(`/engagements/${engId}/ai-drafts/bulk`, {
      method: 'POST',
      body: { draft_ids: draftIds, action },
    }),
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
    request('/health'),
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

// Repeatable assessment workflow
export const workflow = {
  templates: (engId) => request(`/engagements/${engId}/workflow/templates`),
  retestQueue: (engId) => request(`/engagements/${engId}/retest-queue`),
  retestOverview: (engId) => request(`/engagements/${engId}/retest-overview`),
  readiness: (engId) => request(`/engagements/${engId}/report-readiness`),
  activity: (engId, limit = 20) => request(`/engagements/${engId}/activity?limit=${limit}`),
  search: (engId, query, limit = 100) =>
    request(`/engagements/${engId}/search?q=${encodeURIComponent(query)}&limit=${limit}`),
  downloadFindingsCsv: async (engId, redactSensitive = true) => {
    const res = await fetch(`/api/engagements/${engId}/findings.csv?redact_sensitive=${redactSensitive}`);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Findings CSV export failed');
    const blob = await res.blob();
    const disposition = res.headers.get('content-disposition') || '';
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'findings.csv';
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    setTimeout(() => {
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    }, 1000);
  },
  assets: (engId) => request(`/engagements/${engId}/assets`),
  listSnapshots: (engId) => request(`/engagements/${engId}/scan-snapshots`),
  createSnapshot: (engId, label, scanIds) =>
    request(`/engagements/${engId}/scan-snapshots`, {
      method: 'POST',
      body: { label, scan_ids: scanIds },
    }),
  compareSnapshot: (engId, snapshotId) =>
    request(`/engagements/${engId}/scan-snapshots/${snapshotId}/comparison`),
  acceptObservation: (engId, snapshotId, fingerprint) =>
    request(`/engagements/${engId}/scan-snapshots/${snapshotId}/observations/${fingerprint}/finding`, {
      method: 'POST',
    }),
  downloadSarif: async (engId, redactSensitive = false) => {
    const res = await fetch(`${BASE}/engagements/${engId}/findings.sarif?redact_sensitive=${redactSensitive}`);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'SARIF export failed');
    const blob = await res.blob();
    const disposition = res.headers.get('content-disposition') || '';
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'breachwright-findings.sarif';
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    setTimeout(() => {
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    }, 1000);
  },
};

export const assessmentTemplates = {
  list: () => request('/assessment-templates'),
  methodologies: () => request('/assessment-templates/methodologies'),
  create: (data) => request('/assessment-templates', { method: 'POST', body: data }),
  update: (key, data) => request(`/assessment-templates/${key}`, { method: 'PUT', body: data }),
  delete: (key) => request(`/assessment-templates/${key}`, { method: 'DELETE' }),
  import: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/assessment-templates/import', { method: 'POST', body: form });
  },
  export: async (key) => {
    const res = await fetch(`${BASE}/assessment-templates/${key}/export`);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Template export failed');
    const blob = await res.blob();
    const disposition = res.headers.get('content-disposition') || '';
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'assessment-template.json';
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    setTimeout(() => {
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    }, 1000);
  },
};

export const findingTemplates = {
  list: () => request('/finding-templates'),
  create: (data) => request('/finding-templates', { method: 'POST', body: data }),
  update: (id, data) => request(`/finding-templates/${id}`, { method: 'PUT', body: data }),
  delete: (id) => request(`/finding-templates/${id}`, { method: 'DELETE' }),
  import: (file) => {
    const form = new FormData();
    form.append('file', file);
    return request('/finding-templates/import', { method: 'POST', body: form });
  },
  export: async (id) => {
    const res = await fetch(`${BASE}/finding-templates/${id}/export`);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Finding template export failed');
    const blob = await res.blob();
    const disposition = res.headers.get('content-disposition') || '';
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'finding-template.json';
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    setTimeout(() => {
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    }, 1000);
  },
};

export const evidenceNotebook = {
  list: (engId) => request(`/engagements/${engId}/notebook`),
  create: (engId, data) => request(`/engagements/${engId}/notebook`, { method: 'POST', body: data }),
  update: (engId, noteId, data) => request(`/engagements/${engId}/notebook/${noteId}`, { method: 'PUT', body: data }),
  promote: (engId, noteId, data) => request(`/engagements/${engId}/notebook/${noteId}/finding`, { method: 'POST', body: data }),
  delete: (engId, noteId) => request(`/engagements/${engId}/notebook/${noteId}`, { method: 'DELETE' }),
  upload: (engId, noteId, file) => {
    const form = new FormData();
    form.append('file', file);
    return request(`/engagements/${engId}/notebook/${noteId}/attachments`, { method: 'POST', body: form });
  },
  deleteAttachment: (engId, noteId, attachmentId) =>
    request(`/engagements/${engId}/notebook/${noteId}/attachments/${attachmentId}`, { method: 'DELETE' }),
  objectUrl: async (url) => {
    const res = await fetch(url);
    if (!res.ok) throw new Error('Unable to load notebook attachment');
    return URL.createObjectURL(await res.blob());
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
      body: formData,
    }).then(async r => { if (!r.ok) throw new Error((await r.json()).detail || r.statusText); return r.json(); }),
  update: (id, formData) =>
    fetch(`${BASE}/report-templates/${id}`, {
      method: 'PUT',
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
  saveToNotebook: (jobId, data = {}) =>
    request(`/jobs/${jobId}/notebook`, { method: 'POST', body: data }),
  addToScans: (jobId) =>
    request(`/jobs/${jobId}/scan`, { method: 'POST' }),
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
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Export failed: ${res.status}`);
    }
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


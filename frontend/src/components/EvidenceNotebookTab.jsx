import { useCallback, useEffect, useMemo, useState } from 'react';
import { BookOpen, Download, Edit3, FileText, Paperclip, Plus, Search, Trash2 } from 'lucide-react';

import { evidenceNotebook as notebookApi } from '../api';
import { EmptyState, Modal, SectionHeader, Spinner } from './UI';


const EMPTY_NOTE = { title: '', body: '', asset: '', tags: '' };


function humanSize(bytes) {
  if (!Number.isFinite(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}


export default function EvidenceNotebookTab({ engId, toast, onFindingsChanged, onOpenFindings }) {
  const [notebook, setNotebook] = useState({ notes: [], total: 0, truncated: false });
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_NOTE);
  const [saving, setSaving] = useState(false);
  const [uploadingNoteId, setUploadingNoteId] = useState(null);
  const [promoting, setPromoting] = useState(null);
  const [creatingFinding, setCreatingFinding] = useState(false);
  const [findingForm, setFindingForm] = useState({
    title: '', description: '', severity: 'info', cvss_score: '',
    affected_hosts: '', evidence: '', remediation: '',
  });

  const load = useCallback(async () => {
    const data = await notebookApi.list(engId);
    setNotebook(data);
    return data;
  }, [engId]);

  useEffect(() => {
    load()
      .catch(err => toast({ message: `Evidence notebook could not be loaded: ${err.message}`, type: 'error' }))
      .finally(() => setLoading(false));
  }, [load, toast]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return notebook.notes;
    return notebook.notes.filter(note => [
      note.title,
      note.body,
      note.asset,
      ...(note.tags || []),
      ...(note.attachments || []).map(attachment => attachment.filename),
    ].some(value => String(value || '').toLowerCase().includes(needle)));
  }, [notebook.notes, query]);

  const openNew = () => {
    setEditing({ id: null });
    setForm(EMPTY_NOTE);
  };

  const openEdit = (note) => {
    setEditing(note);
    setForm({
      title: note.title || '',
      body: note.body || '',
      asset: note.asset || '',
      tags: (note.tags || []).join(', '),
    });
  };

  const save = async (event) => {
    event.preventDefault();
    setSaving(true);
    const tags = [...new Map(
      form.tags.split(',').map(tag => tag.trim()).filter(Boolean).map(tag => [tag.toLowerCase(), tag])
    ).values()];
    const body = {
      title: form.title,
      body: form.body || null,
      asset: form.asset || null,
      tags,
    };
    try {
      if (editing.id) {
        await notebookApi.update(engId, editing.id, body);
        toast({ message: `Evidence note "${body.title}" updated`, type: 'success' });
      } else {
        await notebookApi.create(engId, body);
        toast({ message: `Evidence note "${body.title}" added`, type: 'success' });
      }
      await load();
      setEditing(null);
      setForm(EMPTY_NOTE);
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const deleteNote = async (note) => {
    if (!window.confirm(`Delete evidence note "${note.title}" and its attachments?`)) return;
    try {
      await notebookApi.delete(engId, note.id);
      setNotebook(previous => ({
        ...previous,
        total: Math.max(0, previous.total - 1),
        notes: previous.notes.filter(item => item.id !== note.id),
      }));
      toast({ message: `Evidence note "${note.title}" deleted`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    }
  };

  const uploadAttachment = async (note, event) => {
    const file = event.target.files[0];
    event.target.value = '';
    if (!file) return;
    setUploadingNoteId(note.id);
    try {
      const attachment = await notebookApi.upload(engId, note.id, file);
      setNotebook(previous => ({
        ...previous,
        notes: previous.notes.map(item => item.id === note.id
          ? { ...item, attachments: [attachment, ...(item.attachments || [])] }
          : item),
      }));
      toast({ message: `Attached ${attachment.filename}`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setUploadingNoteId(null);
    }
  };

  const downloadAttachment = async (attachment) => {
    try {
      const url = await notebookApi.objectUrl(attachment.url);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = attachment.filename;
      document.body.appendChild(anchor);
      anchor.click();
      setTimeout(() => {
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
      }, 1000);
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    }
  };

  const deleteAttachment = async (note, attachment) => {
    try {
      await notebookApi.deleteAttachment(engId, note.id, attachment.id);
      setNotebook(previous => ({
        ...previous,
        notes: previous.notes.map(item => item.id === note.id
          ? { ...item, attachments: item.attachments.filter(file => file.id !== attachment.id) }
          : item),
      }));
      toast({ message: `Attachment ${attachment.filename} deleted`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    }
  };

  const openPromote = (note) => {
    setPromoting(note);
    setFindingForm({
      title: note.title || '',
      description: note.body || '',
      severity: 'info',
      cvss_score: '',
      affected_hosts: note.asset || '',
      evidence: note.body || '',
      remediation: '',
    });
  };

  const promoteToFinding = async (event) => {
    event.preventDefault();
    setCreatingFinding(true);
    try {
      const finding = await notebookApi.promote(engId, promoting.id, {
        ...findingForm,
        cvss_score: findingForm.cvss_score === '' ? null : parseFloat(findingForm.cvss_score),
      });
      await Promise.all([load(), onFindingsChanged()]);
      setPromoting(null);
      toast({ message: `Reviewed note added to Findings as "${finding.title}"`, type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    } finally {
      setCreatingFinding(false);
    }
  };

  if (loading) {
    return <div className="flex justify-center py-16"><Spinner className="w-6 h-6 themed-text-muted" /></div>;
  }

  return (
    <div>
      <SectionHeader
        title="Evidence Notebook"
        description="Capture raw testing notes and files before they become formal findings. Everything stays in this local workspace."
        action={<button className="btn-primary flex items-center gap-2 text-sm" onClick={openNew}><Plus size={14} /> Add Note</button>}
      />

      {notebook.notes.length > 0 && (
        <div className="relative mb-4">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 themed-text-muted" />
          <input className="input-field pl-9 text-sm" value={query}
            onChange={event => setQuery(event.target.value)}
            placeholder="Filter notes, assets, tags, and attachment names" aria-label="Filter evidence notebook" />
        </div>
      )}

      {notebook.truncated && (
        <p className="text-xs text-yellow-500 mb-4">Showing the 500 most recently updated notes out of {notebook.total}.</p>
      )}

      {notebook.notes.length === 0 ? (
        <EmptyState icon={BookOpen} title="No evidence notes"
          description="Keep investigation notes, raw HTTP exchanges, HAR files, screenshots, and supporting files together before deciding what becomes a finding."
          action={<button className="btn-primary flex items-center gap-2" onClick={openNew}><Plus size={16} /> Add Note</button>} />
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center text-sm themed-text-muted">No evidence notes match this filter.</div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-4">
          {filtered.map(note => (
            <article key={note.id} className="card p-4 flex flex-col gap-3">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-semibold themed-text-primary break-words">{note.title}</h3>
                  <div className="flex flex-wrap items-center gap-2 mt-1 text-xs themed-text-muted">
                    {note.asset && <span className="font-mono">{note.asset}</span>}
                    {note.source_type === 'tool_runner_job' && <span className="badge border text-cyan-400">Tool Runner</span>}
                    {(note.tags || []).map(tag => <span key={tag} className="badge border themed-text-muted">{tag}</span>)}
                  </div>
                </div>
                {note.finding_id ? (
                  <button className="btn-secondary text-xs shrink-0" onClick={onOpenFindings}>In Findings</button>
                ) : (
                  <button className="btn-secondary text-xs shrink-0" onClick={() => openPromote(note)}>Create Finding</button>
                )}
                {!note.finding_id && <>
                  <button className="btn-ghost p-1" title="Edit evidence note" onClick={() => openEdit(note)}><Edit3 size={14} /></button>
                  <button className="btn-ghost p-1 text-red-400" title="Delete evidence note" onClick={() => deleteNote(note)}><Trash2 size={14} /></button>
                </>}
              </div>
              {note.body && (
                <pre className="text-xs themed-text-secondary whitespace-pre-wrap break-words rounded p-3 max-h-56 overflow-auto"
                  style={{ backgroundColor: 'var(--bg-800)' }}>{note.body}</pre>
              )}
              <div className="mt-auto">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="text-xs font-mono themed-text-muted uppercase tracking-wider">
                    Attachments ({(note.attachments || []).length})
                  </span>
                  {note.finding_id ? (
                    <span className="text-[10px] themed-text-muted">Locked provenance</span>
                  ) : (
                    <label className="btn-ghost flex items-center gap-1 text-xs cursor-pointer">
                      {uploadingNoteId === note.id ? <Spinner className="w-3 h-3" /> : <Paperclip size={12} />} Attach
                      <input type="file" className="hidden" disabled={uploadingNoteId === note.id}
                        accept="image/*,.pdf,.txt,.http,.req,.resp,.md,.csv,.json,.har"
                        onChange={event => uploadAttachment(note, event)} />
                    </label>
                  )}
                </div>
                {(note.attachments || []).length > 0 && (
                  <div className="space-y-2">
                    {note.attachments.map(attachment => (
                      <div key={attachment.id} className="rounded border p-2 flex items-center gap-2" style={{ borderColor: 'var(--border)' }}>
                        <FileText size={14} className="themed-text-muted shrink-0" />
                        <button className="text-left flex-1 min-w-0 text-xs themed-text-secondary hover:themed-text-primary truncate"
                          title={`Download ${attachment.filename}`} onClick={() => downloadAttachment(attachment)}>
                          {attachment.filename}
                        </button>
                        <span className="text-[10px] themed-text-muted shrink-0">{humanSize(attachment.file_size)}</span>
                        {!note.finding_id && <button className="btn-ghost p-1 text-red-400" title={`Delete ${attachment.filename}`}
                          onClick={() => deleteAttachment(note, attachment)}><Trash2 size={12} /></button>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      <Modal open={!!editing} onClose={() => setEditing(null)} title={editing?.id ? 'Edit Evidence Note' : 'Add Evidence Note'} wide>
        <form className="space-y-4" onSubmit={save}>
          <div>
            <label htmlFor="notebook-title" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Title</label>
            <input id="notebook-title" className="input-field text-sm" value={form.title}
              onChange={event => setForm(previous => ({ ...previous, title: event.target.value }))}
              placeholder="What did you observe?" required autoFocus />
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor="notebook-asset" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Asset</label>
              <input id="notebook-asset" className="input-field text-sm font-mono" value={form.asset}
                onChange={event => setForm(previous => ({ ...previous, asset: event.target.value }))}
                placeholder="host, URL, or service" />
            </div>
            <div>
              <label htmlFor="notebook-tags" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Tags</label>
              <input id="notebook-tags" className="input-field text-sm" value={form.tags}
                onChange={event => setForm(previous => ({ ...previous, tags: event.target.value }))}
                placeholder="http, auth, follow-up" />
            </div>
          </div>
          <div>
            <label htmlFor="notebook-body" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Notes or raw text</label>
            <textarea id="notebook-body" className="input-field text-sm font-mono resize-y" rows={10} value={form.body}
              onChange={event => setForm(previous => ({ ...previous, body: event.target.value }))}
              placeholder="Paste request and response text, test steps, commands, or analyst notes." />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button>
            <button type="submit" className="btn-primary flex items-center gap-2" disabled={saving}>
              {saving && <Spinner className="w-4 h-4" />} {editing?.id ? 'Update Note' : 'Add Note'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={!!promoting} onClose={() => setPromoting(null)} title="Review and Create Finding" wide>
        <form className="space-y-4" onSubmit={promoteToFinding}>
          <p className="text-xs themed-text-muted">Review the note before it becomes a formal finding. The note and attachment identifiers remain linked as provenance.</p>
          <div>
            <label htmlFor="notebook-finding-title" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Title</label>
            <input id="notebook-finding-title" className="input-field text-sm" value={findingForm.title}
              onChange={event => setFindingForm(previous => ({ ...previous, title: event.target.value }))} required autoFocus />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="notebook-finding-severity" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Severity</label>
              <select id="notebook-finding-severity" className="input-field text-sm" value={findingForm.severity}
                onChange={event => setFindingForm(previous => ({ ...previous, severity: event.target.value }))}>
                {['critical', 'high', 'medium', 'low', 'info'].map(severity => <option key={severity} value={severity}>{severity[0].toUpperCase() + severity.slice(1)}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="notebook-finding-cvss" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">CVSS Score</label>
              <input id="notebook-finding-cvss" type="number" min="0" max="10" step="0.1" className="input-field text-sm" value={findingForm.cvss_score}
                onChange={event => setFindingForm(previous => ({ ...previous, cvss_score: event.target.value }))} />
            </div>
          </div>
          <div>
            <label htmlFor="notebook-finding-hosts" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Affected Hosts</label>
            <input id="notebook-finding-hosts" className="input-field text-sm font-mono" value={findingForm.affected_hosts}
              onChange={event => setFindingForm(previous => ({ ...previous, affected_hosts: event.target.value }))} />
          </div>
          <div>
            <label htmlFor="notebook-finding-description" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Description</label>
            <textarea id="notebook-finding-description" rows={3} className="input-field text-sm resize-y" value={findingForm.description}
              onChange={event => setFindingForm(previous => ({ ...previous, description: event.target.value }))} />
          </div>
          <div>
            <label htmlFor="notebook-finding-evidence" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Evidence</label>
            <textarea id="notebook-finding-evidence" rows={3} className="input-field text-sm font-mono resize-y" value={findingForm.evidence}
              onChange={event => setFindingForm(previous => ({ ...previous, evidence: event.target.value }))} />
          </div>
          <div>
            <label htmlFor="notebook-finding-remediation" className="block text-xs font-mono themed-text-muted uppercase tracking-wider mb-1.5">Remediation</label>
            <textarea id="notebook-finding-remediation" rows={3} className="input-field text-sm resize-y" value={findingForm.remediation}
              onChange={event => setFindingForm(previous => ({ ...previous, remediation: event.target.value }))} />
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-secondary" onClick={() => setPromoting(null)}>Cancel</button>
            <button type="submit" className="btn-primary flex items-center gap-2" disabled={creatingFinding}>
              {creatingFinding && <Spinner className="w-4 h-4" />} Create Finding
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}

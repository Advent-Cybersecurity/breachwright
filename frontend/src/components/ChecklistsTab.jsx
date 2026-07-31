import { useState, useEffect } from 'react';
import { checklists as checklistsApi } from '../api';
import { Spinner, Toast } from './UI';
import {
  CheckSquare, Square, Clock, MinusCircle, ChevronDown, ChevronRight,
  Plus, Trash2, ExternalLink, Wrench
} from 'lucide-react';

const STATUS_CONFIG = {
  pending: { label: 'Pending', color: '#71717a', icon: Square },
  in_progress: { label: 'In Progress', color: '#eab308', icon: Clock },
  done: { label: 'Done', color: '#22c55e', icon: CheckSquare },
  na: { label: 'N/A', color: '#3b82f6', icon: MinusCircle },
};

const METH_COLORS = {
  owasp_top10: '#ef4444',
  ptes: '#f97316',
  nist_800_115: '#3b82f6',
  network_pentest: '#22c55e',
};

function ProgressBar({ progress }) {
  if (!progress || progress.total === 0) return null;
  const pct = Math.round(((progress.done + progress.na) / progress.total) * 100);

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--bg-600)' }}>
        <div className="h-full rounded-full transition-all" style={{
          width: `${pct}%`,
          background: pct === 100 ? '#22c55e' : 'var(--accent-red)',
        }} />
      </div>
      <span className="text-xs font-mono themed-text-muted shrink-0">{pct}%</span>
      <span className="text-xs themed-text-muted shrink-0">
        {progress.done}/{progress.total}
      </span>
    </div>
  );
}

function ChecklistItemRow({ item, onUpdate }) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(item.notes || '');
  const [saving, setSaving] = useState(false);
  const statusConf = STATUS_CONFIG[item.status] || STATUS_CONFIG.pending;

  const cycleStatus = async () => {
    const order = ['pending', 'in_progress', 'done', 'na'];
    const next = order[(order.indexOf(item.status) + 1) % order.length];
    setSaving(true);
    try {
      await onUpdate(item.id, next, notes);
    } finally {
      setSaving(false);
    }
  };

  const saveNotes = async () => {
    setSaving(true);
    try {
      await onUpdate(item.id, item.status, notes);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border-b" style={{ borderColor: 'color-mix(in srgb, var(--border) 40%, transparent)' }}>
      <div className="flex items-center gap-3 px-4 py-2.5">
        {/* Status toggle */}
        <button onClick={cycleStatus} disabled={saving}
          className="shrink-0 transition-colors" title={`Status: ${statusConf.label} (click to cycle)`}>
          <statusConf.icon size={18} style={{ color: statusConf.color }} />
        </button>

        {/* Item text */}
        <button onClick={() => setExpanded(!expanded)} className="flex-1 text-left min-w-0">
          <span className="text-sm themed-text-primary"
            style={{ textDecoration: item.status === 'done' ? 'line-through' : 'none',
                     opacity: item.status === 'na' ? 0.5 : item.status === 'done' ? 0.7 : 1 }}>
            {item.item}
          </span>
        </button>

        {/* Tools badge */}
        {item.tools && (
          <span className="text-[10px] font-mono px-2 py-0.5 rounded shrink-0 hidden sm:inline-block"
            style={{ backgroundColor: 'var(--bg-600)', color: 'var(--text-muted)' }}>
            {item.tools.split(',')[0].trim()}
          </span>
        )}

        {/* Expand chevron */}
        <button onClick={() => setExpanded(!expanded)} className="shrink-0 themed-text-muted">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      </div>

      {expanded && (
        <div className="px-4 pb-3 pl-11 space-y-2">
          {item.description && (
            <p className="text-xs themed-text-secondary">{item.description}</p>
          )}

          <div className="flex flex-wrap gap-4 text-xs">
            {item.tools && (
              <div>
                <span className="font-mono themed-text-muted uppercase text-[10px]">Tools: </span>
                <span className="themed-text-secondary">{item.tools}</span>
              </div>
            )}
            {item.techniques && (
              <div>
                <span className="font-mono themed-text-muted uppercase text-[10px]">Techniques: </span>
                <span className="themed-text-secondary">{item.techniques}</span>
              </div>
            )}
          </div>

          {item.reference_url && (
            <a href={item.reference_url} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs transition-colors"
              style={{ color: 'var(--accent-red)' }}>
              <ExternalLink size={10} /> Reference
            </a>
          )}

          {/* Notes */}
          <div className="flex gap-2 mt-1">
            <input className="input-field text-xs flex-1" value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={saveNotes}
              placeholder="Add notes..."
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default function ChecklistsTab({ engId, toast }) {
  const [methodologies, setMethodologies] = useState({});
  const [items, setItems] = useState([]);
  const [progress, setProgress] = useState({});
  const [loading, setLoading] = useState(true);
  const [expandedCategories, setExpandedCategories] = useState(new Set());

  useEffect(() => {
    (async () => {
      try {
        const [meths, checklist, prog] = await Promise.all([
          checklistsApi.methodologies(),
          checklistsApi.list(engId),
          checklistsApi.progress(engId),
        ]);
        setMethodologies(meths);
        setItems(checklist);
        setProgress(prog);
        // Auto-expand first category of each methodology
        const cats = new Set();
        const seen = new Set();
        checklist.forEach(i => {
          const key = `${i.methodology}:${i.category}`;
          if (!seen.has(i.methodology)) { cats.add(key); seen.add(i.methodology); }
        });
        setExpandedCategories(cats);
      } catch (e) {
        toast({ message: `Could not load checklists: ${e.message}`, type: 'error' });
      }
      finally { setLoading(false); }
    })();
  }, [engId]);

  const handlePopulate = async (methKey) => {
    try {
      await checklistsApi.populate(engId, methKey);
      const [checklist, prog] = await Promise.all([
        checklistsApi.list(engId),
        checklistsApi.progress(engId),
      ]);
      setItems(checklist);
      setProgress(prog);
      toast({ message: `${methodologies[methKey]?.name} checklist added`, type: 'success' });
    } catch (err) {
      const msg = err?.detail || err.message;
      toast({ message: typeof msg === 'string' ? msg : 'Already exists', type: 'error' });
    }
  };

  const handleClear = async (methKey) => {
    const confirmed = window.confirm(`Clear all ${methodologies[methKey]?.name} checklist items?`);
    if (!confirmed) return;
    try {
      await checklistsApi.clear(engId, methKey);
      setItems(prev => prev.filter(i => i.methodology !== methKey));
      setProgress(prev => { const n = { ...prev }; delete n[methKey]; return n; });
      toast({ message: 'Checklist cleared', type: 'success' });
    } catch (err) {
      toast({ message: err.message, type: 'error' });
    }
  };

  const handleUpdateItem = async (itemId, status, notes) => {
    try {
      await checklistsApi.update(engId, itemId, status, notes);
      setItems(prev => prev.map(i => i.id === itemId ? { ...i, status, notes } : i));
      const prog = await checklistsApi.progress(engId);
      setProgress(prog);
    } catch (err) {
      toast({ message: `Could not update checklist: ${err.message}`, type: 'error' });
    }
  };

  const toggleCategory = (key) => {
    setExpandedCategories(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>;

  // Group items by methodology, then category
  const activeMethods = [...new Set(items.map(i => i.methodology))];

  // Available but not yet added
  const availableMethods = Object.entries(methodologies).filter(
    ([key]) => !activeMethods.includes(key)
  );

  return (
    <div>
      {/* Add methodology */}
      {availableMethods.length > 0 && (
        <div className="card p-5 mb-5" style={{ borderStyle: 'dashed' }}>
          <div className="flex items-center gap-2 mb-3">
            <Wrench size={16} className="themed-text-muted" />
            <span className="text-sm font-semibold themed-text-primary">Add Methodology Checklist</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
            {availableMethods.map(([key, meth]) => (
              <button key={key} onClick={() => handlePopulate(key)}
                className="p-3 rounded-md text-left transition-all"
                style={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--bg-500)' }}
                onMouseEnter={e => e.currentTarget.style.borderColor = METH_COLORS[key] || 'var(--accent-red)'}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--bg-500)'}
              >
                <div className="text-xs font-semibold themed-text-primary">{meth.name}</div>
                <div className="text-[10px] themed-text-muted mt-0.5">{meth.item_count} items</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Active checklists */}
      {activeMethods.map(methKey => {
        const methItems = items.filter(i => i.methodology === methKey);
        const categories = [...new Set(methItems.map(i => i.category))];
        const methName = methodologies[methKey]?.name || methKey;
        const methProgress = progress[methKey];

        return (
          <div key={methKey} className="card overflow-hidden mb-5">
            {/* Methodology header */}
            <div className="flex items-center gap-3 px-5 py-4"
              style={{ borderBottom: '1px solid var(--border)', borderLeft: `3px solid ${METH_COLORS[methKey] || '#ef4444'}` }}>
              <div className="flex-1">
                <h3 className="text-sm font-semibold themed-text-primary">{methName}</h3>
                <div className="mt-1.5" style={{ maxWidth: 300 }}>
                  <ProgressBar progress={methProgress} />
                </div>
              </div>
              <button onClick={() => handleClear(methKey)}
                className="themed-text-muted hover:text-red-400 transition-colors p-1" title="Clear checklist">
                <Trash2 size={14} />
              </button>
            </div>

            {/* Categories */}
            {categories.map(cat => {
              const catKey = `${methKey}:${cat}`;
              const catItems = methItems.filter(i => i.category === cat);
              const catDone = catItems.filter(i => i.status === 'done' || i.status === 'na').length;
              const isExpanded = expandedCategories.has(catKey);

              return (
                <div key={catKey}>
                  <button onClick={() => toggleCategory(catKey)}
                    className="w-full flex items-center gap-3 px-5 py-2.5 text-left transition-colors"
                    style={{ backgroundColor: isExpanded ? 'color-mix(in srgb, var(--bg-700) 30%, transparent)' : 'transparent' }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--bg-700) 50%, transparent)'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = isExpanded ? 'color-mix(in srgb, var(--bg-700) 30%, transparent)' : 'transparent'}
                  >
                    {isExpanded ?
                      <ChevronDown size={14} className="themed-text-muted" /> :
                      <ChevronRight size={14} className="themed-text-muted" />
                    }
                    <span className="text-xs font-semibold themed-text-secondary flex-1">{cat}</span>
                    <span className="text-[10px] font-mono themed-text-muted">
                      {catDone}/{catItems.length}
                    </span>
                  </button>

                  {isExpanded && catItems.map(item => (
                    <ChecklistItemRow key={item.id} item={item} onUpdate={handleUpdateItem} />
                  ))}
                </div>
              );
            })}
          </div>
        );
      })}

      {/* Empty state */}
      {activeMethods.length === 0 && availableMethods.length === 0 && (
        <div className="text-center py-12">
          <CheckSquare size={32} className="themed-text-muted mx-auto mb-3" />
          <p className="text-sm themed-text-secondary">No checklists available</p>
        </div>
      )}
    </div>
  );
}

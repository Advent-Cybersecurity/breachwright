import { useState, useEffect, useRef } from 'react';
import { engagements as engApi, assistant as assistantApi, appSettings } from '../api';
import { Toast, Spinner } from '../components/UI';
import { Send, Bot, User, Info, ChevronDown } from 'lucide-react';

function InlineContent({ text }) {
  const parts = text.split(/(\*\*.*?\*\*|`.*?`)/g);
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={index}
          className="px-1 py-0.5 rounded text-xs"
          style={{ background: 'var(--bg-600)', color: '#06b6d4' }}
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

function ChatMessage({ msg }) {
  const isUser = msg.role === 'user';

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
        style={{
          backgroundColor: isUser ? 'rgba(239,68,68,0.15)' : 'rgba(6,182,212,0.15)',
        }}>
        {isUser ?
          <User size={14} style={{ color: 'var(--accent-red)' }} /> :
          <Bot size={14} style={{ color: '#06b6d4' }} />
        }
      </div>
      <div className={`flex-1 max-w-[80%] ${isUser ? 'text-right' : ''}`}>
        <div className="inline-block text-left px-4 py-3 rounded-lg text-sm leading-relaxed"
          style={{
            backgroundColor: isUser ? 'rgba(239,68,68,0.1)' : 'var(--bg-700)',
            border: `1px solid ${isUser ? 'rgba(239,68,68,0.2)' : 'var(--border)'}`,
          }}>
          {/* Render markdown-like content */}
          {msg.content.split('\n').map((line, i) => {
            if (line.startsWith('### ')) {
              return <p key={i} className="font-semibold themed-text-primary mt-2 mb-1">{line.slice(4)}</p>;
            }
            if (line.startsWith('## ')) {
              return <p key={i} className="font-bold themed-text-primary text-base mt-3 mb-1">{line.slice(3)}</p>;
            }
            if (line.startsWith('- ') || line.startsWith('* ')) {
              return <p key={i} className="themed-text-secondary ml-3 my-0.5">{'\u2022 '}{line.slice(2)}</p>;
            }
            if (line.match(/^\d+\.\s/)) {
              return <p key={i} className="themed-text-secondary ml-3 my-0.5">{line}</p>;
            }
            if (line.startsWith('```')) {
              return null;
            }
            if (line.trim() === '') {
              return <div key={i} className="h-2" />;
            }
            return (
              <p key={i} className="themed-text-secondary my-0.5">
                <InlineContent text={line} />
              </p>
            );
          })}
        </div>
        {/* Context labels */}
        {msg.context_used && msg.context_used.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1.5">
            {msg.context_used.map((label, i) => (
              <span key={i} className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                style={{ backgroundColor: 'rgba(6,182,212,0.1)', color: '#06b6d4' }}>
                {label}
              </span>
            ))}
          </div>
        )}
        {msg.citations && msg.citations.length > 0 && (
          <details className="mt-2 text-left">
            <summary className="text-[10px] font-mono themed-text-muted cursor-pointer">
              Evidence sources ({msg.citations.length})
            </summary>
            <div className="flex flex-wrap gap-1 mt-1.5">
              {msg.citations.map(citation => (
                <span key={citation.id} className="text-[10px] font-mono px-1.5 py-0.5 rounded"
                  title={citation.id}
                  style={{ backgroundColor: 'var(--bg-700)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                  [{citation.id}] {citation.label}
                </span>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}

export default function Assistant() {
  const [engagementList, setEngagementList] = useState([]);
  const [selectedEng, setSelectedEng] = useState('');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState(null);
  const [providerConfig, setProviderConfig] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    engApi.list().then(engs => {
      setEngagementList(engs);
      if (engs.length > 0) setSelectedEng(engs[0].id);
    }).catch((err) => {
      setToast({ message: `Could not load engagements: ${err.message}`, type: 'error' });
    });
  }, []);

  useEffect(() => {
    appSettings.getProvider().then(setProviderConfig).catch((err) => {
      setToast({ message: `Could not load AI privacy settings: ${err.message}`, type: 'error' });
    });
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    const msg = input.trim();
    if (!msg || sending) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: msg }]);
    setSending(true);

    try {
      const result = await assistantApi.chat(msg, selectedEng || null);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: result.response,
        context_used: result.context_used,
        citations: result.citations,
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.message}. Make sure your AI provider is configured in Settings.`,
        context_used: [],
      }]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const engName = engagementList.find(e => e.id === selectedEng)?.name;

  return (
    <>
    <div className="animate-fade-in flex flex-col" style={{ height: 'calc(100vh - 64px)' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div>
          <h1 className="text-xl font-semibold themed-text-primary">AI Assistant</h1>
          <p className="text-sm themed-text-muted mt-0.5">Ask questions about your engagements, findings, and scan data</p>
        </div>
      </div>

      {/* Engagement selector */}
      <div className="flex items-center gap-3 mb-4 shrink-0">
        <label htmlFor="assistant-context" className="text-xs font-mono themed-text-muted uppercase tracking-wider">Context:</label>
        <select id="assistant-context" className="input-field text-sm" style={{ maxWidth: 350 }}
          value={selectedEng}
          onChange={(e) => setSelectedEng(e.target.value)}>
          <option value="">All Engagements (general)</option>
          {engagementList.map(eng => (
            <option key={eng.id} value={eng.id}>{eng.name} ({eng.client_name})</option>
          ))}
        </select>
        {selectedEng && (
          <span className="text-xs themed-text-muted">
            Scoped to: <span style={{ color: '#06b6d4' }}>{engName}</span>
          </span>
        )}
      </div>

      {providerConfig && (
        <div className="flex items-start gap-2 rounded px-3 py-2 mb-4 text-xs themed-text-secondary shrink-0"
          style={{ border: '1px solid var(--border)', backgroundColor: 'var(--bg-800)' }} role="status">
          <Info size={14} className="mt-0.5 shrink-0" style={{ color: '#06b6d4' }} />
          <span>
            Provider: <strong className="themed-text-primary">{providerConfig.ai_provider}</strong>
            {' · '}Sensitive-data redaction: <strong className={providerConfig.ai_redact_sensitive_data ? 'text-green-400' : 'text-yellow-400'}>{providerConfig.ai_redact_sensitive_data ? 'on' : 'off'}</strong>
            {' · '}Each message can send bounded context from the selected engagement to this provider.
          </span>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto rounded-lg p-4 mb-4 space-y-4"
        style={{ backgroundColor: 'var(--bg-800)', border: '1px solid var(--border)' }}>

        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
              style={{ backgroundColor: 'rgba(6,182,212,0.1)' }}>
              <Bot size={28} style={{ color: '#06b6d4' }} />
            </div>
            <p className="text-base font-medium themed-text-secondary mb-2">How can I help?</p>
            <p className="text-sm themed-text-muted max-w-md mb-6">
              I have access to your engagement data. Ask about findings, scan results,
              remediation advice, or anything related to your penetration tests.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-lg">
              {[
                'What are the critical findings?',
                'Summarize the scan results',
                'What remediation should I prioritize?',
                'Are there any AD attack paths?',
              ].map((suggestion, i) => (
                <button key={i} onClick={() => { setInput(suggestion); inputRef.current?.focus(); }}
                  className="text-left text-xs px-3 py-2.5 rounded-md transition-colors"
                  style={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--bg-500)', color: 'var(--text-secondary)' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent-red)'; e.currentTarget.style.color = 'var(--text-primary)'; }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--bg-500)'; e.currentTarget.style.color = 'var(--text-secondary)'; }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <ChatMessage key={i} msg={msg} />
        ))}

        {sending && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
              style={{ backgroundColor: 'rgba(6,182,212,0.15)' }}>
              <Bot size={14} style={{ color: '#06b6d4' }} />
            </div>
            <div className="flex items-center gap-2 px-4 py-3 rounded-lg"
              style={{ backgroundColor: 'var(--bg-700)', border: '1px solid var(--border)' }}>
              <Spinner className="w-4 h-4" style={{ color: '#06b6d4' }} />
              <span className="text-sm themed-text-muted">Thinking...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 flex gap-3">
        <div className="flex-1 relative">
          <textarea ref={inputRef}
            aria-label="Assistant message"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={selectedEng ? `Ask about ${engName}...` : 'Ask a question...'}
            rows={1}
            className="input-field text-sm pr-12 resize-none"
            style={{ minHeight: 44, maxHeight: 120 }}
            disabled={sending}
          />
        </div>
        <button
          type="button"
          aria-label="Send message"
          onClick={handleSend}
          disabled={sending || !input.trim()}
          className="btn-primary flex items-center gap-2 self-end"
          style={{ height: 44 }}>
          {sending ? <Spinner className="w-4 h-4" /> : <Send size={16} />}
        </button>
      </div>

      {toast && <Toast {...toast} onDismiss={() => setToast(null)} />}
    </div>
    </>
  );
}

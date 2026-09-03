import { useEffect, useState, useRef } from 'react';
import { askBot, fetchBotTopics, BotResponse } from '@/lib/api';
import { Send, Sparkles, Bot as BotIcon, User } from 'lucide-react';

interface Message {
  role: 'user' | 'bot';
  text: string;
  confident: boolean;
}

export default function Bot() {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [topics, setTopics] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchBotTopics()
      .then(res => {
        setTopics(Array.isArray(res.topics) ? res.topics : []);
      })
      .catch(() => setTopics([]));
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleAsk = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setMessages(prev => [...prev, { role: 'user', text: trimmed, confident: true }]);
    setLoading(true);
    setError('');

    try {
      const res: BotResponse = await askBot(trimmed);
      setMessages(prev => [...prev, { role: 'bot', text: res.answer, confident: res.confident }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to reach the policy bot.';
      setError(msg);
      setMessages(prev => [...prev, { role: 'bot', text: `Error: ${msg}`, confident: false }]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleAsk(query);
    setQuery('');
  };

  return (
    <div className="bot-page">
      <div className="bot-container">
        <div className="bot-header">
          <div className="bot-brand">
            <div className="bot-icon-wrap"><BotIcon size={24} /></div>
            <div>
              <h3 className="bot-title">Policy Intelligence Bot</h3>
              <p className="bot-subtitle">AI-Powered Financial Guide</p>
            </div>
          </div>
        </div>

        <div className="chat-window" ref={scrollRef}>
          {messages.length === 0 && (
            <div className="chat-empty">
              <div className="empty-icon"><Sparkles size={48} color="var(--primary)" /></div>
              <h3 className="chat-empty-title">How can I help you today?</h3>
              <p>Select a common topic or ask a specific question about loans, tax, or payouts.</p>
              <div className="topic-grid">
                {topics.map(t => (
                  <button key={t} onClick={() => handleAsk(t)} className="topic-btn">{t}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={`chat-msg-wrap ${m.role}`}>
              <div className="msg-avatar">
                {m.role === 'user' ? <User size={16} /> : <BotIcon size={16} />}
              </div>
              <div className={`chat-bubble ${m.role === 'bot' && !m.confident ? 'unconfident' : ''}`}>
                {m.text}
              </div>
            </div>
          ))}

          {loading && (
            <div className="chat-msg-wrap bot">
              <div className="msg-avatar"><BotIcon size={16} /></div>
              <div className="chat-bubble loading-bubble">Thinking...</div>
            </div>
          )}
        </div>

        {error && <div className="error-msg" style={{ margin: '0 24px 8px' }}>{error}</div>}

        <form onSubmit={handleSubmit} className="chat-input">
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Type your question here..."
            disabled={loading}
          />
          <button type="submit" disabled={loading || !query.trim()}>
            <Send size={20} />
          </button>
        </form>
      </div>
    </div>
  );
}

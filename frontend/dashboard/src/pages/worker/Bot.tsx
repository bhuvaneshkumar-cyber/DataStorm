import { useEffect, useState } from 'react';
import { askBot, fetchBotTopics } from '@/lib/api';
import { MessageSquare, Send, Sparkles } from 'lucide-react';

export default function Bot() {
  const [query, setQuery] = useState('');
  const [messages, setMessages] = useState<{q: string, a: string, conf: boolean}[]>([]);
  const [topics, setTopics] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchBotTopics().then(res => setTopics(res.topics));
  }, []);

  const handleAsk = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query) return;
    setLoading(true);
    try {
      const res = await askBot(query);
      setMessages(prev => [...prev, { q: query, a: res.answer, conf: res.confident }]);
      setQuery('');
    } catch (err: any) {
      alert(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bot-page">
      <div className="bot-container">
        <div className="bot-header">
          <MessageSquare size={24} />
          <div>
            <h3>Policy Bot</h3>
            <p>Ask me anything about our financial policies</p>
          </div>
        </div>

        <div className="chat-window">
          {messages.length === 0 && (
            <div className="chat-empty">
              <Sparkles size={48} />
              <p>Get started by asking a question or picking a topic.</p>
              <div className="topic-grid">
                {topics.map(t => (
                  <button key={t} onClick={() => { setQuery(t); }} className="topic-btn">{t}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className="chat-msg">
              <div className="msg-user">{m.q}</div>
              <div className={`msg-bot ${!m.conf ? 'unconfident' : ''}`}>{m.a}</div>
            </div>
          ))}
          {loading && <div className="msg-bot loading">Thinking...</div>}
        </div>

        <form onSubmit={handleAsk} className="chat-input">
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="Ask about loans, tax, or sweeps..." required />
          <button type="submit" disabled={loading}><Send size={20} /></button>
        </form>
      </div>
    </div>
  );
}

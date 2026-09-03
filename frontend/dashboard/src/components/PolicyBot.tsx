/**
 * The credit-policy assistant, docked on every protected route.
 *
 * It answers from a curated policy base on the server, not from a language
 * model, so an answer about the sweep threshold or the loan cut-off is the same
 * one every time and matches the code that enforces it. When nothing matches
 * well it says so and offers the topics it does cover, rather than guessing.
 */

import { useEffect, useRef, useState } from 'react';
import { MessageCircleQuestion, Send, X } from 'lucide-react';
import { bot } from '@/lib/api';
import { useAction, useAsync } from '@/lib/useAsync';
import { useI18n } from '@/i18n';
import { InlineSpinner } from './primitives';
import type { BotAnswer } from '@/lib/types';

type Turn = { from: 'you' | 'bot'; text: string; answer?: BotAnswer };

export default function PolicyBot() {
  const { t, language } = useI18n();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Topics are the bot's own list of what it can answer, so the suggestions can
  // never drift from the knowledge base the way a hardcoded list would.
  const topics = useAsync(() => bot.topics(), [open]);
  const ask = useAction((text: string) => bot.ask(text, language));

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Keep the newest turn in view. Scrolling the container rather than the page
  // means the panel behaves like a conversation and not like a growing document.
  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open]);

  const submit = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || ask.busy) return;

    setTurns((current) => [...current, { from: 'you', text: trimmed }]);
    setQuestion('');

    // Routed through `ask.run` rather than the API directly, so the busy state
    // the spinner reads is the same one the request actually sets.
    const answer = await ask.run(trimmed);
    setTurns((current) => [
      ...current,
      answer
        ? { from: 'bot', text: answer.answer, answer }
        : { from: 'bot', text: t('state.unavailable') },
    ]);
  };

  if (!open) {
    return (
      <button
        type="button"
        className="bot-launcher"
        onClick={() => setOpen(true)}
        aria-label={t('bot.open')}
      >
        <MessageCircleQuestion size={20} strokeWidth={1.9} aria-hidden="true" />
      </button>
    );
  }

  return (
    <aside className="bot-panel" role="dialog" aria-label={t('bot.title')}>
      <header className="bot-head">
        <div>
          <strong>{t('bot.title')}</strong>
          <p>{t('bot.intro')}</p>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={() => setOpen(false)}
          aria-label={t('action.close')}
        >
          <X size={16} />
        </button>
      </header>

      <div className="bot-transcript" ref={transcriptRef}>
        {turns.length === 0 && topics.data && (
          <div className="bot-topics">
            <p className="bot-topics-label">{t('bot.topics')}</p>
            {topics.data.slice(0, 6).map((topic) => (
              <button key={topic} type="button" className="chip" onClick={() => submit(topic)}>
                {topic}
              </button>
            ))}
          </div>
        )}

        {turns.map((turn, index) => (
          <div key={index} className={`bot-turn from-${turn.from}`}>
            <p>{turn.text}</p>
            {/* An unconfident answer is labelled as one, and its suggestions
                become the next question rather than a dead end. */}
            {turn.answer && !turn.answer.confident && turn.answer.suggestions.length > 0 && (
              <div className="bot-suggestions">
                {turn.answer.suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    className="chip"
                    onClick={() => submit(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
            {turn.answer?.confident && turn.answer.sources[0] && (
              <p className="bot-source">{turn.answer.sources[0].topic}</p>
            )}
          </div>
        ))}

        {ask.busy && <InlineSpinner label={t('state.loading')} />}
      </div>

      <form
        className="bot-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(question);
        }}
      >
        <input
          ref={inputRef}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={t('bot.placeholder')}
          aria-label={t('bot.placeholder')}
          maxLength={500}
        />
        <button type="submit" className="primary-button" disabled={!question.trim() || ask.busy}>
          <Send size={14} strokeWidth={2} aria-hidden="true" />
          <span className="sr-only">{t('bot.send')}</span>
        </button>
      </form>
    </aside>
  );
}

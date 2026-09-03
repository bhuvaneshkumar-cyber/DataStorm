import { Loader2 } from 'lucide-react';

/**
 * A full-page loading state, used only while the session is being verified.
 *
 * Separate from the skeletons in `primitives`: those keep a known layout in
 * place while its data arrives, whereas this covers the moment before the app
 * knows which layout it is going to render at all.
 */
export default function Spinner({ full = false, label }: { full?: boolean; label?: string }) {
  return (
    <div className={full ? 'spinner-page' : 'spinner-inline'} role="status" aria-live="polite">
      <Loader2 size={full ? 26 : 16} className="spin" aria-hidden="true" />
      <span className={full ? 'spinner-label' : 'sr-only'}>{label ?? 'Loading'}</span>
    </div>
  );
}

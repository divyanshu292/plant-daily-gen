import { useEffect, useRef, useState } from 'react';
import { Check, CircleAlert, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { parseInput, toInputText } from '@/lib/format';

function sameValue(a, b, kind) {
  if (a == null || b == null) return a == null && b == null;
  if (kind === 'text') return a === b;
  return Math.abs(a - b) < 1e-9;
}

const HINTS = {
  hours: 'Use h:mm, for example 2:30',
  count: 'Whole number',
  number: 'Number',
  text: '',
};

/**
 * Text box for one stored value. Keeps what the person types as a draft and
 * calls onCommit(value) on blur or Enter, only when the parsed value changed.
 * kind: number | count | hours | text.  status: 'saving' | 'saved' | 'error' | null
 */
export function ValueInput({
  value,
  kind = 'number',
  onCommit,
  flagged = false,
  status = null,
  placeholder = '—',
  className,
  inputClassName,
  ...props
}) {
  const [draft, setDraft] = useState(() => toInputText(value, kind));
  const [invalid, setInvalid] = useState(false);
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) {
      setDraft(toInputText(value, kind));
      setInvalid(false);
    }
  }, [value, kind]);

  const commit = () => {
    const parsed = parseInput(draft, kind === 'count' ? 'number' : kind);
    if (!parsed.ok || (kind === 'count' && parsed.value != null && !Number.isInteger(parsed.value))) {
      setInvalid(true);
      return;
    }
    setInvalid(false);
    setDraft(toInputText(parsed.value, kind));
    if (!sameValue(parsed.value, value ?? null, kind)) onCommit?.(parsed.value);
  };

  const showStatus = status === 'saving' || status === 'saved' || status === 'error';

  return (
    <div className={cn('relative', className)}>
      <input
        type="text"
        inputMode={kind === 'number' ? 'decimal' : kind === 'count' ? 'numeric' : undefined}
        autoComplete="off"
        value={draft}
        placeholder={placeholder}
        title={invalid ? HINTS[kind] : undefined}
        aria-invalid={invalid || undefined}
        onFocus={() => {
          focused.current = true;
        }}
        onChange={(e) => {
          setDraft(e.target.value);
          if (invalid) setInvalid(false);
        }}
        onBlur={() => {
          focused.current = false;
          commit();
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') e.currentTarget.blur();
          if (e.key === 'Escape') {
            setDraft(toInputText(value, kind));
            setInvalid(false);
          }
        }}
        className={cn(
          'h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 text-sm tabular transition-colors',
          kind === 'text' ? 'text-left' : 'text-right',
          showStatus && 'pr-8',
          'placeholder:text-muted-foreground/40 hover:border-foreground/30',
          'focus:border-foreground/60 focus:outline-none focus:ring-1 focus:ring-ring',
          flagged && 'border-attention bg-attention/[0.08] ring-1 ring-attention/60 hover:border-attention',
          (invalid || status === 'error') && 'border-attention ring-1 ring-attention',
          inputClassName
        )}
        {...props}
      />
      {showStatus && (
        <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2">
          {status === 'saving' && <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
          {status === 'saved' && <Check className="h-3.5 w-3.5 text-foreground" />}
          {status === 'error' && <CircleAlert className="h-3.5 w-3.5 text-attention" />}
        </span>
      )}
      {invalid && <div className="mt-1 text-[11px] text-attention">{HINTS[kind] || 'Not valid'}</div>}
    </div>
  );
}

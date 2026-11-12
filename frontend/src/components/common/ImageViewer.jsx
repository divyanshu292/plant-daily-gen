import { useState } from 'react';
import { createPortal } from 'react-dom';
import { ExternalLink, ImageOff, Loader2, Maximize2, X, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useDialog } from '@/lib/hooks';

/** Uploaded page images are deleted this many days after upload (see backend/main.py). */
export const IMAGE_RETENTION_DAYS = 15;

/** False once a report's page image has passed its deletion date. */
export function imageKept(report) {
  return !report?.imageUntil || new Date(report.imageUntil) > new Date();
}

function useImageState() {
  const [state, setState] = useState('loading');
  return [state, { onLoad: () => setState('ok'), onError: () => setState('error') }];
}

function ImageMessage({ state }) {
  if (state === 'loading') {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading the page image
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <ImageOff className="h-4 w-4" /> The page image is not available. Uploaded pages are kept for {IMAGE_RETENTION_DAYS} days.
    </div>
  );
}

/** Full-screen view of an uploaded page. Tap the image to switch between fit and full size. */
export function ImageViewer({ src, title, onClose }) {
  useDialog(onClose);
  const [zoom, setZoom] = useState(false);
  const [state, handlers] = useImageState();

  return createPortal(
    <div className="fixed inset-0 z-[70] flex flex-col bg-background/95 backdrop-blur-sm animate-fade-in" role="dialog" aria-modal="true" aria-label={title}>
      <div className="flex items-center gap-2 border-b border-border px-3 py-2 md:px-6">
        <div className="min-w-0 flex-1 truncate text-sm font-medium">{title}</div>
        <Button variant="ghost" size="sm" onClick={() => setZoom((z) => !z)} disabled={state !== 'ok'}>
          {zoom ? <ZoomOut /> : <ZoomIn />}
          <span className="hidden sm:inline">{zoom ? 'Fit to screen' : 'Full size'}</span>
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <a href={src} target="_blank" rel="noreferrer">
            <ExternalLink />
            <span className="hidden sm:inline">Open in new tab</span>
          </a>
        </Button>
        <Button variant="outline" size="icon" onClick={onClose} aria-label="Close">
          <X />
        </Button>
      </div>
      <div className={cn('relative flex-1 overflow-auto scroll-thin', !zoom && 'flex items-center justify-center p-2 md:p-6')}>
        {state !== 'ok' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <ImageMessage state={state} />
          </div>
        )}
        <img
          src={src}
          alt={title}
          {...handlers}
          onClick={() => setZoom((z) => !z)}
          className={cn(
            'bg-white',
            zoom ? 'max-w-none cursor-zoom-out' : 'max-h-full max-w-full cursor-zoom-in object-contain',
            state !== 'ok' && 'invisible'
          )}
        />
      </div>
    </div>,
    document.body
  );
}

/** The page image inside a card, scrollable, with a zoom toggle and a full-screen button. */
export function InlinePageImage({ src, title, className }) {
  const [zoom, setZoom] = useState(false);
  const [full, setFull] = useState(false);
  const [state, handlers] = useImageState();

  return (
    <div className={cn('space-y-2', className)}>
      <div className="relative h-[55vh] min-h-[280px] overflow-auto rounded-lg border border-border bg-muted/40 scroll-thin md:h-[70vh]">
        {state !== 'ok' && (
          <div className="absolute inset-0 flex items-center justify-center">
            <ImageMessage state={state} />
          </div>
        )}
        <img
          src={src}
          alt={title}
          {...handlers}
          onClick={() => setZoom((z) => !z)}
          className={cn(
            'block bg-white',
            zoom ? 'w-[220%] max-w-none cursor-zoom-out' : 'w-full cursor-zoom-in',
            state !== 'ok' && 'invisible'
          )}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => setZoom((z) => !z)} disabled={state !== 'ok'}>
          {zoom ? <ZoomOut /> : <ZoomIn />}
          {zoom ? 'Fit width' : 'Zoom in'}
        </Button>
        <Button variant="outline" size="sm" onClick={() => setFull(true)} disabled={state === 'error'}>
          <Maximize2 />
          Full screen
        </Button>
      </div>
      {full && <ImageViewer src={src} title={title} onClose={() => setFull(false)} />}
    </div>
  );
}

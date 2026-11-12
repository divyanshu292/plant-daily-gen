import { useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowSquareOutIcon,
  ArrowsOutIcon,
  CircleNotchIcon,
  ImageBrokenIcon,
  MagnifyingGlassMinusIcon,
  MagnifyingGlassPlusIcon,
  XIcon,
} from '@phosphor-icons/react';
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
        <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin" /> Loading the page image
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <ImageBrokenIcon weight="bold" className="h-4 w-4" /> The page image is not available. Uploaded pages are kept for {IMAGE_RETENTION_DAYS} days.
    </div>
  );
}

/** Full-screen view of an uploaded page. Tap the image to switch between fit and full size. */
export function ImageViewer({ src, title, onClose }) {
  useDialog(onClose);
  const [zoom, setZoom] = useState(false);
  const [state, handlers] = useImageState();

  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex flex-col bg-background/95 pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)] backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="flex items-center gap-1 border-b border-border py-1.5 pl-4 pr-1.5 md:gap-2 md:px-6 md:py-2">
        <div className="min-w-0 flex-1 truncate text-sm font-medium">{title}</div>
        <Button
          variant="ghost"
          size="touch"
          className="w-11 px-0 sm:w-auto sm:px-3"
          onClick={() => setZoom((z) => !z)}
          disabled={state !== 'ok'}
          aria-label={zoom ? 'Fit to screen' : 'Full size'}
        >
          {zoom ? <MagnifyingGlassMinusIcon weight="bold" /> : <MagnifyingGlassPlusIcon weight="bold" />}
          <span className="hidden sm:inline">{zoom ? 'Fit to screen' : 'Full size'}</span>
        </Button>
        <Button variant="ghost" size="touch" className="w-11 px-0 sm:w-auto sm:px-3" asChild>
          <a href={src} target="_blank" rel="noreferrer" aria-label="Open in new tab">
            <ArrowSquareOutIcon weight="bold" />
            <span className="hidden sm:inline">Open in new tab</span>
          </a>
        </Button>
        <Button variant="ghost" size="icon-touch" onClick={onClose} aria-label="Close">
          <XIcon weight="bold" />
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
        <Button variant="outline" size="touch" className="md:h-8 md:px-3 md:text-xs" onClick={() => setZoom((z) => !z)} disabled={state !== 'ok'}>
          {zoom ? <MagnifyingGlassMinusIcon weight="bold" /> : <MagnifyingGlassPlusIcon weight="bold" />}
          {zoom ? 'Fit width' : 'Zoom in'}
        </Button>
        <Button variant="outline" size="touch" className="md:h-8 md:px-3 md:text-xs" onClick={() => setFull(true)} disabled={state === 'error'}>
          <ArrowsOutIcon weight="bold" />
          Full screen
        </Button>
      </div>
      {full && <ImageViewer src={src} title={title} onClose={() => setFull(false)} />}
    </div>
  );
}

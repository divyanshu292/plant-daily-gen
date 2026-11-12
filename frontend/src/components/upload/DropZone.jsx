import { useMemo, useRef, useState } from 'react';
import { Camera, ImageUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/** Drag and drop, click to choose, or the phone camera. Paste is handled by the screen. */
export function DropZone({ onFiles }) {
  const pickRef = useRef(null);
  const cameraRef = useRef(null);
  const [over, setOver] = useState(false);
  const touch = useMemo(() => typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches, []);

  const take = (e) => {
    onFiles(e.target.files);
    e.target.value = '';
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Choose report images to upload"
      onClick={() => pickRef.current?.click()}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          pickRef.current?.click();
        }
      }}
      onDragEnter={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        if (!over) setOver(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setOver(false);
        onFiles(e.dataTransfer.files);
      }}
      className={cn(
        'group flex cursor-pointer flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed px-5 py-10 text-center transition-colors md:py-16',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background',
        over ? 'border-foreground bg-accent' : 'border-border bg-card hover:border-foreground/40'
      )}
    >
      <div
        className={cn(
          'flex h-14 w-14 items-center justify-center rounded-full border transition-colors',
          over ? 'border-foreground bg-foreground text-background' : 'border-border text-muted-foreground group-hover:text-foreground'
        )}
      >
        <ImageUp className="h-6 w-6" />
      </div>
      <div className="space-y-1.5">
        <div className="text-lg font-semibold tracking-tight md:text-xl">
          {over ? 'Drop to upload' : touch ? 'Photograph or choose the report page' : 'Drop the report page here'}
        </div>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">
          A photo or screenshot of the Daily System Report. You can add several pages at once; they are read one
          after another.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {touch && (
          <Button
            size="lg"
            onClick={(e) => {
              e.stopPropagation();
              cameraRef.current?.click();
            }}
          >
            <Camera />
            Take photo
          </Button>
        )}
        <Button
          size="lg"
          variant={touch ? 'outline' : 'default'}
          onClick={(e) => {
            e.stopPropagation();
            pickRef.current?.click();
          }}
        >
          <ImageUp />
          Choose images
        </Button>
      </div>
      <div className="hidden text-xs text-muted-foreground md:block">
        You can also paste a screenshot here with <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 text-[10px]">Ctrl</kbd>{' '}
        + <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 text-[10px]">V</kbd> (
        <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 text-[10px]">⌘</kbd> +{' '}
        <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 text-[10px]">V</kbd> on a Mac).
      </div>

      <input ref={pickRef} type="file" accept="image/*" multiple className="hidden" onChange={take} onClick={(e) => e.stopPropagation()} />
      <input
        ref={cameraRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={take}
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  );
}

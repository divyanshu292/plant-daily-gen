import { CameraIcon, ImagesIcon } from '@phosphor-icons/react';
import { cn } from '@/lib/utils';

const TILE =
  'relative flex h-32 cursor-pointer select-none flex-col items-center justify-center gap-3 rounded-2xl border text-center transition-[opacity,background-color] active:opacity-80 [-webkit-tap-highlight-color:transparent] focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background';

/**
 * The phone's way in: the camera, or the photo library / files. Labels wrap the
 * inputs so a tap opens the picker natively (no scripted click).
 */
export function PhonePicker({ onFiles, className }) {
  const take = (e) => {
    onFiles(e.target.files);
    e.target.value = '';
  };

  return (
    <div className={cn('space-y-3', className)}>
      <div className="grid grid-cols-2 gap-3">
        <label className={cn(TILE, 'border-foreground bg-foreground text-background')}>
          <CameraIcon weight="fill" className="h-8 w-8" />
          <span className="text-base font-semibold tracking-tight">Take photo</span>
          <input type="file" accept="image/*" capture="environment" className="sr-only" onChange={take} />
        </label>
        <label className={cn(TILE, 'border-border bg-card text-foreground')}>
          <ImagesIcon weight="fill" className="h-8 w-8" />
          <span className="text-base font-semibold tracking-tight">Choose image</span>
          <input type="file" accept="image/*" multiple className="sr-only" onChange={take} />
        </label>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        Photograph the Daily System Report flat and in good light, or pick a screenshot. Several pages can be added;
        they are read one after another.
      </p>
    </div>
  );
}

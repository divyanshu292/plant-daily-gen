import { cn } from '@/lib/utils';

export function MicroLabel({ className, children, as: Comp = 'div', ...props }) {
  return (
    <Comp
      className={cn('text-[11px] font-medium uppercase tracking-widest text-muted-foreground', className)}
      {...props}
    >
      {children}
    </Comp>
  );
}

/** Screen heading: micro-label, large title, optional muted second line. */
export function PageHeading({ eyebrow, title, subtitle, children }) {
  return (
    <section className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0 space-y-2">
        {eyebrow && <MicroLabel>{eyebrow}</MicroLabel>}
        <h1 className="text-3xl font-semibold leading-[1.05] tracking-tight md:text-5xl">{title}</h1>
        {subtitle && <p className="max-w-2xl text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </section>
  );
}

export function SectionTitle({ title, hint, children }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <MicroLabel>{title}</MicroLabel>
        {hint && <div className="mt-1 text-xs text-muted-foreground/80">{hint}</div>}
      </div>
      {children}
    </div>
  );
}

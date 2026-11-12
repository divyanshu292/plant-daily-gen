// Things that stick while the page scrolls must sit right under the app header, not behind it.
// The header is 3 rem tall on phones and 3.5 rem from md up, below the notch. Put STICKY_TOP on
// a screen's root element and use `top-[var(--sticky-top)]` on sticky children. If the header
// ever publishes its height as --app-header-h, that value wins.
export const STICKY_TOP =
  '[--sticky-top:var(--app-header-h,calc(3rem_+_env(safe-area-inset-top)))] md:[--sticky-top:var(--app-header-h,calc(3.5rem_+_env(safe-area-inset-top)))]';

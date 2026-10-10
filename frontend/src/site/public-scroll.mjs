/** Public anchors have one owner. Booking and Contact keep their own form scrolling. */
export function observeHeader(shell, header) {
  let disposed = false;
  const measure = () => {
    if (!disposed && header?.isConnected) {
      const value = `${header.getBoundingClientRect().height}px`;
      if (shell.style.getPropertyValue('--public-header-height') !== value) shell.style.setProperty('--public-header-height', value);
    }
  };
  measure();
  let observer;
  try { if (typeof ResizeObserver === 'function') { observer = new ResizeObserver(measure); observer.observe(header); } } catch { observer?.disconnect(); observer = null; }
  window.addEventListener('resize', measure);
  document.fonts?.ready?.then(measure);
  return () => { disposed = true; observer?.disconnect(); window.removeEventListener('resize', measure); };
}

// Solve the x component before evaluating y: the easing is cubic-bezier(.2,.7,.2,1).
export function scrollEase(progress) {
  if (progress <= 0 || progress >= 1) return Math.max(0, Math.min(1, progress));
  const curve = (t, a, b) => 3 * (1 - t) ** 2 * t * a + 3 * (1 - t) * t * t * b + t ** 3;
  let low = 0, high = 1;
  for (let i = 0; i < 16; i++) { const t = (low + high) / 2; if (curve(t, .2, .2) < progress) low = t; else high = t; }
  return curve((low + high) / 2, .7, 1);
}

export function createPublicScroller({ main, header, navigate }) {
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  let generation = 0, frame = 0, observer, timer, intent, previous, disposed = false;
  function cancel() {
    generation++;
    if (frame) window.cancelAnimationFrame(frame);
    frame = 0; observer?.disconnect(); observer = null; clearTimeout(timer);
  }
  function focus(element) { if (element?.isConnected) element.focus({ preventScroll: true }); }
  function move({ target, animate = true, keyboard = false, marker, top = false }) {
    cancel();
    const token = generation;
    const offset = header && getComputedStyle(header).position === 'sticky' ? header.getBoundingClientRect().height : 0;
    const max = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    const end = top ? 0 : Math.max(0, Math.min(max, target.getBoundingClientRect().top + window.scrollY - offset - (animate ? 16 : 0)));
    const start = window.scrollY;
    const finish = () => { frame = 0; if (!disposed && token === generation && keyboard) focus(marker); };
    if (!animate || reduced?.matches || (typeof window.requestAnimationFrame !== 'function' || typeof window.cancelAnimationFrame !== 'function') || start === end) {
      window.scrollTo(0, end); finish(); return;
    }
    const started = performance.now();
    const tick = now => {
      if (disposed || token !== generation) return;
      const progress = Math.min(1, Math.max(0, (now - started) / 400));
      window.scrollTo(0, start + (end - start) * scrollEase(progress));
      if (progress < 1) frame = window.requestAnimationFrame(tick); else finish();
    };
    frame = window.requestAnimationFrame(tick);
  }
  function route(location, navigationType) {
    cancel();
    const activated = navigationType !== 'POP' && intent?.url === location.pathname + location.search + location.hash ? intent : null;
    intent = null;
    const sameDestination = previous?.pathname === location.pathname && previous?.hash === location.hash;
    previous = location;
    if (!activated && sameDestination) return; // Query-only booking changes are owned by the wizard.
    if (!location.hash) { window.scrollTo(0, 0); return; }
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const token = generation;
    const find = () => {
      if (disposed || token !== generation) return false;
      const target = document.getElementById(id);
      if (!target || !main.contains(target)) return false;
      const marker = [...main.querySelectorAll('[data-scroll-destination]')].find(el => el.dataset.scrollDestination === id);
      move({ target, animate: !!activated, keyboard: !!activated?.keyboard, marker });
      return true;
    };
    if (!find() && typeof MutationObserver === 'function') {
      observer = new MutationObserver(find);
      observer.observe(main, { childList: true, subtree: true });
      timer = setTimeout(() => { if (token === generation) { observer?.disconnect(); observer = null; } }, 10000);
    }
  }
  function click(event) {
    const anchor = event.target.closest?.('a[data-public-scroll]');
    if (!anchor || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey || anchor.hasAttribute('download') || (anchor.target && anchor.target !== '_self')) return;
    const url = new URL(anchor.href, window.location.href);
    if (url.origin !== window.location.origin || url.pathname !== window.location.pathname || url.search !== window.location.search || !url.hash) return;
    cancel();
    intent = { url: url.pathname + url.search + url.hash, keyboard: event.detail === 0 };
    event.preventDefault(); event.stopPropagation();
    navigate(intent.url);
  }
  function interrupt(event) {
    if (event.type === 'keydown' && (!['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key) || event.target.closest?.('input,textarea,select,[contenteditable="true"]'))) return;
    if (event.type === 'visibilitychange' && !document.hidden) return;
    cancel(); intent = null;
  }
  main.addEventListener('click', click, true);
  const events = ['wheel', 'touchstart', 'pointerdown', 'keydown', 'resize'];
  events.forEach(name => window.addEventListener(name, interrupt, { passive: true }));
  document.addEventListener('visibilitychange', interrupt);
  reduced?.addEventListener?.('change', interrupt);
  return {
    route,
    top: keyboard => move({ top: true, keyboard, marker: main }),
    dispose() { disposed = true; cancel(); main.removeEventListener('click', click, true); events.forEach(name => window.removeEventListener(name, interrupt)); document.removeEventListener('visibilitychange', interrupt); reduced?.removeEventListener?.('change', interrupt); },
  };
}

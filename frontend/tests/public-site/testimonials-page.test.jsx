/** Page-only integration checks use the client-approved public review collection;
 * no real customer, booking, payment, email or provider operation is allowed. */
import React, {act, StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {MemoryRouter, useLocation} from 'react-router-dom';
import {beforeEach, afterEach, test, expect, vi} from 'vitest';
import {testimonialStories} from '../fixtures/testimonial-stories.mjs';

const model = vi.hoisted(() => ({snapshot: {}, listeners: new Set(), location: null}));
vi.mock('../../src/site/BookingProduct.jsx', async () => {
  const React = await import('react');
  const Router = await import('react-router-dom');
  const {createReactBindings} = await import('../../../appointment-system/browser/react-bindings.mjs');
  const {surfaces} = await import('../../../appointment-settings/project.json');
  return createReactBindings(React, Router, {surfaces, state: {
    subscribe: listener => {model.listeners.add(listener); return () => model.listeners.delete(listener);},
    getSnapshot: () => model.snapshot,
    getServerSnapshot: () => model.snapshot,
    start: () => () => {},
    refresh: async () => {}
  }});
});
import Testimonials from '../../src/pages/Testimonials.jsx';

const categories = ['kundli-prediction', 'kundli-matching', 'vastu-consultation', 'numerology'];
const originalDialogMethods = Object.fromEntries(['showModal', 'close'].map(name => [
  name, Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, name)
]));
let root, host, fetchSpy, media;

function LocationRecorder() {model.location = useLocation(); return null;}
function cards() {return [...host.querySelectorAll('.story-card[data-story]')];}
function readButton() {return host.querySelector('.story-card button[data-story-id]');}
function shownIds() {return cards().map(card => card.dataset.story);}
async function click(element) {
  expect(element).not.toBeNull();
  await act(async () => element.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, button: 0, detail: 1})));
}
async function renderPage({stories = testimonialStories, strict = false, useDefault = false} = {}) {
  const page = useDefault ? <Testimonials/> : <Testimonials stories={stories}/>;
  const contents = <MemoryRouter initialEntries={['/testimonials']}>
    <main id="page-content" tabIndex="-1">{page}</main><LocationRecorder/>
  </MemoryRouter>;
  await act(async () => root.render(strict ? <StrictMode>{contents}</StrictMode> : contents));
}
async function availability(update) {
  await act(async () => {
    model.snapshot = {...model.snapshot, ...update};
    model.listeners.forEach(listener => listener());
  });
}
async function unmountPage() {
  await act(async () => root.unmount());
  root = null;
}

// jsdom does not supply the browser's top-layer/inert/default-cancel behaviour.
// These methods exercise the page's native-dialog lifecycle wiring only.
function nativeDialogMethods() {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {configurable: true, value: vi.fn(function () {
    this.setAttribute('open', '');
  })});
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {configurable: true, value: vi.fn(function () {
    this.removeAttribute('open');
    this.dispatchEvent(new Event('close'));
  })});
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  model.snapshot = {enabled: true, verified: true, checking: false, retained_on_epoch: 'synthetic-testimonials'};
  model.listeners.clear();
  model.location = null;
  host = document.createElement('div');
  document.body.append(host);
  document.body.style.overflow = '';
  root = createRoot(host);
  media = new EventTarget();
  media.matches = true;
  vi.stubGlobal('matchMedia', () => media);
  vi.stubGlobal('IntersectionObserver', class {observe() {} disconnect() {}});
  vi.stubGlobal('ResizeObserver', class {observe() {} disconnect() {}});
  window.scrollTo = vi.fn();
  HTMLElement.prototype.scrollIntoView = vi.fn();
  fetchSpy = vi.fn(() => {throw Error('Network access is forbidden in the testimonials page checks.');});
  vi.stubGlobal('fetch', fetchSpy);
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {configurable: true, value: undefined});
});
afterEach(async () => {
  if (root) await unmountPage();
  expect(fetchSpy).not.toHaveBeenCalled();
  host.remove();
  document.body.style.overflow = '';
  delete HTMLElement.prototype.scrollIntoView;
  for (const [name, descriptor] of Object.entries(originalDialogMethods)) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor);
    else delete HTMLDialogElement.prototype[name];
  }
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test('the first six stories cover all four services without changing their excerpts', async () => {
  await renderPage();
  expect(host.querySelectorAll('.sarsa-testimonials')).toHaveLength(1);
  expect(cards()).toHaveLength(6);
  expect(new Set(cards().map(card => testimonialStories.find(story => story.id === card.dataset.story).category))).toEqual(new Set(categories));
  for (const card of cards()) {
    const story = testimonialStories.find(record => record.id === card.dataset.story);
    expect(card.querySelector('blockquote').textContent).toBe(story.quote);
    expect(card.querySelector('blockquote').lang).toBe(story.lang);
    expect(card.textContent).toContain(story.name);
    expect(card.textContent).toContain(story.city);
    expect(card.querySelector('.card-read').getAttribute('aria-label')).toBe('Read full story from '+story.name);
  }
  expect(host.querySelector('#result-count').textContent).toMatch(/6.*12/);
  expect(host.querySelector('#more-stories').hidden).toBe(false);
  for (const button of host.querySelectorAll('button[data-story-id]')) {
    const story = testimonialStories.find(record => record.id === button.dataset.storyId);
    expect(button.getAttribute('aria-label')).toBe(button.textContent.trim()+' from '+story.name);
  }
});

test('service filters preserve their controls and focus while showing only matching stories', async () => {
  await renderPage();
  const controls = [...host.querySelectorAll('[data-filter]')];
  for (const category of categories) {
    const button = controls.find(control => control.dataset.filter === category);
    button.focus();
    await click(button);
    expect(document.activeElement).toBe(button);
    expect([...host.querySelectorAll('[data-filter]')]).toEqual(controls);
    expect(controls.filter(control => control.getAttribute('aria-pressed') === 'true')).toEqual([button]);
    expect(new Set(shownIds())).toEqual(new Set(testimonialStories.filter(story => story.category === category).map(story => story.id)));
    expect(cards()).toHaveLength(3);
    expect(host.querySelector('#result-count').textContent).toMatch(/3.*3/);
    expect(host.querySelector('#more-stories')).toBeNull();
  }
});

test('See more reveals all twelve once and continues reading at the first added article', async () => {
  await renderPage();
  const initial = shownIds();
  const more = host.querySelector('#more-stories');
  more.focus();
  await click(more);
  expect(cards()).toHaveLength(12);
  expect(new Set(shownIds())).toEqual(new Set(testimonialStories.map(story => story.id)));
  expect(shownIds().slice(0, 6)).toEqual(initial);
  for (const card of cards()) {
    const story = testimonialStories.find(record => record.id === card.dataset.story);
    expect(card.querySelector('blockquote').textContent).toBe(story.quote);
    expect(card.querySelector('blockquote').lang).toBe(story.lang);
  }
  expect(document.activeElement).toBe(cards()[6]);
  expect(host.querySelector('#more-stories')).toBeNull();
  expect(host.querySelector('#result-count').textContent).toMatch(/12.*12/);
  await click(host.querySelector('[data-filter="numerology"]'));
  await click(host.querySelector('[data-filter="all"]'));
  expect(cards()).toHaveLength(6);
  expect(host.querySelector('#more-stories')).not.toBeNull();
});

test('featured selection wraps manually while keeping buttons and story targets consistent', async () => {
  await renderPage();
  const previous = host.querySelector('#feature-prev');
  const next = host.querySelector('#feature-next');
  const expected = categories.slice(0, 3).map(category => testimonialStories.find(story => story.category === category));
  for (const story of [...expected.slice(1), expected[0]]) {
    next.focus();
    await click(next);
    expect(host.querySelector('#feature-next')).toBe(next);
    expect(host.querySelector('#feature-prev')).toBe(previous);
    expect(document.activeElement).toBe(next);
    expect(host.querySelector('#featured-story').textContent).toContain(story.quote);
    expect(host.querySelector('#featured-story').textContent).toContain(story.name);
    expect(host.querySelector('#featured-story button[data-story-id]').dataset.storyId).toBe(story.id);
  }
  await click(previous);
  expect(host.querySelector('#featured-story button[data-story-id]').dataset.storyId).toBe(expected[2].id);
});

test('theme selectors use three distinct voices without replacing the focused controls', async () => {
  await renderPage();
  const controls = [...host.querySelectorAll('[data-theme]')];
  const expected = {heard: 'neha-numerology', simple: 'rohit-vastu', calm: 'kavya-matching'};
  for (const [theme, id] of Object.entries(expected)) {
    const button = controls.find(control => control.dataset.theme === theme);
    button.focus();
    await click(button);
    const story = testimonialStories.find(record => record.id === id);
    expect(document.activeElement).toBe(button);
    expect([...host.querySelectorAll('[data-theme]')]).toEqual(controls);
    expect(controls.filter(control => control.getAttribute('aria-pressed') === 'true')).toEqual([button]);
    expect(host.querySelector('.echo-content').textContent).toContain(story.quote);
    expect(host.querySelector('.echo-content').textContent).toContain(story.name);
    expect(host.querySelector('.echo-content button[data-story-id]').dataset.storyId).toBe(story.id);
  }
});

test('featured and theme readers close before changing their selected story', async () => {
  await renderPage();
  const featureButton = host.querySelector('#featured-story button[data-story-id]');
  await click(featureButton);
  expect(host.querySelector('.feature-reader [data-inline]')).not.toBeNull();
  const next = host.querySelector('#feature-next');
  next.focus();
  await click(next);
  expect(host.querySelector('[data-inline]')).toBeNull();
  expect(document.activeElement).toBe(next);

  await click(host.querySelector('.echo-content button[data-story-id]'));
  expect(host.querySelector('.echo-reading [data-inline]')).not.toBeNull();
  const theme = host.querySelector('[data-theme="calm"]');
  theme.focus();
  await click(theme);
  expect(host.querySelector('[data-inline]')).toBeNull();
  expect(document.activeElement).toBe(theme);
  const opener = host.querySelector('.echo-content button[data-story-id]');
  await click(opener);
  await click(host.querySelector('#dialog-close'));
  expect(document.activeElement).toBe(opener);
});

test('unsupported-dialog reading is an inline region with exact content and focus restoration', async () => {
  await renderPage();
  const opener = readButton();
  const story = testimonialStories.find(record => record.id === opener.dataset.storyId);
  opener.focus();
  await click(opener);
  const reader = host.querySelector('[data-inline]');
  expect(reader).not.toBeNull();
  expect(reader.getAttribute('role')).toBe('region');
  expect(reader.getAttribute('aria-modal')).not.toBe('true');
  expect(document.activeElement).toBe(host.querySelector('#dialog-title'));
  expect(reader.textContent).toContain(story.quote);
  for (const paragraph of story.paragraphs) expect(reader.textContent).toContain(paragraph);
  expect(document.body.style.overflow).toBe('');
  await click(host.querySelector('#dialog-close'));
  expect(host.querySelector('[data-inline]')).toBeNull();
  expect(document.activeElement).toBe(opener);
});

test('inline readers can change story, close on Escape, and reopen after filtering', async () => {
  await renderPage();
  const first = readButton();
  await click(first);
  const second = cards()[1].querySelector('button[data-story-id]');
  await click(second);
  expect(host.querySelectorAll('[data-inline]')).toHaveLength(1);
  expect(host.querySelector('#dialog-title').textContent).toContain(testimonialStories.find(story => story.id === second.dataset.storyId).name);
  await act(async () => host.querySelector('#dialog-title').dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true})));
  expect(host.querySelector('[data-inline]')).toBeNull();
  expect(document.activeElement).toBe(second);
  await click(readButton());
  const filter = host.querySelector('[data-filter="numerology"]');
  filter.focus();
  await click(filter);
  expect(host.querySelector('[data-inline]')).toBeNull();
  expect(document.activeElement).toBe(filter);
  await click(readButton());
  expect(host.querySelector('[data-inline]')).not.toBeNull();
});

test('See more closes an inline reader before updating the collection', async () => {
  await renderPage();
  await click(readButton());
  await click(host.querySelector('#more-stories'));
  expect(host.querySelector('[data-inline]')).toBeNull();
  expect(cards()).toHaveLength(12);
  expect(document.activeElement).toBe(cards()[6]);
  await click(cards()[6].querySelector('button[data-story-id]'));
  expect(host.querySelector('[data-inline]')).not.toBeNull();
});

test.each(['close', 'cancel'])('native-dialog %s wiring restores the opener and previous scrolling', async method => {
  nativeDialogMethods();
  document.body.style.overflow = 'scroll';
  await renderPage();
  const opener = readButton();
  opener.focus();
  await click(opener);
  const dialog = host.querySelector('#story-dialog');
  expect(dialog.open).toBe(true);
  expect(dialog.showModal).toHaveBeenCalledOnce();
  expect(document.activeElement).toBe(host.querySelector('#dialog-title'));
  expect(document.body.style.overflow).toBe('hidden');
  if (method === 'close') await click(host.querySelector('#dialog-close'));
  else await act(async () => {
    const cancellation = new Event('cancel', {cancelable: true});
    dialog.dispatchEvent(cancellation);
    // Emulate the browser's default Escape action only when not handled by React.
    if (!cancellation.defaultPrevented && dialog.open) dialog.close();
  });
  expect(dialog.open).toBe(false);
  expect(document.activeElement).toBe(opener);
  expect(document.body.style.overflow).toBe('scroll');
});

test('native-dialog keyboard wiring reaches Close in either direction from the reading title', async () => {
  nativeDialogMethods();
  await renderPage();
  await click(readButton());
  const title = host.querySelector('#dialog-title');
  const close = host.querySelector('#dialog-close');
  for (const shiftKey of [false, true]) {
    title.focus();
    await act(async () => title.dispatchEvent(new KeyboardEvent('keydown', {key: 'Tab', shiftKey, bubbles: true, cancelable: true})));
    expect(document.activeElement).toBe(close);
  }
});

test('StrictMode does not duplicate stories and unmounting an open reader restores scrolling', async () => {
  nativeDialogMethods();
  document.body.style.overflow = 'auto';
  await renderPage({strict: true});
  expect(cards()).toHaveLength(6);
  expect(host.querySelectorAll('#story-dialog')).toHaveLength(0);
  await click(readButton());
  expect(host.querySelectorAll('#story-dialog')).toHaveLength(1);
  expect(document.body.style.overflow).toBe('hidden');
  await unmountPage();
  expect(document.body.style.overflow).toBe('auto');
  expect(document.querySelector('[data-inline]')).toBeNull();
  expect(document.querySelector('#story-dialog')).toBeNull();
  expect(model.listeners.size).toBe(0);
});

test.each([
  {enabled: false, verified: true, checking: false, retained_on_epoch: null},
  {enabled: false, verified: false, checking: false, retained_on_epoch: null}
])('booking unavailable state %j keeps stories and service exploration available', async state => {
  await renderPage();
  expect(host.querySelector('a[href="/booking"]')).not.toBeNull();
  await availability(state);
  expect(host.querySelector('a[href="/booking"]')).toBeNull();
  expect(host.querySelector('a[href="/services"]')).not.toBeNull();
  expect(cards()).toHaveLength(6);
  await click(readButton());
  expect(host.querySelector('[data-inline]')).not.toBeNull();
});

test('a displayed Book action cannot bypass a newer booking admission restriction', async () => {
  await renderPage();
  const book = host.querySelector('a[href="/booking"]');
  model.snapshot = {...model.snapshot, checking: true};
  await click(book);
  expect(model.location.pathname).toBe('/testimonials');
  model.snapshot = {...model.snapshot, checking: false};
  await click(book);
  expect(model.location.pathname).toBe('/booking');
});

test('an explicitly empty editorial collection exposes no identities or dead story controls', async () => {
  await renderPage({stories: []});
  expect(host.querySelector('h1')).not.toBeNull();
  expect(cards()).toHaveLength(0);
  expect(host.querySelector('button[data-story-id]')).toBeNull();
  expect(host.querySelector('a[href="/services"]')).not.toBeNull();
  for (const story of testimonialStories) expect(host.textContent).not.toContain(story.name);
});

test('the public route default contains all five approved chapters and all twelve complete reviews', async () => {
  await renderPage({useDefault: true});
  expect([...host.querySelectorAll('.chapter[data-scene]')].map(section => section.dataset.scene)).toEqual([
    'opening', 'featured', 'collection', 'echoes', 'invitation'
  ]);
  expect(host.querySelector('h1').textContent).toBe('What people sayabout Madhuri.');
  expect(host.textContent).not.toContain('Reviews will be added here.');
  expect(host.querySelectorAll('[data-paper]')).toHaveLength(3);
  expect(cards()).toHaveLength(6);
  await click(host.querySelector('#more-stories'));
  expect(cards()).toHaveLength(12);
  for (const story of testimonialStories) {
    const card = cards().find(item => item.dataset.story === story.id);
    expect(card.querySelector('blockquote').textContent).toBe(story.quote);
    expect(card.textContent).toContain(story.name);
    await click(card.querySelector('button[data-story-id]'));
    const reader = host.querySelector('[data-inline]');
    for (const paragraph of story.paragraphs) expect(reader.textContent).toContain(paragraph);
    await click(host.querySelector('#dialog-close'));
  }
});

test('one story works without carousel or theme controls and an empty service group can reset', async () => {
  // Deliberately sparse test-only content; no assumption that the client has twelve reviews.
  const story = {...testimonialStories.find(record => record.category === 'numerology'), theme: undefined};
  await renderPage({stories: [story]});
  expect(cards()).toHaveLength(1);
  expect(host.querySelector('#result-count').textContent).toBe('Showing 1 of 1 story');
  expect(host.querySelector('#feature-prev')).toBeNull();
  expect(host.querySelector('#feature-next')).toBeNull();
  expect(host.querySelector('#featured-story').textContent).toContain(story.quote);
  expect(host.querySelector('[data-theme]')).toBeNull();
  expect(host.querySelector('.echoes')).toBeNull();
  expect(host.querySelector('#more-stories')).toBeNull();

  const emptyGroup = host.querySelector('[data-filter="kundli-matching"]');
  emptyGroup.focus();
  await click(emptyGroup);
  expect(cards()).toHaveLength(0);
  expect(host.querySelector('#result-count').textContent).toBe('Showing 0 of 0 stories');
  expect(host.querySelector('#empty-stories')).not.toBeNull();
  expect(document.activeElement).toBe(emptyGroup);
  await click(host.querySelector('#reset-filter'));
  expect(cards()).toHaveLength(1);
  expect(host.querySelector('#empty-stories')).toBeNull();
  expect(document.activeElement).toBe(host.querySelector('[data-filter="all"]'));
  await click(readButton());
  expect(host.querySelector('#dialog-title').textContent).toContain(story.name);
});

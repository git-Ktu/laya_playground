'use strict';
const guideScrollKey = 'laya-guide:scroll:v1';
const menu = document.getElementById('guide-menu');
const chapterNav = document.querySelector('.chapter-nav');
const navLinks = [...document.querySelectorAll('#guide-nav a')];
const sections = [...document.querySelectorAll('#guide-content section')];
let currentSection = null;
function closeMenu(focus = false) {
  chapterNav.classList.remove('open');
  menu.setAttribute('aria-expanded', 'false');
  if (focus) menu.focus();
}
menu.addEventListener('click', () => {
  const open = chapterNav.classList.toggle('open');
  menu.setAttribute('aria-expanded', String(open));
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape') return;
  if (!document.getElementById('guide-manual-container').hidden) closeManualCopy();
  else if (chapterNav.classList.contains('open')) closeMenu(true);
});
function updateChapter() {
  const active = sections.reduce((selected, section) => section.getBoundingClientRect().top <= 170 ? section : selected, sections[0]);
  if (active === currentSection) return;
  currentSection = active;
  navLinks.forEach(link => {
    if (link.hash === `#${active.id}`) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  });
  const local = document.getElementById('guide-local-nav');
  local.replaceChildren();
  const title = document.createElement('strong'); title.textContent = 'この章の内容'; local.append(title);
  active.querySelectorAll('h3[id]').forEach(heading => {
    const link = document.createElement('a'); link.href = `#${heading.id}`; link.textContent = heading.textContent; local.append(link);
  });
}
navLinks.forEach(link => link.addEventListener('click', event => {
  event.preventDefault();
  closeMenu();
  history.pushState(null, '', link.hash);
  document.querySelector(link.hash).scrollIntoView();
  const heading = document.querySelector(`${link.hash} h2`);
  heading.tabIndex = -1; heading.focus({preventScroll:true});
  updateChapter();
}));
function savePosition() {
  try { sessionStorage.setItem(guideScrollKey, String(scrollY)); } catch (_) { /* Reading remains available without storage. */ }
}
window.addEventListener('scroll', updateChapter, {passive:true});
window.addEventListener('pagehide', savePosition);
document.querySelectorAll('[data-internal-nav]').forEach(link => link.addEventListener('click', savePosition));
function restorePosition() {
  if (location.hash) {
    const target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
    if (target) target.scrollIntoView();
  } else {
    try {
      const raw = sessionStorage.getItem(guideScrollKey);
      const position = Number(raw);
      if (raw !== null && Number.isFinite(position) && position >= 0) scrollTo(0, position);
    } catch (_) { /* Storage restrictions must not block the guide. */ }
  }
  updateChapter();
}
window.addEventListener('pageshow', event => { if (!event.persisted) requestAnimationFrame(restorePosition); else updateChapter(); });
window.addEventListener('hashchange', () => { requestAnimationFrame(updateChapter); });
let manualCopyButton = null;
function closeManualCopy() {
  document.getElementById('guide-manual-container').hidden = true;
  document.getElementById('guide-copy-status').textContent = '';
  manualCopyButton?.focus({preventScroll:true});
}
document.getElementById('guide-manual-close').addEventListener('click', closeManualCopy);
async function copyExample(targetId, button) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const text = target.textContent;
  const status = document.getElementById('guide-copy-status');
  const container = document.getElementById('guide-manual-container');
  container.hidden = true;
  try {
    if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
    await navigator.clipboard.writeText(text);
    status.textContent = 'JSON をコピーしました。';
    return;
  } catch (_) { /* LAN HTTP can lack the Clipboard API. */ }
  const manual = document.getElementById('guide-manual-copy');
  manualCopyButton = button;
  container.hidden = false; manual.value = text; manual.focus({preventScroll:true}); manual.select();
  try {
    if (document.execCommand('copy')) {
      container.hidden = true; button.focus({preventScroll:true});
      status.textContent = 'JSON をコピーしました。'; return;
    }
  } catch (_) { /* Keep the text selected for manual copying. */ }
  status.textContent = '自動コピーが使えません。選択済みの JSON を Ctrl+C / ⌘C で手動コピーしてください。';
}
document.querySelectorAll('[data-copy-target]').forEach(button => button.addEventListener('click', () => copyExample(button.dataset.copyTarget, button)));
updateChapter();

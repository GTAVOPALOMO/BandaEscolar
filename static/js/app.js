const toggle = document.querySelector('.nav-toggle');
const nav = document.getElementById('navlinks');
if (toggle && nav) {
  document.documentElement.classList.add('nav-enhanced');
  const closeNav = (restoreFocus = false) => {
    nav.classList.remove('open');
    toggle.setAttribute('aria-expanded', 'false');
    if (restoreFocus) toggle.focus();
  };
  toggle.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      const menu = document.querySelector('.nav-more[open]');
      if (menu && menu.contains(document.activeElement)) {
        menu.open = false;
        menu.querySelector('summary').focus();
      } else if (nav.classList.contains('open')) {
        closeNav(true);
      }
    }
  });
  document.addEventListener('click', event => {
    if (!nav.contains(event.target) && !toggle.contains(event.target)) {
      closeNav(nav.contains(document.activeElement));
    }
  });
  nav.addEventListener('click', event => {
    if (event.target.closest('a')) closeNav();
  });
  const mobileNav = window.matchMedia('(max-width: 1100px)');
  mobileNav.addEventListener('change', () => {
    closeNav(mobileNav.matches && nav.contains(document.activeElement));
  });
}
const search = document.getElementById('table-search');
if (search) search.addEventListener('input', () => {
  const rows = [...document.querySelectorAll('#filter-table tbody tr')];
  rows.forEach(row => { row.hidden = !row.textContent.toLowerCase().includes(search.value.toLowerCase()); });
  const status = document.getElementById('search-status');
  if (status) status.textContent = `${rows.filter(row => !row.hidden && row.querySelector('a')).length} estudiantes encontrados.`;
});

const toggle = document.querySelector('.nav-toggle');
if (toggle) toggle.addEventListener('click', () => {
  const nav = document.getElementById('navlinks');
  const open = nav.classList.toggle('open');
  toggle.setAttribute('aria-expanded', String(open));
});
const search = document.getElementById('table-search');
if (search) search.addEventListener('input', () => {
  document.querySelectorAll('#filter-table tbody tr').forEach(row => row.hidden = !row.textContent.toLowerCase().includes(search.value.toLowerCase()));
});

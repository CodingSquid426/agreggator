const searchInput = document.getElementById('searchInput');
const sourceFilter = document.getElementById('sourceFilter');
const clearFilters = document.getElementById('clearFilters');
const cards = [...document.querySelectorAll('.card')];
const themeToggle = document.getElementById('themeToggle');

const applyFilters = () => {
  const query = searchInput.value.trim().toLowerCase();
  const source = sourceFilter.value;

  cards.forEach((card) => {
    const matchesSource = source === 'all' || card.dataset.company === source;
    const haystack = `${card.dataset.title} ${card.dataset.summary} ${card.dataset.company.toLowerCase()}`;
    const matchesQuery = !query || haystack.includes(query);
    card.style.display = matchesSource && matchesQuery ? '' : 'none';
  });
};

searchInput.addEventListener('input', applyFilters);
sourceFilter.addEventListener('change', applyFilters);
clearFilters.addEventListener('click', () => {
  searchInput.value = '';
  sourceFilter.value = 'all';
  applyFilters();
});

themeToggle.addEventListener('click', () => {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', current);
  localStorage.setItem('theme', current);
});

const storedTheme = localStorage.getItem('theme');
if (storedTheme) {
  document.documentElement.setAttribute('data-theme', storedTheme);
}

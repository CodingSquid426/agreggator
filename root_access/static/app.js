const searchInput = document.getElementById('searchInput');
const sourceFilter = document.getElementById('sourceFilter');
const clearFilters = document.getElementById('clearFilters');
const cards = [...document.querySelectorAll('.card')];
const themeToggle = document.getElementById('themeToggle');
const settingsToggle = document.getElementById('settingsToggle');
const settingsPanel = document.getElementById('settingsPanel');
const paletteSelect = document.getElementById('paletteSelect');
const feedPills = document.getElementById('feedPills');
const showCompanyFeeds = document.getElementById('showCompanyFeeds');
const companyPills = [...document.querySelectorAll('[data-company-pill]')];

const applyFilters = () => {
  const query = searchInput.value.trim().toLowerCase();
  const source = sourceFilter.value;

  cards.forEach((card) => {
    const matchesSource = source === 'all' || card.dataset.company === source;
    const haystack = `${card.dataset.title} ${card.dataset.summary} ${card.dataset.company.toLowerCase()}`;
    const matchesQuery = !query || haystack.includes(query);
    card.style.display = matchesSource && matchesQuery ? '' : 'none';
  });

  companyPills.forEach((pill) => {
    pill.classList.toggle('active', source === pill.dataset.companyPill);
  });
};

searchInput.addEventListener('input', applyFilters);
sourceFilter.addEventListener('change', applyFilters);
clearFilters.addEventListener('click', () => {
  searchInput.value = '';
  sourceFilter.value = 'all';
  applyFilters();
});

companyPills.forEach((pill) => {
  pill.addEventListener('click', () => {
    sourceFilter.value = sourceFilter.value === pill.dataset.companyPill ? 'all' : pill.dataset.companyPill;
    applyFilters();
  });
});

themeToggle.addEventListener('click', () => {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', current);
  localStorage.setItem('theme', current);
});

settingsToggle.addEventListener('click', () => {
  settingsPanel.hidden = !settingsPanel.hidden;
});

paletteSelect.addEventListener('change', () => {
  document.documentElement.setAttribute('data-palette', paletteSelect.value);
  localStorage.setItem('palette', paletteSelect.value);
});

showCompanyFeeds.addEventListener('change', () => {
  feedPills.hidden = !showCompanyFeeds.checked;
  localStorage.setItem('showCompanyFeeds', String(showCompanyFeeds.checked));
});

const storedTheme = localStorage.getItem('theme');
if (storedTheme) {
  document.documentElement.setAttribute('data-theme', storedTheme);
}
const storedPalette = localStorage.getItem('palette');
if (storedPalette) {
  document.documentElement.setAttribute('data-palette', storedPalette);
  paletteSelect.value = storedPalette;
}
const storedShowCompanyFeeds = localStorage.getItem('showCompanyFeeds');
if (storedShowCompanyFeeds !== null) {
  const enabled = storedShowCompanyFeeds === 'true';
  showCompanyFeeds.checked = enabled;
  feedPills.hidden = !enabled;
}

applyFilters();

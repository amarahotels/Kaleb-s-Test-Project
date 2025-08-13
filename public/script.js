// footer year
const y = document.getElementById('year');
if (y) y.textContent = new Date().getFullYear();

// refs
const listEl = document.getElementById('placeList');
const errorEl = document.getElementById('placesError');
const sortSel = document.getElementById('sortSelect');
const minRatingSel = document.getElementById('minRating');
const typeSel = document.getElementById('typeFilter');

let allPlaces = [];
let selectedType = 'all';

// ---- Hawker detection config (keep all lowercase) ----
const hawkerNameSet = new Set([
  'lau pa sat',
  'maxwell food centre',
  'maxwell food center',
  'amoy street food centre',
  'amoy street food center',
  'chinatown complex',
  'chinatown hawker center',
  'chinatown hawker centre'
]);

// Phrases that indicate a hawker in the address
const HAWKER_ADDRESS_RE =
  /(food\s*centre|food\s*center|hawker\s*centre|hawker\s*center|hawker|market)/i;

// Name-based categorization (word-boundary where sensible)
const NAME_IS_CAFE_RE =
  /\b(café|cafe|coffee|espresso|roastery|coffee\s*bar|bakery)\b/i;
const NAME_IS_BAR_RE =
  /\b(bar|pub|taproom|wine\s*bar|speakeasy)\b/i;
const NAME_IS_RESTAURANT_RE =
  /\b(restaurant|ristorante|trattoria|bistro|eatery|osteria|cantina|kitchen|diner)\b/i;

// load latest JSON (cache-busted)
async function loadPlaces() {
  try {
    const res = await fetch(`data/places.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // handle { meta, places } or legacy plain array
    allPlaces = Array.isArray(data.places) ? data.places : (Array.isArray(data) ? data : []);

    render();
  } catch (e) {
    console.error('Failed to fetch places.json', e);
    if (errorEl) errorEl.classList.remove('hidden');
  }
}

// --- Category helpers ---
function isHawker(p) {
  const name = (p.name || '').toLowerCase().trim();
  const addr = (p.address || '').toLowerCase().trim();
  const primary = (p.primary_type || '').toLowerCase();
  const types = (p.types || []).map(t => (t || '').toLowerCase());

  const nameHit = [...hawkerNameSet].some(h => name.includes(h));
  const addrHit = HAWKER_ADDRESS_RE.test(addr);
  const metaHit =
    primary.includes('food_court') ||
    types.some(t => t.includes('food_court') || t.includes('market'));

  return nameHit || addrHit || metaHit;
}

// Name-first classifier returning 'cafes' | 'bars' | 'restaurants' | null
function classifyByName(p) {
  const name = p.name || '';
  if (NAME_IS_CAFE_RE.test(name)) return 'cafes';
  if (NAME_IS_BAR_RE.test(name)) return 'bars';
  if (NAME_IS_RESTAURANT_RE.test(name)) return 'restaurants';
  return null;
}

function metaSaysCafe(p) {
  const primary = (p.primary_type || '').toLowerCase();
  const types = (p.types || []).map(t => (t || '').toLowerCase());
  return primary.includes('cafe') || types.some(t => t.includes('cafe') || t.includes('coffee_shop'));
}

function metaSaysBar(p) {
  const primary = (p.primary_type || '').toLowerCase();
  const types = (p.types || []).map(t => (t || '').toLowerCase());
  return primary.includes('bar') || types.some(t => t.includes('bar') || t.includes('wine_bar') || t.includes('pub'));
}

function metaSaysRestaurant(p) {
  const primary = (p.primary_type || '').toLowerCase();
  const types = (p.types || []).map(t => (t || '').toLowerCase());
  return primary.includes('restaurant') || types.some(t => t.includes('restaurant'));
}

function isCafe(p) {
  if (isHawker(p)) return false;
  const byName = classifyByName(p);
  if (byName) return byName === 'cafes';
  return metaSaysCafe(p);
}

function isBar(p) {
  if (isHawker(p)) return false;
  const byName = classifyByName(p);
  if (byName) return byName === 'bars';
  return metaSaysBar(p);
}

function isRestaurant(p) {
  if (isHawker(p)) return false;
  const byName = classifyByName(p);
  if (byName) return byName === 'restaurants';
  return metaSaysRestaurant(p);
}

// render cards with image overlay + controls
function render() {
  if (!listEl) return;
  if (errorEl) errorEl.classList.add('hidden');

  const minR = parseFloat(minRatingSel?.value || '0');

  let items = allPlaces.filter(p => {
    const r = num(p.rating);
    const passRating = Number.isFinite(r) ? r >= minR : true;

    const passType =
      selectedType === 'all' ||
      (selectedType === 'hawker' && isHawker(p)) ||
      (selectedType === 'cafes' && isCafe(p)) ||
      (selectedType === 'bars' && isBar(p)) ||
      (selectedType === 'restaurants' && isRestaurant(p));

    return passRating && passType;
  });

  // sort
  const sort = sortSel?.value || 'ratingDesc';
  if (sort === 'ratingDesc') {
    items.sort((a, b) => num(b.rating) - num(a.rating));
  } else {
    items.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  }

  // limit
  items = items.slice(0, 60);

  listEl.innerHTML = items.map(cardHtml).join('') ||
    `<div class="notice">No places found.</div>`;
}

function cardHtml(p) {
  const name = esc(p.name || 'Unknown');
  const addr = esc(p.address || '');
  const rating = p.rating ? `${p.rating}★` : '';

  const imgBlock = p.photo_url ? `
    <div class="thumb-wrap">
      <img class="thumb" src="${p.photo_url}" alt="${name}" loading="lazy">
      ${rating ? `<span class="rating-pill">${rating}</span>` : ''}
    </div>` : '';

  const meta = !p.photo_url && rating ? `<span class="rating-pill" style="position:static;margin-left:8px">${rating}</span>` : '';

  return `
    <article class="card">
      ${imgBlock}
      <div class="title">${name}${meta}</div>
      <div class="addr">${addr}</div>
      <div class="actions">
        ${p.maps_url ? `<a class="btn-link" href="${p.maps_url}" target="_blank" rel="noopener">Open in Google Maps</a>` : ''}
      </div>
    </article>
  `;
}

const num = v => Number.isFinite(v) ? v : parseFloat(v);
function esc(s = '') {
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

sortSel?.addEventListener('change', render);
minRatingSel?.addEventListener('change', render);

// category change
typeSel?.addEventListener('change', () => {
  selectedType = typeSel.value; // 'all' | 'restaurants' | 'cafes' | 'bars' | 'hawker'
  render();
});

// NAV TOGGLE
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const tab = btn.dataset.tab;
    document.getElementById('places').classList.toggle('hidden', tab !== 'places');
    document.getElementById('events').classList.toggle('hidden', tab !== 'events');
  });
});

// LOAD EVENTS
async function loadEvents() {
  try {
    const res = await fetch(`data/events.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const events = data?.events || [];
    renderEvents(events);
  } catch (e) {
    console.error('Failed to fetch events.json', e);
    document.getElementById('eventsError')?.classList.remove('hidden');
  }
}

// RENDER EVENTS
function renderEvents(events) {
  const list = document.getElementById('eventList');
  if (!list) return;

  const parseDate = (d) => {
    if (!d) return null;
    const parsed = Date.parse(d);
    return isNaN(parsed) ? null : new Date(parsed);
  };

  // Sort by start date (ascending)
  events.sort((a, b) => {
    const dateA = parseDate(a.start);
    const dateB = parseDate(b.start);
    if (!dateA) return 1;
    if (!dateB) return -1;
    return dateA - dateB;
  });

  list.innerHTML = events.slice(0, 24).map(e => `
    <article class="card">
      ${e.image ? `<div class="thumb-wrap"><img class="thumb" src="${e.image}" alt="${esc(e.title)}" loading="lazy"></div>` : ''}
      <div class="title">${esc(e.title)}</div>
      <div class="addr">${esc(e.venue?.join(', ') || e.venue || '')}</div>
      <div class="addr"><b>${esc(e.start || '')}</b></div>
      <div class="actions">
        ${e.url ? `<a class="btn-link" href="${e.url}" target="_blank">Event Link</a>` : ''}
      </div>
    </article>
  `).join('') || `<div class="notice">No events found.</div>`;
}

loadEvents();
loadPlaces();

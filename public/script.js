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
// Alcohol cue → also counts as “bar”
const NAME_ALCOHOL_RE =
  /\b(cocktail|cocktails|wine|beer|ale|lager|ipa|stout|porter|whisky|whiskey|gin|rum|tequila|mezcal|soju|sake|spirits|liqueur)\b/i;
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

/**
 * Categorize a place with multi-tag logic.
 * Returns a Set with any of: 'restaurants', 'cafes', 'bars'
 * Hawkers are handled separately and never mixed.
 *
 * Rules:
 * 1) First look at the NAME — add tags found there.
 * 2) If NAME had no tags, fall back to PRIMARY TYPE.
 * 3) Ignore extra categories from `types` unless the NAME also suggests them.
 * 4) If primary_type is decisively one category (e.g., 'bar') and
 *    name does NOT suggest another category, do not add the other from `types`.
 */
function categorize(p) {
  const tags = new Set();
  const name = p.name || '';
  const primary = (p.primary_type || '').toLowerCase();
  const types = (p.types || []).map(t => (t || '').toLowerCase());

  // 1) NAME signals (highest priority)
  const nameSaysCafe = NAME_IS_CAFE_RE.test(name);
  const nameSaysBar = NAME_IS_BAR_RE.test(name) || NAME_ALCOHOL_RE.test(name);
  const nameSaysRestaurant = NAME_IS_RESTAURANT_RE.test(name);

  if (nameSaysCafe) tags.add('cafes');
  if (nameSaysBar) tags.add('bars');
  if (nameSaysRestaurant) tags.add('restaurants');

  // 2) If nothing from name, fall back to PRIMARY TYPE
  if (tags.size === 0) {
    if (primary.includes('cafe')) tags.add('cafes');
    if (primary.includes('bar')) tags.add('bars');
    if (primary.includes('restaurant')) tags.add('restaurants');
  } else {
    // If name already picked categories, we still allow primary
    // to reinforce them (no-op since Set), but we DO NOT add other
    // categories just because `types` includes them.
    if (primary.includes('cafe')) tags.add('cafes');
    if (primary.includes('bar')) tags.add('bars');
    if (primary.includes('restaurant')) tags.add('restaurants');
  }

  // 3) Only use `types` to add a category if the NAME also suggests that category.
  //    This prevents cases like “Oriental Elixir” (primary: bar, types include restaurant)
  //    from leaking into Restaurants when the name doesn’t say so.
  if (nameSaysCafe && types.some(t => t.includes('cafe') || t.includes('coffee_shop'))) {
    tags.add('cafes');
  }
  if (nameSaysBar && types.some(t => t.includes('bar') || t.includes('wine_bar') || t.includes('pub'))) {
    tags.add('bars');
  }
  if (nameSaysRestaurant && types.some(t => t.includes('restaurant'))) {
    tags.add('restaurants');
  }

  return tags;
}

// render cards with image overlay + controls
function render() {
  if (!listEl) return;
  if (errorEl) errorEl.classList.add('hidden');

  const minR = parseFloat(minRatingSel?.value || '0');

  let items = allPlaces.filter(p => {
    const r = num(p.rating);
    const passRating = Number.isFinite(r) ? r >= minR : true;

    // Hawkers are exclusive
    if (selectedType === 'hawker') return passRating && isHawker(p);

    // Non-hawker categories
    if (isHawker(p)) return false;

    const tags = categorize(p); // Set('restaurants'|'cafes'|'bars')
    const passType =
      selectedType === 'all' ||
      (selectedType === 'restaurants' && tags.has('restaurants')) ||
      (selectedType === 'cafes' && tags.has('cafes')) ||
      (selectedType === 'bars' && tags.has('bars'));

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
  items = items.slice(0, 24);

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

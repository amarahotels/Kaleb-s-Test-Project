// footer year
const y = document.getElementById('year');
if (y) y.textContent = new Date().getFullYear();

// refs
const listEl = document.getElementById('placeList');
const errorEl = document.getElementById('placesError');
const sortSel = document.getElementById('sortSelect');
const minRatingSel = document.getElementById('minRating');

let allPlaces = [];

// load latest JSON (cache-busted)
async function loadPlaces() {
  try {
    const res = await fetch(`data/places.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allPlaces = Array.isArray(data) ? data : [];
    render();
  } catch (e) {
    console.error('Failed to fetch places.json', e);
    if (errorEl) errorEl.classList.remove('hidden');
  }
}

// render cards with image overlay + controls
function render() {
  if (!listEl) return;
  if (errorEl) errorEl.classList.add('hidden');

  // filter by rating
  const minR = parseFloat(minRatingSel?.value || '0');
  let items = allPlaces.filter(p => {
    const r = num(p.rating);
    return Number.isFinite(r) ? r >= minR : true;
  });

  // sort
  const sort = sortSel?.value || 'ratingDesc';
  if (sort === 'ratingDesc') {
    items.sort((a,b) => num(b.rating) - num(a.rating));
  } else {
    items.sort((a,b) => (a.name || '').localeCompare(b.name || ''));
  }

  // brochure size
  items = items.slice(0, 24);

  listEl.innerHTML = items.map(cardHtml).join('') ||
    `<div class="notice">No places found.</div>`;
}

// build one card
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

// helpers
const num = v => Number.isFinite(v) ? v : parseFloat(v);
function esc(s=''){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

// events
sortSel?.addEventListener('change', render);
minRatingSel?.addEventListener('change', render);

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

function renderEvents(events) {
  const list = document.getElementById('eventList');
  if (!list) return;

  list.innerHTML = events.slice(0, 24).map(e => `
    <article class="card">
      ${e.image ? `<div class="thumb-wrap"><img class="thumb" src="${e.image}" alt="${esc(e.title)}" loading="lazy"></div>` : ''}
      <div class="title">${esc(e.title)}</div>
      <div class="addr">${esc(e.venue?.join(', ') || '')}</div>
      <div class="addr"><b>${esc(e.start || '')}</b></div>
      <div class="actions">
        ${e.url ? `<a class="btn-link" href="${e.url}" target="_blank">Event Link</a>` : ''}
      </div>
    </article>
  `).join('') || `<div class="notice">No events found.</div>`;
}

loadEvents();


// start
loadPlaces();

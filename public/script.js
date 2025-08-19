// footer year
const y = document.getElementById('year');
if (y) y.textContent = new Date().getFullYear();

// Refs
const listEl = document.getElementById('placeList');
const errorEl = document.getElementById('placesError');
const sortSel = document.getElementById('sortSelect');
const minRatingSel = document.getElementById('minRating');
const typeSel = document.getElementById('typeFilter');

// Top picks carousel refs
const topTrack = document.getElementById('topTrack');
const topPrev = document.getElementById('topPrev');
const topNext = document.getElementById('topNext');
const topSection = document.getElementById('topPicks');

// HERO slider refs
const heroSlidesEl = document.getElementById('heroSlides');
const heroDotsEl = document.getElementById('heroDots');
const heroPrev = document.getElementById('heroPrev');
const heroNext = document.getElementById('heroNext');
const heroEl = document.getElementById('hero');
const heroTitleEl = document.querySelector('.hero-overlay .brand-title');
const heroSubEl = document.querySelector('.hero-overlay .subtitle');
const scrollCue = document.querySelector('.scroll-cue');

// Events / attractions refs
const heroAttractionLink = document.getElementById('heroAttractionLink');
const eventCatSel = document.getElementById('eventCat');

let allPlaces = [];
let featuredAttractions = [];
let selectedType = 'all';
let allEventsData = [];
let selectedEventCat = 'all';
let heroMode = 'places';


// ---- Hawker detection config ----
const hawkerNameSet = new Set([
  'lau pa sat','maxwell food centre','maxwell food center',
  'amoy street food centre','amoy street food center',
  'chinatown complex','chinatown hawker center','chinatown hawker centre'
]);

// Name-based categorization
const NAME_IS_CAFE_RE = /\b(café|cafe|coffee|espresso|roastery|coffee\s*bar|bakery)\b/i;
const NAME_IS_BAR_RE = /\b(bar|pub|taproom|wine\s*bar|speakeasy)\b/i;
const NAME_ALCOHOL_RE = /\b(cocktail|cocktails|wine|beer|ale|lager|ipa|stout|porter|whisky|whiskey|gin|rum|tequila|mezcal|soju|sake|spirits|liqueur)\b/i;
const NAME_IS_RESTAURANT_RE = /\b(restaurant|ristorante|trattoria|bistro|eatery|osteria|cantina|kitchen|diner)\b/i;
const NAME_IS_BOOKSTORE_RE = /\b(bookstore|book\s*shop|book\s*store|books|comics|manga|书店|書店|书屋|書屋)\b/i;

// Load data (places)
async function loadPlaces() {
  try {
    const res = await fetch(`data/places.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allPlaces = Array.isArray(data.places) ? data.places : (Array.isArray(data) ? data : []);

    buildHeroFromPlaces(allPlaces);   // default hero (Places)
    renderTopPicks(allPlaces);
    render();
  } catch (e) {
    console.error('Failed to fetch places.json', e);
    if (errorEl) errorEl.classList.remove('hidden');
  }
}

// Load featured attractions (year-round)
async function loadAttractions() {
  try {
    const res = await fetch(`data/featured_attractions.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    featuredAttractions = Array.isArray(data.attractions) ? data.attractions : (Array.isArray(data) ? data : []);
  } catch (e) {
    console.warn('No featured_attractions.json yet or failed to load.', e);
  }
}

/* ---------- Helpers ---------- */
function isHawker(p) {
  if (typeof p.is_hawker_centre === 'boolean') return p.is_hawker_centre;
  const name = (p.name || '').toLowerCase().trim();
  const primary = (p.primary_type || '').toLowerCase();
  const types = (p.types || []).map(t => (t || '').toLowerCase());
  const canonicalNameHit = [...hawkerNameSet].some(h => name.includes(h));
  const metaHit = primary === 'food_court' || types.some(t => t === 'food_court');
  return canonicalNameHit || metaHit;
}
function categorize(p){
  const tags = new Set();
  const name = p.name || '';
  const primary = (p.primary_type || '').toLowerCase();
  const types = (p.types || []).map(t => (t || '').toLowerCase());

  const nameSaysCafe = NAME_IS_CAFE_RE.test(name);
  const nameSaysBar = NAME_IS_BAR_RE.test(name) || NAME_ALCOHOL_RE.test(name);
  const nameSaysRestaurant = NAME_IS_RESTAURANT_RE.test(name);
  const nameSaysBookstore = NAME_IS_BOOKSTORE_RE.test(name);

  if (nameSaysCafe) tags.add('cafes');
  if (nameSaysBar) tags.add('bars');
  if (nameSaysRestaurant) tags.add('restaurants');
  if (nameSaysBookstore) tags.add('bookstores');

  if (tags.size === 0) {
    if (primary.includes('cafe')) tags.add('cafes');
    if (primary.includes('bar')) tags.add('bars');
    if (primary.includes('restaurant')) tags.add('restaurants');
    if (primary.includes('book_store')) tags.add('bookstores');
  } else {
    if (primary.includes('cafe') && nameSaysCafe) tags.add('cafes');
    if (primary.includes('bar') && nameSaysBar) tags.add('bars');
    if (primary.includes('restaurant') && nameSaysRestaurant) tags.add('restaurants');
    if (primary.includes('book_store') && nameSaysBookstore) tags.add('bookstores');
  }

  if (nameSaysCafe && (p.types||[]).some(t => t.includes('cafe') || t.includes('coffee_shop'))) tags.add('cafes');
  if (nameSaysBar && (p.types||[]).some(t => t.includes('bar') || t.includes('wine_bar') || t.includes('pub'))) tags.add('bars');
  if (nameSaysRestaurant && (p.types||[]).some(t => t.includes('restaurant'))) tags.add('restaurants');
  if (nameSaysBookstore && (p.types||[]).some(t => t.includes('book_store'))) tags.add('bookstores');
  return tags;
}
function formatDistance(m){
  if (!Number.isFinite(m)) return '';
  if (m < 1000) return `${Math.round(m)} m`;
  const km = m / 1000;
  return `${km < 10 ? km.toFixed(1) : Math.round(km)} km`;
}
function topScore(p){
  const r = Number(p.rating) || 0;
  const n = Number(p.rating_count) || 0;
  const d = Number(p.distance_m);
  const C = 25, m = 4.3;
  const bayes = (C*m + n*r) / (C + n);
  const distBoost = Number.isFinite(d) ? Math.max(0, 1 - Math.min(d, 1200) / 1200) : 0;
  return bayes + distBoost;
}
function pickTopPicks(places, limit = 12){
  const candidates = places.filter(p => p.photo_url);
  const scored = [...candidates].sort((a,b)=> topScore(b) - topScore(a));
  const buckets = { restaurants:[], cafes:[], bars:[], bookstores:[], other:[] };
  for (const p of scored){
    const tags = categorize(p);
    let key = 'other';
    if (tags.has('restaurants')) key = 'restaurants';
    else if (tags.has('cafes')) key = 'cafes';
    else if (tags.has('bars')) key = 'bars';
    else if (tags.has('bookstores')) key = 'bookstores';
    buckets[key].push(p);
  }
  const order = ['restaurants','cafes','bars','bookstores','other'];
  const quotas = { restaurants:3, cafes:3, bars:3, bookstores:3 };
  const picks = [];
  for (const k of order){
    const q = quotas[k] || 0;
    for (let i=0; i<Math.min(q, buckets[k].length) && picks.length<limit; i++){
      picks.push(buckets[k][i]);
    }
  }
  for (const p of scored){
    if (picks.length >= limit) break;
    if (!picks.includes(p)) picks.push(p);
  }
  return picks.slice(0, limit);
}

function enableHeroSwipe() {
  if (!heroEl) return;
  let x0 = 0, y0 = 0;
  const THRESH = 40;

  heroEl.addEventListener('touchstart', e => {
    const t = e.touches[0]; x0 = t.clientX; y0 = t.clientY;
  }, { passive: true });

  heroEl.addEventListener('touchend', e => {
    const t = e.changedTouches[0];
    const dx = t.clientX - x0, dy = t.clientY - y0;
    if (Math.abs(dx) > THRESH && Math.abs(dx) > Math.abs(dy)) {
      dx < 0 ? showHero(heroIndex + 1, true) : showHero(heroIndex - 1, true);
    }
  }, { passive: true });
}

function updateHeroAttractionLink(){
  if (!heroAttractionLink) return;

  if (heroMode !== 'events') {
    heroAttractionLink.classList.add('hidden');
    return;
  }

  const slide = heroSlides[heroIndex];
  const href = slide?.dataset?.href;
  if (href) {
    heroAttractionLink.href = href;
    heroAttractionLink.textContent = '📍 Click for location';
    heroAttractionLink.classList.remove('hidden');
  } else {
    heroAttractionLink.classList.add('hidden');
  }
}



/* ---------- HERO SLIDER ---------- */
let heroIndex = 0, heroTimer = null, heroSlides = [];
let heroControlsBound = false;

function bindHeroControlsOnce(){
  if (heroControlsBound) return;
  heroPrev?.addEventListener('click', ()=> showHero(heroIndex-1, true));
  heroNext?.addEventListener('click', ()=> showHero(heroIndex+1, true));
  startHeroAuto();
  heroEl?.addEventListener('mouseenter', stopHeroAuto);
  heroEl?.addEventListener('mouseleave', startHeroAuto);
  heroEl?.addEventListener('focusin', stopHeroAuto);
  heroEl?.addEventListener('focusout', startHeroAuto);

  // Clicking the HERO opens the current attraction on Events tab
  heroEl?.addEventListener('click', (e)=>{
    if (e.target.closest('.nav-btn, .hs-arrow, .hs-dot')) return;
    if (heroMode !== 'events') return;                   // ← only in Events
    const slide = heroSlides[heroIndex];
    const href = slide?.dataset?.href;
    if (href) window.open(href, '_blank', 'noopener');
  });


  enableHeroSwipe();

  heroControlsBound = true;
}

function rebuildDots(count){
  if (!heroDotsEl) return;
  heroDotsEl.innerHTML = Array.from({length: count}).map((_,i)=>
    `<button class="hs-dot${i===0?' is-active':''}" role="tab" aria-selected="${i===0?'true':'false'}" aria-label="Slide ${i+1}"></button>`
  ).join('');
  [...heroDotsEl.children].forEach((dot, i)=> dot.addEventListener('click', ()=> showHero(i, true)));
}

function buildHeroFromPlaces(all){
  if (!heroSlidesEl) return;

  const picks = [...all].filter(p => p.photo_url).sort((a,b)=> topScore(b) - topScore(a)).slice(0, 6);

  heroSlidesEl.innerHTML = picks.map((p, i) =>
    `<div class="hs-slide${i===0 ? ' is-active':''}" role="img" aria-label="${esc(p.name || '')}"
       style="background-image:url('${p.photo_url}')"></div>`
  ).join('');
  heroSlides = [...heroSlidesEl.querySelectorAll('.hs-slide')];

  rebuildDots(heroSlides.length);
  bindHeroControlsOnce();
  showHero(0);

  // Places-mode copy + scroll cue
  if (heroTitleEl) heroTitleEl.innerHTML = `Explore Around <span class="brand">Amara</span>`;
  if (heroSubEl) heroSubEl.textContent = 'Handpicked nearby places for staff & guests near Tanjong Pagar.';
  if (scrollCue) scrollCue.setAttribute('href', '#places');

  heroMode = 'places';
  heroAttractionLink?.classList.add('hidden');

}

function buildEventsHero(attractions){
  if (!heroSlidesEl) return;

  const picks = [...attractions]
    .filter(a => (a.image_url || a.photo_url || a.image))
    .slice(0, 12);

  heroSlidesEl.innerHTML = picks.map((a,i)=>{
    const img = a.image_url || a.photo_url || a.image || '';
    const name = esc(a.name || '');
    const href = a.maps_url || a.website || '';
    return `
      <div class="hs-slide${i===0?' is-active':''}" role="img"
           aria-label="${name}"
           data-href="${esc(href)}"
           style="background-image:url('${img}')"></div>
    `;
  }).join('');

  heroSlides = [...heroSlidesEl.querySelectorAll('.hs-slide')];
  rebuildDots(heroSlides.length);
  bindHeroControlsOnce();

  heroMode = 'events';
  showHero(0);
  updateHeroAttractionLink();

  if (heroTitleEl) heroTitleEl.textContent = `What’s On in Singapore`;
  if (heroSubEl) heroSubEl.textContent = 'Signature year-round attractions & family-friendly hits.';
  if (scrollCue) scrollCue.setAttribute('href', '#events');
}


function showHero(nextIndex, userTriggered=false){
  if (!heroSlides.length) return;
  const count = heroSlides.length;
  heroIndex = (nextIndex + count) % count;
  heroSlides.forEach((el,i)=> el.classList.toggle('is-active', i===heroIndex));
  if (heroDotsEl){
    [...heroDotsEl.children].forEach((d,i)=>{
      d.classList.toggle('is-active', i===heroIndex);
      d.setAttribute('aria-selected', i===heroIndex ? 'true':'false');
    });
  }
  if (userTriggered){ restartHeroAuto(); }

  updateHeroAttractionLink();
}
function startHeroAuto(){ stopHeroAuto(); heroTimer = setInterval(()=> showHero(heroIndex+1, false), 6000); }
function stopHeroAuto(){ if (heroTimer) clearInterval(heroTimer); heroTimer = null; }
function restartHeroAuto(){ stopHeroAuto(); startHeroAuto(); }

/* ---------- TOP PICKS CAROUSEL ---------- */
function renderTopPicks(all){
  if (!topTrack || !topSection) return;
  const items = pickTopPicks(all, 12);
  if (!items.length){ topSection.classList.add('hidden'); return; }
  topSection.classList.remove('hidden');
  topTrack.innerHTML = items.map(topSlideHtml).join('');
  const step = () => topTrack.clientWidth * 0.9;
  topPrev?.addEventListener('click', () => topTrack.scrollBy({ left: -step(), behavior:'smooth'}));
  topNext?.addEventListener('click', () => topTrack.scrollBy({ left:  step(), behavior:'smooth'}));
}
function topSlideHtml(p){
  const name = esc(p.name || '');
  const dist = Number.isFinite(p.distance_m) ? formatDistance(p.distance_m) : '';
  const rating = p.rating ? `${p.rating}★` : '';
  const meta = [rating, dist].filter(Boolean).join(' · ');
  return `
    <a class="slide" href="${p.maps_url || '#'}" target="_blank" rel="noopener">
      <img class="thumb" src="${p.photo_url}" alt="${name}" loading="lazy">
      <div class="meta">
        <div class="name">${name}</div>
        ${meta ? `<span class="pill">${meta}</span>` : ''}
      </div>
    </a>
  `;
}

/* ---------- GRID RENDER ---------- */
function render(){
  if (!listEl) return;
  if (errorEl) errorEl.classList.add('hidden');
  const minR = parseFloat(minRatingSel?.value || '0');

  let items = allPlaces.filter(p => {
    const r = num(p.rating);
    const passRating = Number.isFinite(r) ? r >= minR : true;
    if (!p.photo_url) return false;
    if (selectedType === 'hawker') return passRating && isHawker(p);
    if (isHawker(p)) return false;
    const tags = categorize(p);
    const passType =
      selectedType === 'all' ||
      (selectedType === 'restaurants' && tags.has('restaurants')) ||
      (selectedType === 'cafes' && tags.has('cafes')) ||
      (selectedType === 'bars' && tags.has('bars')) ||
      (selectedType === 'bookstores' && tags.has('bookstores'));
    return passRating && passType;
  });

  const sort = sortSel?.value || 'ratingDesc';
  if (sort === 'ratingDesc') items.sort((a,b)=> num(b.rating) - num(a.rating));
  else if (sort === 'distanceAsc') items.sort((a,b)=> (num(a.distance_m)||1e12) - (num(b.distance_m)||1e12));
  else items.sort((a,b)=> (a.name||'').localeCompare(b.name||''));

  items = items.slice(0, 24);
  listEl.innerHTML = items.map(cardHtml).join('') || `<div class="notice">No places found.</div>`;
}
function cardHtml(p){
  const name = esc(p.name || 'Unknown');
  const addr = esc(p.address || '');
  const rating = p.rating ? `${p.rating}★` : '';
  const dist = Number.isFinite(p.distance_m) ? formatDistance(p.distance_m) : '';
  const pillRight = [rating, dist].filter(Boolean).join(' · ');
  const imgBlock = p.photo_url ? `
    <div class="thumb-wrap">
      <img class="thumb" src="${p.photo_url}" alt="${name}" loading="lazy">
      ${pillRight ? `<span class="rating-pill">${pillRight}</span>` : ''}
    </div>` : '';
  return `
    <article class="card">
      ${imgBlock}
      <div class="title">${name}</div>
      <div class="addr">${addr}</div>
      <div class="actions">
        ${p.maps_url ? `<a class="btn-link" href="${p.maps_url}" target="_blank" rel="noopener">Open in Google Maps</a>` : ''}
      </div>
    </article>
  `;
}

// utils
const num = v => Number.isFinite(v) ? v : parseFloat(v);
function esc(s=''){ return s.replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
const toText = (v) => Array.isArray(v) ? v.filter(Boolean).join(', ')
  : (v && typeof v === 'object')
    ? (['name','address','line1','line2','city'].map(k => v[k]).filter(Boolean).join(', ') || String(v))
    : (v ?? '');

// ---------- Events ----------
async function loadEvents(){
  try{
    const res = await fetch(`data/events.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allEventsData = data?.events || [];
    renderEvents(allEventsData);
  }catch(e){
    console.error('Failed to fetch events.json', e);
    document.getElementById('eventsError')?.classList.remove('hidden');
  }
}
function renderEvents(events){
  const list = document.getElementById('eventList');
  if (!list) return;

  let items = events;
  if (selectedEventCat !== 'all') {
    items = items.filter(e => ((e.category || 'general') + '').toLowerCase() === selectedEventCat);
  }
  items = items.filter(e => typeof e.image === 'string' && e.image.trim().length > 0);

  const parseDate = d => (d && !isNaN(Date.parse(d))) ? new Date(d) : null;
  items.sort((a,b)=>{
    const A = parseDate(a.start), B = parseDate(b.start);
    if (!A) return 1; if (!B) return -1; return A - B;
  });

  list.innerHTML = items.slice(0,24).map(e=>`
    <article class="card">
      <div class="thumb-wrap">
        <img class="thumb event-img" src="${e.image}" alt="${esc(e.title)}" loading="lazy">
      </div>
      <div class="title">${esc(e.title)}</div>
      <div class="addr">${esc(toText(e.venue) || toText(e.address))}</div>
      <div class="addr"><b>${esc(e.start || '')}</b></div>
      <div class="actions">
        ${e.url ? `<a class="btn-link" href="${e.url}" target="_blank" rel="noopener">Event Link</a>` : ''}
      </div>
    </article>
  `).join('') || `<div class="notice">No events found.</div>`;

  pruneBrokenEventImages(list);
}
function pruneBrokenEventImages(root){
  root.querySelectorAll('img.event-img').forEach(img => {
    const removeCard = () => img.closest('article.card')?.remove();
    img.addEventListener('error', removeCard, { once: true });
    img.addEventListener('load', () => {
      if (img.naturalWidth <= 2 || img.naturalHeight <= 2) removeCard();
    }, { once: true });
    if (img.complete) {
      queueMicrotask(() => {
        if (img.naturalWidth <= 2 || img.naturalHeight <= 2) removeCard();
      });
    }
  });
}

// Events category change -> re-render
eventCatSel?.addEventListener('change', ()=>{
  selectedEventCat = eventCatSel.value;
  renderEvents(allEventsData);
});

/* ---------- Nav: swap hero on tab change ---------- */
document.querySelectorAll('.nav-btn').forEach(btn=>{
  btn.addEventListener('click', async ()=>{
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;

    const placesSec = document.getElementById('places');
    const eventsSec = document.getElementById('events');
    const isEvents = tab === 'events';

    placesSec.classList.toggle('hidden', isEvents);
    eventsSec.classList.toggle('hidden', !isEvents);
    topSection?.classList.toggle('hidden', isEvents); // hide Top picks on Events

    if (isEvents) {
      if (!featuredAttractions.length) await loadAttractions();
      if (featuredAttractions.length) buildEventsHero(featuredAttractions);
      else buildHeroFromPlaces(allPlaces); // graceful fallback
    } else {
      buildHeroFromPlaces(allPlaces);
    }
  });
});

// ===== Filters accordion (phones) =====
(function initFiltersAccordion() {
  const toggle = document.querySelector('.filters-toggle');
  const body   = document.getElementById('filtersBody');

  if (!toggle || !body) return;

  // Helper to set state
  function setOpen(isOpen) {
    body.style.display = isOpen ? 'block' : 'none';
    toggle.setAttribute('aria-expanded', String(isOpen));
    toggle.textContent = isOpen ? 'Hide' : 'Show';
  }

  // Initial state: collapsed on small screens, open otherwise (CSS also handles this)
  const mq = window.matchMedia('(min-width: 640px)');
  setOpen(mq.matches);            // open if ≥640px

  toggle.addEventListener('click', () => setOpen(body.style.display !== 'block'));

  // Keep it in sync if the user rotates/resizes
  mq.addEventListener?.('change', e => setOpen(e.matches));
})();


// kick off
loadAttractions();   // prefetch for snappy swap
loadEvents();
loadPlaces();

// tiny version marker
console.info("script.js events-hero fix v2");

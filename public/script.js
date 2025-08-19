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

// Events filter ref
const eventCatSel = document.getElementById('eventCat');

// NEW: Year-round attractions carousel refs (Events tab)
const attrTrack   = document.getElementById('attrTrack');
const attrPrev    = document.getElementById('attrPrev');
const attrNext    = document.getElementById('attrNext');
const attrSection = document.getElementById('attractionsSection');

let allPlaces = [];
let selectedType = 'all';
let allEventsData = [];
let selectedEventCat = 'all';

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

// Load data
async function loadPlaces() {
  try {
    const res = await fetch(`data/places.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    allPlaces = Array.isArray(data.places) ? data.places : (Array.isArray(data) ? data : []);

    buildHeroSlider(allPlaces);   // full-viewport hero carousel
    renderTopPicks(allPlaces);
    render();
  } catch (e) {
    console.error('Failed to fetch places.json', e);
    if (errorEl) errorEl.classList.remove('hidden');
  }
}

// Helpers
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

  if (nameSaysCafe && types.some(t => t.includes('cafe') || t.includes('coffee_shop'))) tags.add('cafes');
  if (nameSaysBar && types.some(t => t.includes('bar') || t.includes('wine_bar') || t.includes('pub'))) tags.add('bars');
  if (nameSaysRestaurant && types.some(t => t.includes('restaurant'))) tags.add('restaurants');
  if (nameSaysBookstore && types.some(t => t.includes('book_store'))) tags.add('bookstores');
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

/* ---------- HERO SLIDER ---------- */
let heroIndex = 0, heroTimer = null, heroSlides = [];

function buildHeroSlider(all){
  if (!heroSlidesEl) return;

  // pick 4–6 best items with photos; prefer closer ones
  const picks = [...all]
    .filter(p => p.photo_url)
    .sort((a,b)=> topScore(b) - topScore(a))
    .slice(0, 6);

  heroSlidesEl.innerHTML = picks.map((p, i) =>
    `<div class="hs-slide${i===0 ? ' is-active':''}" role="img" aria-label="${esc(p.name || '')}"
       style="background-image:url('${p.photo_url}')"></div>`
  ).join('');

  // Dots
  if (heroDotsEl){
    heroDotsEl.innerHTML = picks.map((_,i)=>
      `<button class="hs-dot${i===0?' is-active':''}" role="tab" aria-selected="${i===0?'true':'false'}" aria-label="Slide ${i+1}"></button>`
    ).join('');
    [...heroDotsEl.children].forEach((dot, i)=>{
      dot.addEventListener('click', ()=> showHero(i, true));
    });
  }

  heroSlides = [...heroSlidesEl.querySelectorAll('.hs-slide')];

  // arrows
  heroPrev?.addEventListener('click', ()=> showHero(heroIndex-1, true));
  heroNext?.addEventListener('click', ()=> showHero(heroIndex+1, true));

  // autoplay
  startHeroAuto();

  // pause on hover / focus
  heroEl?.addEventListener('mouseenter', stopHeroAuto);
  heroEl?.addEventListener('mouseleave', startHeroAuto);
  heroEl?.addEventListener('focusin', stopHeroAuto);
  heroEl?.addEventListener('focusout', startHeroAuto);

  // swipe
  addSwipe(heroEl, (dir)=>{
    if (dir === 'left') showHero(heroIndex+1, true);
    if (dir === 'right') showHero(heroIndex-1, true);
  });
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
}
function startHeroAuto(){
  stopHeroAuto();
  heroTimer = setInterval(()=> showHero(heroIndex+1, false), 6000);
}
function stopHeroAuto(){ if (heroTimer) clearInterval(heroTimer); heroTimer = null; }
function restartHeroAuto(){ stopHeroAuto(); startHeroAuto(); }
function addSwipe(el, cb){
  let x0=null, y0=null;
  el.addEventListener('touchstart', e=>{ const t=e.touches[0]; x0=t.clientX; y0=t.clientY; }, {passive:true});
  el.addEventListener('touchend', e=>{
    if (x0==null) return;
    const t=e.changedTouches[0];
    const dx = t.clientX - x0; const dy = t.clientY - y0;
    if (Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy)){ cb(dx<0 ? 'left':'right'); }
    x0 = y0 = null;
  }, {passive:true});
}

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
    if (!p.photo_url) return false;           // photo required
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
// safely stringify possible array/string/object for venue/address
const toText = (v) => Array.isArray(v) ? v.filter(Boolean).join(', ')
  : (v && typeof v === 'object')
    ? (['name','address','line1','line2','city'].map(k => v[k]).filter(Boolean).join(', ') || String(v))
    : (v ?? '');

// filter listeners (Places)
sortSel?.addEventListener('change', render);
minRatingSel?.addEventListener('change', render);
typeSel?.addEventListener('change', ()=>{ selectedType = typeSel.value; render(); });

// nav toggle
document.querySelectorAll('.nav-btn').forEach(btn=>{
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    const tab = btn.dataset.tab;
    document.getElementById('places').classList.toggle('hidden', tab !== 'places');
    document.getElementById('events').classList.toggle('hidden', tab !== 'events');
  });
});

// -------------------- Events list --------------------
async function loadEvents(){
  try{
    const res = await fetch(`data/events.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    // store & render (so category filter can re-render without refetching)
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

  // 1) category filter
  let items = events;
  if (selectedEventCat !== 'all') {
    items = items.filter(e => ((e.category || 'general') + '').toLowerCase() === selectedEventCat);
  }

  // 2) cheap prefilter: has a non-empty image URL
  items = items.filter(e => typeof e.image === 'string' && e.image.trim().length > 0);

  // 3) sort by start date
  const parseDate = d => (d && !isNaN(Date.parse(d))) ? new Date(d) : null;
  items.sort((a,b)=>{
    const A = parseDate(a.start), B = parseDate(b.start);
    if (!A) return 1; if (!B) return -1; return A - B;
  });

  // 4) render (note: event-img class)
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

  // 5) post-render prune: remove cards with broken/tiny images
  pruneBrokenEventImages(list);
}

// Remove event cards whose images 404 or load as tiny placeholders
function pruneBrokenEventImages(root){
  root.querySelectorAll('img.event-img').forEach(img => {
    const removeCard = () => img.closest('article.card')?.remove();

    // If the image fails to load → remove card
    img.addEventListener('error', removeCard, { once: true });

    // If it loads but is basically empty (1×1, etc.) → remove
    img.addEventListener('load', () => {
      if (img.naturalWidth <= 2 || img.naturalHeight <= 2) removeCard();
    }, { once: true });

    // If already cached/complete, check immediately
    if (img.complete) {
      queueMicrotask(() => {
        if (img.naturalWidth <= 2 || img.naturalHeight <= 2) removeCard();
      });
    }
  });
}

// Events category change -> re-render
eventCatSel?.addEventListener('change', ()=>{
  selectedEventCat = eventCatSel.value;     // 'all' | 'family' | 'music' | 'general'
  renderEvents(allEventsData);
});

/* ---------- Year-round Attractions (Events tab, from JSON) ---------- */
async function loadAttractions(){
  if (!attrTrack || !attrSection) return;
  try{
    const res = await fetch(`data/featured_attractions.json?ts=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.json();
    // Accept either {attractions:[...]} or bare array
    let items = Array.isArray(raw?.attractions) ? raw.attractions : (Array.isArray(raw) ? raw : []);
    // keep only those with an image
    items = items.filter(a => (a.image || a.photo_url)?.trim());
    renderAttractions(items);
  }catch(e){
    // Hide the section quietly if file missing or bad
    attrSection.classList.add('hidden');
    console.warn('Attractions not loaded:', e.message || e);
  }
}

function renderAttractions(items){
  if (!items?.length){
    attrSection.classList.add('hidden');
    return;
  }
  attrSection.classList.remove('hidden');
  attrTrack.innerHTML = items.map(attrSlideHtml).join('');
  const step = () => attrTrack.clientWidth * 0.9;
  attrPrev?.addEventListener('click', () => attrTrack.scrollBy({ left: -step(), behavior:'smooth'}));
  attrNext?.addEventListener('click', () => attrTrack.scrollBy({ left:  step(), behavior:'smooth'}));
}

function attrSlideHtml(a){
  const name = esc(a.name || a.title || '');
  const img  = a.image || a.photo_url || '';
  const link = a.url || a.website || a.maps_url || '#';
  const meta = esc(toText(a.address) || '');
  return `
    <a class="slide" href="${link}" target="_blank" rel="noopener">
      <img class="thumb" src="${img}" alt="${name}" loading="lazy">
      <div class="meta">
        <div class="name">${name}</div>
        ${meta ? `<span class="pill">${meta}</span>` : ''}
      </div>
    </a>
  `;
}

loadEvents();
loadAttractions();   // NEW: fetch & render year-round attractions
loadPlaces();

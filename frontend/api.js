// =============================================================================
// api.js  –  Shared API client for AttendTrax frontend
// =============================================================================

// ── CHANGE this to your Render backend URL after deployment ────────────────
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://127.0.0.1:8000'
  : 'https://attendtrax-api.onrender.com';   // ← update after Render deploy

// ── Token storage ──────────────────────────────────────────────────────────
function saveAuth(data) {
  localStorage.setItem('at_token', data.access_token);
  localStorage.setItem('at_role',  data.role);
  localStorage.setItem('at_name',  data.name);
  localStorage.setItem('at_uid',   data.user_id);
  localStorage.setItem('at_class', data.class_id || '');
}

function getToken()   { return localStorage.getItem('at_token'); }
function getRole()    { return localStorage.getItem('at_role'); }
function getName()    { return localStorage.getItem('at_name'); }
function getUserId()  { return localStorage.getItem('at_uid'); }
function getClassId() { return localStorage.getItem('at_class'); }

function clearAuth() {
  ['at_token','at_role','at_name','at_uid','at_class'].forEach(k => localStorage.removeItem(k));
}

// ── Proactive Server Pre-warm & Warmup Telemetry ───────────────────────────
let _warmupPillEl = null;
let _warmupTimer = null;

function showWarmupPill(show, text = '⚡ Connecting to live server… (waking up cloud instance)') {
  if (typeof document === 'undefined') return;
  if (!_warmupPillEl) {
    _warmupPillEl = document.createElement('div');
    _warmupPillEl.id = 'server-warmup-pill';
    _warmupPillEl.className = 'server-warmup-pill';
    _warmupPillEl.innerHTML = `
      <span class="warmup-spinner"></span>
      <span class="warmup-text">${text}</span>
    `;
    document.body.appendChild(_warmupPillEl);
  }
  if (show) {
    _warmupPillEl.querySelector('.warmup-text').textContent = text;
    _warmupPillEl.classList.add('visible');
  } else {
    _warmupPillEl.classList.remove('visible');
  }
}

// Proactively ping server in background on script execution
function warmupServer() {
  try {
    fetch(`${API_BASE}/`, { method: 'GET', mode: 'cors' }).catch(() => {});
  } catch (e) {}
}
warmupServer();

// ── Performance Utilities: Debounce & Throttle ─────────────────────────────
function debounce(fn, delay = 250) {
  let timer = null;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}
window.debounce = debounce;

function throttle(fn, limit = 250) {
  let inThrottle = false;
  return function (...args) {
    if (!inThrottle) {
      fn.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}
window.throttle = throttle;

// ── In-memory Client Cache ──────────────────────────────────────────────────
const _apiCache = new Map();
const CLIENT_CACHE_TTL = 15000; // 15 seconds for static metadata

function clearClientCache() {
  _apiCache.clear();
}

// ── Core fetch wrapper with Cold-Start Resilience & Seamless Retries ──────
async function apiFetch(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const isGet = method === 'GET';
  
  // Real-time dynamic endpoints bypass stale local cache
  const isDynamicEndpoint = path.includes('/analytics') || 
                            path.includes('/attendance') || 
                            path.includes('/reports');
  const bypass = options.bypassCache === true || isDynamicEndpoint;

  if (isGet && !bypass) {
    const cached = _apiCache.get(path);
    if (cached && (Date.now() - cached.ts < CLIENT_CACHE_TTL)) {
      return cached.data;
    }
  }

  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  };

  // Start background warm-up indicator if request takes > 2.2s
  const warmupTimer = setTimeout(() => {
    showWarmupPill(true, '⚡ Waking up live cloud backend… Please hold on a moment.');
  }, 2200);

  let res;
  let lastErr = null;

  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
      });
      if (res) break;
    } catch (netErr) {
      lastErr = netErr;
      if (attempt < 2) {
        await new Promise(r => setTimeout(r, 1200 * (attempt + 1)));
      }
    }
  }

  clearTimeout(warmupTimer);
  showWarmupPill(false);

  if (!res) {
    throw new Error('Unable to connect to server. Please check your network connection.');
  }

  if (res.status === 401 && !path.includes('/auth/login')) {
    clearAuth();
    clearClientCache();
    window.location.href = 'index.html';
    throw new Error('Session expired. Please login again.');
  }

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const msg = data?.detail || data?.message || `Error ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }

  if (isGet) {
    _apiCache.set(path, { ts: Date.now(), data });
  } else {
    clearClientCache();
  }

  return data;
}

// ── Convenience methods ────────────────────────────────────────────────────
const api = {
  post:   (path, body)        => { clearClientCache(); return apiFetch(path, { method: 'POST',   body: JSON.stringify(body) }); },
  get:    (path, opts)        => apiFetch(path, { method: 'GET', ...opts }),
  patch:  (path, body)        => { clearClientCache(); return apiFetch(path, { method: 'PATCH',  body: JSON.stringify(body) }); },
  delete: (path)              => { clearClientCache(); return apiFetch(path, { method: 'DELETE' }); },
  upload: (path, formData)    => {
    clearClientCache();
    return fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getToken()}` },
      body: formData,
    }).then(async r => {
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d?.detail || `Error ${r.status}`);
      return d;
    });
  },
  clearCache: clearClientCache,
};

// ── Toast notifications ────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('leaving');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── Loader ─────────────────────────────────────────────────────────────────
function showLoader(show) {
  const el = document.getElementById('page-loader');
  if (el) el.classList.toggle('hidden', !show);
}

// ── Date helpers ───────────────────────────────────────────────────────────
function todayDisplay() {
  return new Date().toLocaleDateString('en-IN', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  });
}

function todayShort() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2,'0');
  const mm = String(d.getMonth()+1).padStart(2,'0');
  const yyyy = d.getFullYear();
  return `${dd}-${mm}-${yyyy}`;
}

// ── XSS Sanitizer ──────────────────────────────────────────────────────────
function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
window.escapeHtml = escapeHtml;

// ── Auth guard (call on every protected page) ──────────────────────────────
function requireAuth(expectedRole) {
  const token = getToken();
  const role  = getRole();
  if (!token || !role) {
    window.location.href = 'index.html';
    return false;
  }
  if (expectedRole && role.toUpperCase() !== expectedRole.toUpperCase()) {
    // Wrong role – redirect to correct page
    const pages = { ADMIN: 'admin.html', FACULTY: 'faculty.html', STUDENT: 'student.html' };
    window.location.href = pages[role.toUpperCase()] || 'index.html';
    return false;
  }
  return true;
}


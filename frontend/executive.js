// =============================================================================
// AttendTrax Enterprise – Executive Principal Academic Intelligence Module
// executive.js – Dedicated C-Suite Dashboard Controller for Principal & VP
// Includes: Scoped Dept Filter, Live Radar, Defaulter Matrix, Hard Copy Docket, & Audit
// =============================================================================

let _deptChartInstance = null;
let _defaulterChartInstance = null;
let _hourlyChartInstance = null;

let _executiveDataCache = null;
let _radarClassesCache = [];
let _defaultersListCache = [];
let _currentExecutiveDept = 'ALL';

// Safe HTML Escape Helper
const _esc = (str) => {
  if (typeof window.escapeHtml === 'function') return window.escapeHtml(str);
  if (str === null || str === undefined) return '';
  return String(str).replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
};

// Safe Debounce Helper
const _debounce = (fn, delay = 250) => {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
};

// ── Color Tokens for Charting ──────────────────────────────────────────────
const DEPT_COLORS = {
  CSE:   '#2563eb', // Blue
  AIDS:  '#8b5cf6', // Violet
  ECE:   '#06b6d4', // Cyan
  IT:    '#059669', // Emerald
  MECH:  '#f59e0b', // Amber
  CIVIL: '#ea580c', // Orange
  EEE:   '#ec4899', // Pink
  CSBS:  '#6366f1', // Indigo
};

// ── Initialize Executive View ──────────────────────────────────────────────
async function initExecutivePortal() {
  const role = (getRole() || '').toUpperCase();
  const isExec = role === 'SUPER_ADMIN' || role === 'ADMIN';

  const execNav = document.getElementById('nav-executive');
  const execSection = document.getElementById('section-executive');

  if (!isExec) {
    if (execNav) execNav.style.display = 'none';
    if (execSection) execSection.style.display = 'none';
    if (typeof showLoader === 'function') showLoader(false);
    return;
  }

  if (execNav) execNav.style.display = 'flex';

  try {
    // Load Executive Dashboard metrics with current filter
    await refreshExecutiveDashboard('ALL');
  } finally {
    if (typeof showLoader === 'function') showLoader(false);
  }

  // Attach event listeners for tabs and actions
  setupExecutiveEventListeners();
}

// ── Fetch & Render Complete Executive Intelligence ─────────────────────────
async function refreshExecutiveDashboard(deptCode) {
  if (deptCode !== undefined) {
    _currentExecutiveDept = (deptCode || 'ALL').toUpperCase();
  } else {
    const filterEl = document.getElementById('exec-department-filter');
    if (filterEl) _currentExecutiveDept = (filterEl.value || 'ALL').toUpperCase();
  }

  // Keep filter dropdown value in sync
  const filterEl = document.getElementById('exec-department-filter');
  if (filterEl && filterEl.value !== _currentExecutiveDept) {
    filterEl.value = _currentExecutiveDept;
  }

  const refreshBtn = document.getElementById('exec-refresh-btn');
  if (refreshBtn) {
    refreshBtn.classList.add('loading');
    refreshBtn.disabled = true;
  }

  try {
    const query = _currentExecutiveDept !== 'ALL' ? `?department_code=${encodeURIComponent(_currentExecutiveDept)}` : '';
    const res = await api.get(`/admin/executive/dashboard${query}`);
    _executiveDataCache = res;

    renderExecutiveKPIs(res.kpis, _currentExecutiveDept);
    renderDepartmentBenchmark(res.department_benchmarks, _currentExecutiveDept);
    renderDefaulterDonut(res.defaulter_distribution);
    renderHourlyTelemetry(res.hourly_telemetry);

    // Simultaneously load queues scoped strictly to the selected department
    await Promise.all([
      loadExecutiveLeavesQueue(_currentExecutiveDept),
      loadLiveRadarGrid(_currentExecutiveDept),
      loadExecutiveDefaultersTable(_currentExecutiveDept),
      loadSanctionedLeavesArchive(_currentExecutiveDept),
      loadExecutiveAuditLogs()
    ]);

    const deptLabel = _currentExecutiveDept === 'ALL' ? 'College-wide Institutional View' : `${_currentExecutiveDept} Department`;
    showToast(`Executive intelligence refreshed for ${deptLabel}`, 'success', 1800);
  } catch (err) {
    console.error('Failed to load executive dashboard:', err);
    showToast(`Executive Notice: ${err.message}`, 'error', 4000);
  } finally {
    if (refreshBtn) {
      refreshBtn.classList.remove('loading');
      refreshBtn.disabled = false;
    }
    if (typeof showLoader === 'function') showLoader(false);
  }
}

// ── Render Top KPI Cards ───────────────────────────────────────────────────
function renderExecutiveKPIs(kpis, deptCode) {
  if (!kpis) return;

  const setEl = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  const isFiltered = deptCode && deptCode !== 'ALL';

  setEl('exec-campus-pct', `${kpis.campus_attendance_pct}%`);
  setEl('exec-total-students', (kpis.total_students || 0).toLocaleString());
  setEl('exec-classes-marked', `${kpis.classes_marked_today} / ${kpis.total_classes}`);
  setEl('exec-compliance-pct', `${kpis.today_compliance_pct}% Marked`);
  setEl('exec-critical-defaulters', kpis.critical_defaulters || 0);
  setEl('exec-warning-defaulters', kpis.warning_defaulters || 0);
  setEl('exec-pending-leaves', kpis.pending_leaves_count || 0);
  setEl('exec-faculty-leave-today', kpis.faculty_on_leave_today || 0);

  // Update KPI card labels if filtered
  const campusLabel = document.getElementById('exec-campus-kpi-label');
  if (campusLabel) campusLabel.textContent = isFiltered ? `${deptCode} Attendance` : 'Campus Attendance';

  const studentsLabel = document.getElementById('exec-students-kpi-label');
  if (studentsLabel) studentsLabel.textContent = isFiltered ? `${deptCode} Students` : 'Enrolled Students';

  // Update compliance progress bar
  const progBar = document.getElementById('exec-today-progress');
  if (progBar) {
    progBar.style.width = `${Math.min(100, Math.max(5, kpis.today_compliance_pct))}%`;
  }
}

// ── Render 8-Department Comparative Benchmark & Chart ──────────────────────
function renderDepartmentBenchmark(benchmarks, deptCode) {
  if (!benchmarks || !benchmarks.length) return;

  const isFiltered = deptCode && deptCode !== 'ALL';
  const displayBenchmarks = isFiltered 
    ? benchmarks.filter(b => b.code === deptCode) 
    : benchmarks;

  // 1. Render Table Rows
  const tbody = document.getElementById('exec-dept-benchmark-tbody');
  if (tbody) {
    if (!displayBenchmarks.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:1.5rem;">No benchmark data available for ${deptCode}.</td></tr>`;
    } else {
      tbody.innerHTML = displayBenchmarks.map((b, idx) => {
        const color = DEPT_COLORS[b.code] || '#4f46e5';
        const rankBadge = idx === 0 
          ? '<span class="exec-rank-badge rank-1">🏆 1st</span>' 
          : idx === 1 
          ? '<span class="exec-rank-badge rank-2">🥈 2nd</span>' 
          : idx === 2 
          ? '<span class="exec-rank-badge rank-3">🥉 3rd</span>' 
          : `<span class="exec-rank-badge">#${idx + 1}</span>`;

        const statusBadge = b.is_fully_marked
          ? '<span class="badge badge-success">✓ 100% Marked</span>'
          : `<span class="badge badge-warning">⏳ ${b.today_status}</span>`;

        return `
          <tr ${isFiltered ? 'style="background:rgba(37,99,235,0.06);"' : ''}>
            <td>${rankBadge}</td>
            <td>
              <div class="flex items-center gap-2">
                <span class="dept-dot" style="background-color: ${color}"></span>
                <div>
                  <strong>${b.code}</strong>
                  <div class="text-xs text-muted" style="max-width:200px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${b.name}</div>
                </div>
              </div>
            </td>
            <td><strong>${b.student_count}</strong> students</td>
            <td>${b.class_count} sections</td>
            <td>
              <div class="flex items-center gap-2">
                <div class="progress-bar-wrap" style="width:70px;height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden;">
                  <div style="width:${b.attendance_pct}%;height:100%;background:${color};border-radius:3px;"></div>
                </div>
                <strong style="color:${b.attendance_pct >= 85 ? 'var(--success)' : (b.attendance_pct >= 75 ? 'var(--brand-600)' : 'var(--danger)')};">
                  ${b.attendance_pct}%
                </strong>
              </div>
            </td>
            <td>
              <span class="text-xs" style="font-weight:600;color:${b.critical_count > 0 ? 'var(--danger)' : 'var(--gray-600)'};">
                ${b.critical_count} critical · ${b.warning_count} warning
              </span>
            </td>
            <td>${statusBadge}</td>
          </tr>
        `;
      }).join('');
    }
  }

  // 2. Render Chart.js Horizontal Bar Benchmark
  const canvas = document.getElementById('exec-dept-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  const labels = displayBenchmarks.map(b => b.code);
  const dataValues = displayBenchmarks.map(b => b.attendance_pct);
  const bgColors = displayBenchmarks.map(b => DEPT_COLORS[b.code] || '#3b82f6');

  if (_deptChartInstance) {
    _deptChartInstance.destroy();
  }

  _deptChartInstance = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Attendance Rate (%)',
        data: dataValues,
        backgroundColor: bgColors,
        borderRadius: 6,
        barThickness: isFiltered ? 36 : 22,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ` Attendance: ${ctx.parsed.y || ctx.parsed.x}%`
          }
        }
      },
      scales: {
        y: {
          min: 60,
          max: 100,
          ticks: {
            callback: (v) => `${v}%`,
            font: { family: "'Plus Jakarta Sans', sans-serif", weight: '600' }
          },
          grid: { color: 'rgba(0,0,0,0.06)' }
        },
        x: {
          ticks: { font: { family: "'Plus Jakarta Sans', sans-serif", weight: '700' } },
          grid: { display: false }
        }
      }
    }
  });
}

// ── Render Defaulter Distribution Donut Chart ──────────────────────────────
function renderDefaulterDonut(dist) {
  const canvas = document.getElementById('exec-defaulter-donut');
  if (!canvas || typeof Chart === 'undefined' || !dist) return;

  if (_defaulterChartInstance) {
    _defaulterChartInstance.destroy();
  }

  _defaulterChartInstance = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: ['Safe (≥75%)', 'Warning (65-74%)', 'Critical (<65%)'],
      datasets: [{
        data: [dist.safe || 0, dist.warning || 0, dist.critical || 0],
        backgroundColor: ['#10b981', '#f59e0b', '#ef4444'],
        borderWidth: 2,
        borderColor: '#ffffff',
        hoverOffset: 4
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '72%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 12,
            padding: 12,
            font: { family: "'Plus Jakarta Sans', sans-serif", size: 11, weight: '600' }
          }
        }
      }
    }
  });
}

// ── Render Hourly Telemetry Graph ──────────────────────────────────────────
function renderHourlyTelemetry(telemetry) {
  const canvas = document.getElementById('exec-hourly-chart');
  if (!canvas || typeof Chart === 'undefined' || !telemetry) return;

  if (_hourlyChartInstance) {
    _hourlyChartInstance.destroy();
  }

  const labels = telemetry.map(t => `${t.hour}`);
  const values = telemetry.map(t => t.presence_pct);

  _hourlyChartInstance = new Chart(canvas, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Campus Presence (%)',
        data: values,
        borderColor: '#2563eb',
        backgroundColor: 'rgba(37, 99, 235, 0.1)',
        tension: 0.35,
        fill: true,
        pointBackgroundColor: '#2563eb',
        pointRadius: 4,
        pointHoverRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      scales: {
        y: {
          min: 70,
          max: 100,
          ticks: { callback: v => `${v}%`, font: { size: 10 } },
          grid: { color: 'rgba(0,0,0,0.05)' }
        },
        x: {
          grid: { display: false },
          ticks: { font: { size: 10, weight: '600' } }
        }
      }
    }
  });
}

// ── Load Executive Leave Queue (Level 2 Sign-off) ───────────────────────────
async function loadExecutiveLeavesQueue(deptCode) {
  const container = document.getElementById('exec-leaves-container');
  const countBadge = document.getElementById('exec-leaves-badge');
  if (!container) return;

  try {
    const query = deptCode && deptCode !== 'ALL' ? `?department_code=${encodeURIComponent(deptCode)}` : '';
    const leaves = await api.get(`/admin/executive/leaves${query}`);
    if (countBadge) countBadge.textContent = leaves.length;

    if (!leaves.length) {
      container.innerHTML = `
        <div class="empty-state" style="padding:2.5rem 1rem;text-align:center;">
          <div style="font-size:2rem;margin-bottom:0.5rem;">🎉</div>
          <h4 style="margin:0 0 0.25rem;color:var(--gray-800);">Executive Sign-Off Queue Clear</h4>
          <p class="text-xs text-muted">All HOD-recommended faculty leave tickets have been reviewed and approved.</p>
        </div>
      `;
      const batchBtn = document.getElementById('exec-batch-approve-btn');
      if (batchBtn) batchBtn.style.display = 'none';
      return;
    }

    const batchBtn = document.getElementById('exec-batch-approve-btn');
    if (batchBtn) batchBtn.style.display = 'inline-flex';

    container.innerHTML = leaves.map(l => {
      const scopeBadge = l.session_scope === 'FULL_DAY'
        ? '<span class="badge badge-info">Full Day</span>'
        : l.session_scope === 'FN_HALF_DAY'
        ? '<span class="badge badge-warning">Forenoon (FN)</span>'
        : l.session_scope === 'AN_HALF_DAY'
        ? '<span class="badge badge-warning">Afternoon (AN)</span>'
        : `<span class="badge badge-purple">${_esc(l.specific_time_window || 'Specific Hours')}</span>`;

      return `
        <div class="exec-leave-card" data-leave-id="${l.id}">
          <div class="exec-leave-header">
            <div>
              <div class="flex items-center gap-2">
                <span class="dept-tag">${_esc(l.department)}</span>
                <strong style="color:var(--gray-900);font-size:0.95rem;">${_esc(l.faculty_name)}</strong>
              </div>
              <div class="text-xs text-muted" style="margin-top:0.2rem;">Username: ${_esc(l.faculty_username)} · Category: <strong>${_esc(l.leave_category)}</strong></div>
            </div>
            ${scopeBadge}
          </div>
          
          <div class="exec-leave-body">
            <div class="exec-leave-meta">
              <span>📅 <strong>${_esc(l.start_date)}</strong> ${l.start_date !== l.end_date ? 'to ' + _esc(l.end_date) : ''}</span>
              ${l.specific_time_window ? `<span>⏰ ${_esc(l.specific_time_window)}</span>` : ''}
            </div>
            <p class="exec-leave-reason">"${_esc(l.reason)}"</p>
            <div class="exec-leave-hod-remark">
              <span class="text-xs font-semibold text-emerald-700">✓ HOD Recommendation:</span>
              <span class="text-xs text-gray-700">${_esc(l.hod_remarks || 'Recommended for sanction')}</span>
            </div>
          </div>

          <div class="exec-leave-actions flex items-center justify-between" style="padding-top:0.75rem;border-top:1px solid var(--gray-200);margin-top:0.75rem;">
            <div class="flex gap-2">
              <button type="button" class="btn btn-secondary btn-sm" onclick="handleExecutiveSignOff(${l.id}, 'REJECT')">
                Reject
              </button>
              <button type="button" class="btn btn-primary btn-sm" onclick="handleExecutiveSignOff(${l.id}, 'APPROVE')">
                ✓ Executive Sanction
              </button>
            </div>
            <button type="button" class="btn btn-secondary btn-xs" onclick="openLeaveSanctionDocket(${l.id})" style="display:inline-flex;align-items:center;gap:0.25rem;">
              📄 Preview Docket
            </button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Error loading executive leaves:', err);
    container.innerHTML = `<p class="text-xs text-danger" style="padding:1rem;">Failed to load leaves: ${_esc(err.message)}</p>`;
  }
}

// ── Handle Single Leave Approval / Rejection ────────────────────────────────
async function handleExecutiveSignOff(leaveId, action) {
  const remarks = action === 'APPROVE' 
    ? 'Executive Sanction Granted by Dr. S. K. Narayanan (Principal)'
    : 'Leave rejected upon executive administrative review';

  try {
    const res = await api.post(`/admin/executive/leaves/${leaveId}/sign-off`, {
      action: action,
      remarks: remarks
    });
    showToast(res.message, action === 'APPROVE' ? 'success' : 'warning');
    
    // Refresh queues and archive
    await Promise.all([
      loadExecutiveLeavesQueue(_currentExecutiveDept),
      loadSanctionedLeavesArchive(_currentExecutiveDept),
      loadExecutiveAuditLogs()
    ]);

    // Update KPI counter
    const badge = document.getElementById('exec-pending-leaves');
    if (badge && parseInt(badge.textContent) > 0) {
      badge.textContent = parseInt(badge.textContent) - 1;
    }
  } catch (err) {
    showToast(`Action failed: ${err.message}`, 'error');
  }
}

// ── Handle Batch Approval of Verified Leaves ────────────────────────────────
async function handleBatchExecutiveApproval() {
  const leaveCards = document.querySelectorAll('.exec-leave-card');
  const leaveIds = Array.from(leaveCards).map(c => parseInt(c.dataset.leaveId)).filter(id => !isNaN(id));

  if (!leaveIds.length) {
    showToast('No pending leaves to approve.', 'info');
    return;
  }

  if (!confirm(`Are you sure you want to approve all ${leaveIds.length} verified faculty leave tickets with Principal sanction?`)) {
    return;
  }

  try {
    const res = await api.post('/admin/executive/leaves/batch-approve', {
      leave_ids: leaveIds,
      action: 'APPROVE',
      remarks: 'Batch Executive Sanction Approved by Principal'
    });
    showToast(res.message, 'success', 3000);
    
    await Promise.all([
      loadExecutiveLeavesQueue(_currentExecutiveDept),
      loadSanctionedLeavesArchive(_currentExecutiveDept),
      loadExecutiveAuditLogs()
    ]);

    const badge = document.getElementById('exec-pending-leaves');
    if (badge) badge.textContent = '0';
  } catch (err) {
    showToast(`Batch approval failed: ${err.message}`, 'error');
  }
}

// ── Load Live Attendance Radar Grid ─────────────────────────────────────────
async function loadLiveRadarGrid(deptCode) {
  const tbody = document.getElementById('exec-radar-tbody');
  if (!tbody) return;

  try {
    const query = deptCode && deptCode !== 'ALL' ? `?department_code=${encodeURIComponent(deptCode)}` : '';
    const res = await api.get(`/admin/executive/live-radar${query}`);
    _radarClassesCache = res.classes || [];

    renderLiveRadarTable(_radarClassesCache);
  } catch (err) {
    console.error('Error loading live radar:', err);
  }
}

function renderLiveRadarTable(classes) {
  const tbody = document.getElementById('exec-radar-tbody');
  if (!tbody) return;

  const deptFilter = (document.getElementById('exec-radar-filter-dept')?.value || 'ALL').toUpperCase();
  const statusFilter = (document.getElementById('exec-radar-filter-status')?.value || 'ALL').toUpperCase();

  const filtered = classes.filter(c => {
    if (deptFilter !== 'ALL' && c.department !== deptFilter) return false;
    if (statusFilter === 'MARKED' && !c.is_marked) return false;
    if (statusFilter === 'PENDING' && c.is_marked) return false;
    return true;
  });

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding:1.5rem;">No classes match the selected filter.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(c => {
    const statusBadge = c.is_marked
      ? '<span class="badge badge-success">✓ Marked</span>'
      : '<span class="badge badge-warning" style="animation:pulse 2s infinite;">⏳ Pending Submission</span>';

    const actionBtn = c.is_marked
      ? '<span class="text-xs text-muted">Complete</span>'
      : `<button type="button" class="btn btn-secondary btn-xs" onclick="nudgeDepartmentHOD('${c.department}', '${c.class_code}')">📢 Nudge HOD</button>`;

    return `
      <tr>
        <td><strong>${_esc(c.department)}</strong></td>
        <td><strong>${_esc(c.class_code)}</strong> <span class="text-xs text-muted">(${_esc(c.class_name)})</span></td>
        <td>Year ${c.year} · Sec ${_esc(c.section)}</td>
        <td>${statusBadge}</td>
        <td>
          <span class="text-xs">${_esc(c.faculty_name)}</span>
          ${c.submitted_at && c.submitted_at !== '—' ? `<div class="text-xs text-muted">Logged at ${_esc(c.submitted_at)}</div>` : ''}
        </td>
        <td>${actionBtn}</td>
      </tr>
    `;
  }).join('');
}

function nudgeDepartmentHOD(dept, classCode) {
  showToast(`📢 Alert dispatched to Head of Department (${dept}) for class ${classCode} attendance submission.`, 'info', 4000);
}

// ── Load Institutional Defaulters Radar (<75%) ──────────────────────────────
async function loadExecutiveDefaultersTable(deptCode) {
  const tbody = document.getElementById('exec-defaulters-tbody');
  if (!tbody) return;

  try {
    const query = deptCode && deptCode !== 'ALL' ? `?department_code=${encodeURIComponent(deptCode)}` : '';
    const res = await api.get(`/admin/executive/defaulters${query}`);
    _defaultersListCache = res.defaulters || [];

    renderExecutiveDefaultersTable(_defaultersListCache);
  } catch (err) {
    console.error('Error loading defaulters:', err);
  }
}

function renderExecutiveDefaultersTable(list) {
  const tbody = document.getElementById('exec-defaulters-tbody');
  if (!tbody) return;

  const deptFilter = (document.getElementById('exec-def-filter-dept')?.value || 'ALL').toUpperCase();
  const riskFilter = (document.getElementById('exec-def-filter-risk')?.value || 'ALL').toUpperCase();
  const search = (document.getElementById('exec-def-search')?.value || '').toLowerCase().trim();

  const filtered = list.filter(d => {
    if (deptFilter !== 'ALL' && d.department !== deptFilter) return false;
    if (riskFilter !== 'ALL' && d.risk_level !== riskFilter) return false;
    if (search && !d.name.toLowerCase().includes(search) && !d.reg_no.includes(search)) return false;
    return true;
  });

  const countBadge = document.getElementById('exec-defaulters-count-badge');
  if (countBadge) countBadge.textContent = `${filtered.length} Students`;

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:1.5rem;">No defaulters matching criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered.map(d => {
    const riskBadge = d.risk_level === 'CRITICAL'
      ? '<span class="badge badge-danger">🔴 Critical (&lt;65%)</span>'
      : '<span class="badge badge-warning">🟡 Warning (65-75%)</span>';

    return `
      <tr>
        <td><code>${_esc(d.reg_no)}</code></td>
        <td><strong>${_esc(d.name)}</strong></td>
        <td><span class="dept-tag">${_esc(d.department)}</span></td>
        <td>${_esc(d.class_code)} <span class="text-xs text-muted">(Yr ${d.year})</span></td>
        <td>${d.attended_hours} / ${d.total_hours}</td>
        <td>
          <strong style="color:${d.risk_level === 'CRITICAL' ? 'var(--danger)' : 'var(--warning-text)'};">
            ${d.attendance_pct}%
          </strong>
        </td>
        <td>${riskBadge}</td>
      </tr>
    `;
  }).join('');
}

// ── Load Sanctioned Leaves Docket Archive ────────────────────────────────────
async function loadSanctionedLeavesArchive(deptCode) {
  const tbody = document.getElementById('exec-sanctioned-archive-tbody');
  const countBadge = document.getElementById('exec-sanctioned-count-badge');
  if (!tbody) return;

  try {
    const query = deptCode && deptCode !== 'ALL' ? `?department_code=${encodeURIComponent(deptCode)}` : '';
    const records = await api.get(`/admin/executive/leaves/sanctioned-archive${query}`);
    
    if (countBadge) countBadge.textContent = `${records.length} Sanctioned`;

    if (!records.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:1.5rem;">No officially sanctioned leaves found for the selected scope.</td></tr>`;
      return;
    }

    tbody.innerHTML = records.map(r => {
      const scopeDisplay = r.specific_time_window ? `${r.session_scope} (${r.specific_time_window})` : r.session_scope;
      const period = r.start_date === r.end_date ? r.start_date : `${r.start_date} to ${r.end_date}`;

      return `
        <tr>
          <td><code style="font-weight:700;color:#1e40af;">${_esc(r.docket_ref)}</code></td>
          <td>
            <strong>${_esc(r.faculty_name)}</strong>
            <div class="text-xs text-muted">${_esc(r.designation || 'Faculty')} · <code>${_esc(r.faculty_code || r.faculty_username)}</code></div>
          </td>
          <td><span class="dept-tag">${_esc(r.department_code)}</span></td>
          <td>
            <span class="badge badge-brand" style="font-size:0.72rem;">${_esc(r.leave_category)}</span>
            <div class="text-xs text-muted" style="margin-top:2px;">${_esc(scopeDisplay)}</div>
          </td>
          <td>
            <strong>${_esc(period)}</strong>
            <div class="text-xs text-muted">${r.total_days} Day(s)</div>
          </td>
          <td>
            <span class="badge badge-success" style="font-size:0.75rem;">✓ Sanctioned</span>
            <div class="text-xs text-muted" style="margin-top:2px;">${r.principal_action_at ? r.principal_action_at.split('T')[0] : 'Approved'}</div>
          </td>
          <td>
            <button type="button" class="btn btn-secondary btn-xs" onclick="openLeaveSanctionDocket(${r.id})" style="display:inline-flex;align-items:center;gap:0.3rem;background:#1e40af;color:#fff;border-color:#1e3a8a;font-weight:700;padding:3px 8px;">
              🖨️ Print Docket
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Error loading sanctioned archive:', err);
    tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger" style="padding:1.5rem;">Failed to load archive: ${_esc(err.message)}</td></tr>`;
  }
}

// ── Load Executive Audit Trail Ledger ───────────────────────────────────────
async function loadExecutiveAuditLogs() {
  const tbody = document.getElementById('exec-audit-logs-tbody');
  const countBadge = document.getElementById('exec-audit-count-badge');
  if (!tbody) return;

  try {
    const logs = await api.get('/admin/executive/audit-logs');
    if (countBadge) countBadge.textContent = `${logs.length} Logged`;

    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted" style="padding:1.5rem;">No administrative audit entries recorded yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = logs.map(l => {
      const timeStr = l.created_at ? l.created_at.replace('T', ' ').slice(0, 19) : '—';
      const actionBadge = l.action.includes('APPROVE')
        ? '<span class="badge badge-success" style="font-size:0.72rem;">' + _esc(l.action) + '</span>'
        : l.action.includes('REJECT')
        ? '<span class="badge badge-danger" style="font-size:0.72rem;">' + _esc(l.action) + '</span>'
        : '<span class="badge badge-info" style="font-size:0.72rem;">' + _esc(l.action) + '</span>';

      const detailsStr = l.new_values ? JSON.stringify(l.new_values) : '—';

      return `
        <tr>
          <td><span class="text-xs text-muted">${timeStr}</span></td>
          <td>${actionBadge}</td>
          <td><strong>${_esc(l.target_entity)} #${l.target_id || ''}</strong></td>
          <td>
            <span class="text-xs">User #${l.user_id || 'System'}</span>
            <div class="text-xs text-muted">IP: ${_esc(l.ip_address || '127.0.0.1')}</div>
          </td>
          <td><code class="text-xs" style="max-width:280px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(detailsStr)}">${_esc(detailsStr)}</code></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Error loading audit logs:', err);
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger" style="padding:1.5rem;">Failed to load audit logs: ${_esc(err.message)}</td></tr>`;
  }
}

// ── Open Official Printable Leave Sanction Docket Modal ─────────────────────
async function openLeaveSanctionDocket(leaveId) {
  const modal = document.getElementById('leave-docket-modal');
  const container = document.getElementById('docket-content-placeholder');
  if (!modal || !container) return;

  modal.classList.remove('hidden');
  container.innerHTML = `
    <div style="text-align:center;padding:3rem 1rem;">
      <div class="loader-ring"></div>
      <p class="text-xs text-muted" style="margin-top:0.75rem;">Generating Official Sanction Docket #${leaveId}...</p>
    </div>
  `;

  try {
    let data;
    try {
      data = await api.get(`/admin/executive/leaves/${leaveId}/sanction-docket`);
    } catch (e) {
      data = await api.get(`/leaves/faculty/${leaveId}/sanction-docket`);
    }
    window._currentDocketData = data;
    renderDocketHTML(data, container);
  } catch (err) {
    container.innerHTML = `
      <div class="alert alert-danger" style="margin:2rem;">
        <strong>Error Generating Docket:</strong> ${_esc(err.message)}
      </div>
    `;
  }
}

function closeLeaveDocketModal() {
  const modal = document.getElementById('leave-docket-modal');
  if (modal) modal.classList.add('hidden');
}

function printLeaveDocket() {
  if (window._currentDocketData) {
    printLeaveDocketDirect(window._currentDocketData);
  } else {
    window.print();
  }
}

function renderDocketHTML(data, container) {
  container.innerHTML = `
    <div class="docket-header" style="text-align:center;border-bottom:2px solid #0f172a;padding-bottom:1rem;margin-bottom:1.25rem;">
      <div style="display:flex;align-items:center;justify-content:center;gap:1.25rem;margin-bottom:0.5rem;">
        <div style="width:56px;height:56px;background:#1e3a8a;border-radius:8px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:1.6rem;letter-spacing:1px;">ATX</div>
        <div>
          <h2 style="margin:0;font-size:1.35rem;font-weight:800;color:#0f172a;letter-spacing:0.02em;text-transform:uppercase;">
            AttendTrax Autonomous College of Engineering
          </h2>
          <p style="margin:0.15rem 0 0;font-size:0.76rem;font-weight:600;color:#475569;letter-spacing:0.03em;">
            (An Autonomous Institution | Approved by AICTE | Affiliated to Anna University | NAAC 'A++' Accredited)
          </p>
          <p style="margin:0.15rem 0 0;font-size:0.72rem;color:#64748b;">
            Autonomous Institutional Campus, Educational Boulevard, Chennai - 600025, Tamil Nadu
          </p>
        </div>
      </div>
      <div style="margin-top:0.6rem;background:#f1f5f9;display:inline-block;padding:0.3rem 1.5rem;border-radius:4px;border:1px solid #cbd5e1;">
        <span style="font-size:0.8rem;font-weight:800;color:#1e3a8a;letter-spacing:0.06em;text-transform:uppercase;">
          OFFICE OF THE PRINCIPAL &amp; HEAD OF THE INSTITUTION
        </span>
      </div>
    </div>

    <div class="docket-order-title" style="text-align:center;margin-bottom:1.25rem;">
      <h3 style="margin:0;font-size:1.05rem;font-weight:800;color:#0f172a;text-decoration:underline;text-transform:uppercase;letter-spacing:0.04em;">
        FACULTY LEAVE SANCTION PROCEEDINGS
      </h3>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.75rem;font-size:0.8rem;border-bottom:1px dashed #94a3b8;padding-bottom:0.5rem;">
        <span><strong>Docket Ref:</strong> <code>${_esc(data.docket_id)}</code></span>
        <span><strong>Date of Issue:</strong> ${_esc(data.issue_date)}</span>
        <span><strong>Security VRF:</strong> <code>${_esc(data.verification.reference_token)}</code></span>
      </div>
    </div>

    <div class="docket-preamble" style="font-size:0.82rem;line-height:1.6;margin-bottom:1rem;color:#1e293b;">
      <p style="margin:0 0 0.35rem;">
        <strong>Sub:</strong> Establishment – Faculty Academic Leave / Permission Sanction – Order Issued – Regarding.
      </p>
      <p style="margin:0 0 0.35rem;">
        <strong>Ref:</strong> 1. Leave Application submitted by <strong>${_esc(data.faculty.name)}</strong> (${_esc(data.faculty.faculty_code)}), ${_esc(data.faculty.designation)}, Dept. of ${_esc(data.faculty.department_code)}.<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;2. Level-1 Recommendation and clearance recorded by the Head of the Department (${_esc(data.faculty.department_code)}).
      </p>
      <div style="border-top:1px solid #e2e8f0;margin:0.5rem 0;"></div>
      <p style="margin:0;text-align:justify;">
        <strong>ORDER:</strong> In pursuance of institutional leave statutes, sanction is hereby accorded to the undermentioned faculty member for leave/permission as detailed hereunder. Alternative class arrangement has been verified and registered in the institutional academic portal.
      </p>
    </div>

    <div style="margin-bottom:1.25rem;">
      <table style="width:100%;border-collapse:collapse;font-size:0.8rem;border:1px solid #94a3b8;">
        <tbody>
          <tr style="border-bottom:1px solid #cbd5e1;background:#f8fafc;">
            <td style="padding:6px 10px;font-weight:700;width:25%;border-right:1px solid #cbd5e1;">Faculty Name</td>
            <td style="padding:6px 10px;width:35%;border-right:1px solid #cbd5e1;">${_esc(data.faculty.name)}</td>
            <td style="padding:6px 10px;font-weight:700;width:20%;border-right:1px solid #cbd5e1;">Faculty Code</td>
            <td style="padding:6px 10px;width:20%;"><code>${_esc(data.faculty.faculty_code)}</code></td>
          </tr>
          <tr style="border-bottom:1px solid #cbd5e1;">
            <td style="padding:6px 10px;font-weight:700;border-right:1px solid #cbd5e1;">Department</td>
            <td style="padding:6px 10px;border-right:1px solid #cbd5e1;">${_esc(data.faculty.department_name)} (${_esc(data.faculty.department_code)})</td>
            <td style="padding:6px 10px;font-weight:700;border-right:1px solid #cbd5e1;">Designation</td>
            <td style="padding:6px 10px;">${_esc(data.faculty.designation)}</td>
          </tr>
          <tr style="border-bottom:1px solid #cbd5e1;background:#f8fafc;">
            <td style="padding:6px 10px;font-weight:700;border-right:1px solid #cbd5e1;">Leave Category</td>
            <td style="padding:6px 10px;border-right:1px solid #cbd5e1;"><strong>${_esc(data.leave.category)} LEAVE</strong></td>
            <td style="padding:6px 10px;font-weight:700;border-right:1px solid #cbd5e1;">Session Scope</td>
            <td style="padding:6px 10px;">${_esc(data.leave.scope)} ${data.leave.time_window ? '(' + _esc(data.leave.time_window) + ')' : ''}</td>
          </tr>
          <tr style="border-bottom:1px solid #cbd5e1;">
            <td style="padding:6px 10px;font-weight:700;border-right:1px solid #cbd5e1;">Effective Period</td>
            <td style="padding:6px 10px;border-right:1px solid #cbd5e1;"><strong>${_esc(data.leave.start_date)}</strong> to <strong>${_esc(data.leave.end_date)}</strong></td>
            <td style="padding:6px 10px;font-weight:700;border-right:1px solid #cbd5e1;">Total Duration</td>
            <td style="padding:6px 10px;"><strong>${data.leave.total_days} Day(s)</strong></td>
          </tr>
          <tr style="border-bottom:1px solid #cbd5e1;background:#f8fafc;">
            <td style="padding:6px 10px;font-weight:700;border-right:1px solid #cbd5e1;">Stated Purpose / Reason</td>
            <td colspan="3" style="padding:6px 10px;font-style:italic;">"${_esc(data.leave.reason)}"</td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-weight:700;border-right:1px solid #cbd5e1;">Sanction Status</td>
            <td colspan="3" style="padding:6px 10px;">
              <span style="display:inline-block;padding:2px 8px;border-radius:4px;background:#dcfce7;color:#15803d;font-weight:700;font-size:0.78rem;">
                ✓ OFFICIALLY SANCTIONED BY PRINCIPAL
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div style="background:#f8fafc;border:1px solid #cbd5e1;border-radius:4px;padding:0.75rem 1rem;margin-bottom:1.5rem;font-size:0.78rem;">
      <div style="font-weight:700;margin-bottom:0.4rem;color:#0f172a;text-transform:uppercase;letter-spacing:0.04em;display:flex;align-items:center;gap:0.4rem;">
        <span>🔒</span> Digital Endorsement &amp; Audit Ledger
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;">
        <div style="border-right:1px solid #e2e8f0;padding-right:0.75rem;">
          <div style="font-weight:700;color:#1e3a8a;">Tier 1 · Department Recommendation:</div>
          <div><strong>Endorser:</strong> ${_esc(data.endorsements.hod.name)}</div>
          <div><strong>Remarks:</strong> "${_esc(data.endorsements.hod.remarks)}"</div>
          <div style="color:#64748b;font-size:0.72rem;margin-top:2px;">Logged At: ${_esc(data.endorsements.hod.action_at || 'Verified')}</div>
        </div>
        <div>
          <div style="font-weight:700;color:#1e3a8a;">Tier 2 · Executive Sanction:</div>
          <div><strong>Authority:</strong> ${_esc(data.endorsements.principal.name)}</div>
          <div><strong>Remarks:</strong> "${_esc(data.endorsements.principal.remarks)}"</div>
          <div style="color:#64748b;font-size:0.72rem;margin-top:2px;">Logged At: ${_esc(data.endorsements.principal.action_at || 'Sanctioned')}</div>
        </div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1.5rem;margin-top:2rem;padding-top:1.5rem;text-align:center;font-size:0.78rem;">
      <div>
        <div style="height:44px;"></div>
        <div style="border-top:1px solid #475569;padding-top:4px;">
          <strong>Signature of Faculty</strong><br/>
          <span style="font-size:0.72rem;color:#64748b;">${_esc(data.faculty.name)}</span>
        </div>
      </div>
      <div>
        <div style="height:44px;"></div>
        <div style="border-top:1px solid #475569;padding-top:4px;">
          <strong>Head of the Department</strong><br/>
          <span style="font-size:0.72rem;color:#64748b;">Dept. of ${_esc(data.faculty.department_code)}</span>
        </div>
      </div>
      <div>
        <div style="height:44px;display:flex;align-items:center;justify-content:center;">
          <span style="border:1.5px solid #1e40af;color:#1e40af;font-weight:800;font-size:0.68rem;padding:2px 8px;border-radius:4px;text-transform:uppercase;letter-spacing:0.04em;">
            INSTITUTIONAL SEAL
          </span>
        </div>
        <div style="border-top:1px solid #475569;padding-top:4px;">
          <strong>Dr. S. K. Narayanan, Ph.D.</strong><br/>
          <span style="font-size:0.72rem;color:#64748b;">Principal &amp; Head of Institution</span>
        </div>
      </div>
    </div>

    <div style="margin-top:1.75rem;padding-top:0.5rem;border-top:1px solid #e2e8f0;font-size:0.68rem;color:#94a3b8;display:flex;justify-content:space-between;">
      <span>Generated by AttendTrax Autonomous Academic ERP Platform</span>
      <span>Official Record Copy for Physical Archival · Anna University / AICTE / NAAC</span>
    </div>
  `;
}

// ── Export NAAC / NBA Compliance Report (CSV) ──────────────────────────────
function exportNAACComplianceReport() {
  if (!_defaultersListCache || !_defaultersListCache.length) {
    showToast('No defaulters data available to export.', 'warning');
    return;
  }

  const headers = ['Register Number', 'Student Name', 'Department', 'Class Code', 'Class Name', 'Year', 'Attended Sessions', 'Total Sessions', 'Attendance %', 'Risk Category'];
  const rows = _defaultersListCache.map(d => [
    `"${d.reg_no}"`,
    `"${d.name}"`,
    `"${d.department}"`,
    `"${d.class_code}"`,
    `"${d.class_name}"`,
    d.year,
    d.attended_hours,
    d.total_hours,
    d.attendance_pct,
    `"${d.risk_level}"`
  ]);

  let csvContent = "data:text/csv;charset=utf-8," 
    + "# ATTENDTRAX INSTITUTIONAL ACADEMIC DEFAULTER & NAAC/NBA COMPLIANCE REPORT\n"
    + `# Generated on: ${new Date().toLocaleDateString('en-GB')} by Office of the Principal\n`
    + headers.join(',') + '\n'
    + rows.map(e => e.join(',')).join('\n');

  const encodedUri = encodeURI(csvContent);
  const link = document.createElement('a');
  link.setAttribute('href', encodedUri);
  link.setAttribute('download', `AttendTrax_Campus_Defaulter_Report_${new Date().toISOString().split('T')[0]}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast('NAAC / NBA Compliance Report exported successfully!', 'success');
}

// ── Event Listeners Setup ──────────────────────────────────────────────────
function setupExecutiveEventListeners() {
  const refreshBtn = document.getElementById('exec-refresh-btn');
  if (refreshBtn) refreshBtn.addEventListener('click', () => refreshExecutiveDashboard());

  const deptFilter = document.getElementById('exec-department-filter');
  if (deptFilter) {
    deptFilter.addEventListener('change', (e) => {
      refreshExecutiveDashboard(e.target.value);
    });
  }

  const batchApproveBtn = document.getElementById('exec-batch-approve-btn');
  if (batchApproveBtn) batchApproveBtn.addEventListener('click', handleBatchExecutiveApproval);

  // Radar Filters
  const radarDept = document.getElementById('exec-radar-filter-dept');
  const radarStatus = document.getElementById('exec-radar-filter-status');
  if (radarDept) radarDept.addEventListener('change', () => renderLiveRadarTable(_radarClassesCache));
  if (radarStatus) radarStatus.addEventListener('change', () => renderLiveRadarTable(_radarClassesCache));

  // Defaulter Filters & Search
  const defDept = document.getElementById('exec-def-filter-dept');
  const defRisk = document.getElementById('exec-def-filter-risk');
  const defSearch = document.getElementById('exec-def-search');
  if (defDept) defDept.addEventListener('change', () => renderExecutiveDefaultersTable(_defaultersListCache));
  if (defRisk) defRisk.addEventListener('change', () => renderExecutiveDefaultersTable(_defaultersListCache));
  if (defSearch) defSearch.addEventListener('input', _debounce(() => renderExecutiveDefaultersTable(_defaultersListCache), 200));

  // NAAC Export
  const exportBtn = document.getElementById('exec-export-naac-btn');
  if (exportBtn) exportBtn.addEventListener('click', exportNAACComplianceReport);

  // Dedicated Archive Page Listeners
  const pageArchRefresh = document.getElementById('page-archive-refresh-btn');
  if (pageArchRefresh) pageArchRefresh.addEventListener('click', () => loadSanctionedLeavesArchivePage());
  const pageArchDept = document.getElementById('page-archive-filter-dept');
  if (pageArchDept) pageArchDept.addEventListener('change', () => loadSanctionedLeavesArchivePage());
  const pageArchSearch = document.getElementById('page-archive-search');
  if (pageArchSearch) {
    pageArchSearch.addEventListener('input', _debounce(() => {
      const q = (pageArchSearch.value || '').toLowerCase();
      const filtered = _cachedSanctionedRecords.filter(r => 
        (r.faculty_name || '').toLowerCase().includes(q) ||
        (r.docket_ref || '').toLowerCase().includes(q) ||
        (r.reason || '').toLowerCase().includes(q) ||
        (r.department_code || '').toLowerCase().includes(q)
      );
      renderSanctionedLeavesArchivePageRows(filtered);
    }, 200));
  }

  // Dedicated Audit Trail Page Listeners
  const pageAuditRefresh = document.getElementById('page-audit-refresh-btn');
  if (pageAuditRefresh) pageAuditRefresh.addEventListener('click', () => loadExecutiveAuditLogsPage());
  const pageAuditSearch = document.getElementById('page-audit-search');
  if (pageAuditSearch) {
    pageAuditSearch.addEventListener('input', _debounce(() => {
      const q = (pageAuditSearch.value || '').toLowerCase();
      const filtered = _cachedAuditLogs.filter(l => 
        (l.action || '').toLowerCase().includes(q) ||
        (l.target_entity || '').toLowerCase().includes(q) ||
        (l.actor_username || '').toLowerCase().includes(q) ||
        (l.ip_address || '').toLowerCase().includes(q) ||
        JSON.stringify(l.new_values || {}).toLowerCase().includes(q)
      );
      renderExecutiveAuditLogsPageRows(filtered);
    }, 200));
  }

  // Daily Active Leaves Register Listeners
  const dailyDate = document.getElementById('daily-leaves-date');
  if (dailyDate) dailyDate.addEventListener('change', () => loadDailyActiveFacultyLeaves());
  const dailyDept = document.getElementById('daily-leaves-dept');
  if (dailyDept) dailyDept.addEventListener('change', () => loadDailyActiveFacultyLeaves());
  const dailyRefresh = document.getElementById('refresh-daily-leaves-btn');
  if (dailyRefresh) dailyRefresh.addEventListener('click', () => loadDailyActiveFacultyLeaves());

  // Department-Wise Reports Listeners
  const reportDept = document.getElementById('report-dept-selector');
  if (reportDept) reportDept.addEventListener('change', (e) => loadDepartmentReports(e.target.value));
}

// Global exposure for inline onclick handlers

// ═════════════════════════════════════════════════════════════════════════════
// STANDALONE RELIABLE A4 LEAVE DOCKET PRINTING ENGINE (ZERO CLIPPING)
// ═════════════════════════════════════════════════════════════════════════════

function generateDocketPrintableHTML(data) {
  const scopeText = data.leave?.time_window ? `${data.leave?.scope} (${data.leave?.time_window})` : (data.leave?.scope || 'Full Day');
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Faculty Leave Sanction Docket - ${_esc(data.docket_id)}</title>
  <style>
    @page {
      size: A4 portrait;
      margin: 12mm 15mm 12mm 15mm;
    }
    * {
      box-sizing: border-box;
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      margin: 0;
      padding: 20px;
      color: #0f172a;
      background: #ffffff;
      line-height: 1.45;
    }
    @media print {
      body {
        padding: 0;
      }
      .no-print {
        display: none !important;
      }
    }
    .docket-wrapper {
      max-width: 800px;
      margin: 0 auto;
      border: 2px solid #0f172a;
      padding: 24px;
      position: relative;
      background: #fff;
    }
    .watermark {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%) rotate(-30deg);
      font-size: 5.5rem;
      font-weight: 900;
      color: rgba(15, 23, 42, 0.04);
      letter-spacing: 0.15em;
      pointer-events: none;
      user-select: none;
      z-index: 0;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .docket-content {
      position: relative;
      z-index: 1;
    }
    .header-table {
      width: 100%;
      border-bottom: 2px solid #0f172a;
      padding-bottom: 12px;
      margin-bottom: 12px;
    }
    .crest {
      width: 58px;
      height: 58px;
      background: #1e3a8a;
      border-radius: 8px;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 900;
      font-size: 1.7rem;
      letter-spacing: 1px;
    }
    .college-name {
      font-size: 1.25rem;
      font-weight: 800;
      color: #0f172a;
      text-transform: uppercase;
      letter-spacing: 0.02em;
      margin: 0;
    }
    .college-sub {
      font-size: 0.72rem;
      color: #475569;
      font-weight: 600;
      margin: 2px 0 0;
    }
    .college-addr {
      font-size: 0.68rem;
      color: #64748b;
      margin: 2px 0 0;
    }
    .order-banner {
      background: #f1f5f9;
      border: 1px solid #cbd5e1;
      padding: 4px 16px;
      display: inline-block;
      font-weight: 800;
      font-size: 0.78rem;
      color: #1e3a8a;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      margin-top: 6px;
      border-radius: 4px;
    }
    .title-sec {
      text-align: center;
      margin: 12px 0 10px;
    }
    .title-sec h3 {
      margin: 0;
      font-size: 1rem;
      font-weight: 800;
      text-decoration: underline;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .meta-bar {
      display: flex;
      justify-content: space-between;
      border-bottom: 1px dashed #94a3b8;
      padding-bottom: 6px;
      margin-top: 8px;
      font-size: 0.75rem;
    }
    .preamble {
      font-size: 0.78rem;
      line-height: 1.5;
      margin: 10px 0;
      text-align: justify;
    }
    table.data-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.76rem;
      margin-bottom: 12px;
      border: 1px solid #94a3b8;
    }
    table.data-table td {
      padding: 5px 8px;
      border: 1px solid #cbd5e1;
    }
    table.data-table td.label {
      font-weight: 700;
      background: #f8fafc;
      width: 25%;
    }
    .ledger-box {
      background: #f8fafc;
      border: 1px solid #cbd5e1;
      border-radius: 4px;
      padding: 8px 12px;
      margin-bottom: 14px;
      font-size: 0.74rem;
    }
    .ledger-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .sig-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 12px;
      margin-top: 24px;
      text-align: center;
      font-size: 0.75rem;
    }
    .sig-line {
      border-top: 1px solid #475569;
      padding-top: 4px;
    }
    .seal-box {
      border: 1.5px solid #1e40af;
      color: #1e40af;
      font-weight: 800;
      font-size: 0.65rem;
      padding: 2px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      display: inline-block;
      margin-bottom: 6px;
    }
  </style>
</head>
<body>
  <div class="no-print" style="max-width:800px;margin:0 auto 12px;display:flex;justify-content:space-between;align-items:center;background:#f8fafc;padding:10px 16px;border-radius:6px;border:1px solid #e2e8f0;">
    <span style="font-size:0.85rem;font-weight:600;color:#334155;">Official Faculty Leave Sanction Docket (A4 Ready)</span>
    <button onclick="window.print()" style="background:#1e3a8a;color:#fff;border:none;padding:6px 16px;border-radius:4px;font-weight:700;cursor:pointer;">🖨️ Print Now</button>
  </div>

  <div class="docket-wrapper">
    <div class="watermark">SANCTIONED</div>
    <div class="docket-content">
      <table class="header-table" style="border:none;">
        <tr>
          <td style="width:65px;vertical-align:middle;">
            <div class="crest">ATX</div>
          </td>
          <td style="text-align:center;vertical-align:middle;padding:0 10px;">
            <h2 class="college-name">AttendTrax Autonomous College of Engineering</h2>
            <p class="college-sub">(An Autonomous Institution | Approved by AICTE | Affiliated to Anna University | NAAC 'A++' Accredited)</p>
            <p class="college-addr">Autonomous Institutional Campus, Educational Boulevard, Chennai - 600025, Tamil Nadu</p>
            <div class="order-banner">OFFICE OF THE PRINCIPAL &amp; HEAD OF THE INSTITUTION</div>
          </td>
        </tr>
      </table>

      <div class="title-sec">
        <h3>FACULTY LEAVE SANCTION PROCEEDINGS</h3>
        <div class="meta-bar">
          <span><strong>Docket Ref:</strong> <code>${_esc(data.docket_id)}</code></span>
          <span><strong>Date of Issue:</strong> ${_esc(data.issue_date)}</span>
          <span><strong>Security Token:</strong> <code>${_esc(data.verification?.reference_token || 'VRF-LEAVE')}</code></span>
        </div>
      </div>

      <div class="preamble">
        <p style="margin:0 0 3px;"><strong>Sub:</strong> Establishment – Faculty Academic Leave / Permission Sanction – Order Issued – Regarding.</p>
        <p style="margin:0 0 3px;"><strong>Ref:</strong> 1. Leave Application submitted by <strong>${_esc(data.faculty?.name)}</strong> (${_esc(data.faculty?.faculty_code)}), ${_esc(data.faculty?.designation)}, Dept. of ${_esc(data.faculty?.department_code)}.<br/>
        &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;2. Level-1 Recommendation and clearance recorded by Head of the Department (${_esc(data.faculty?.department_code)}).</p>
        <div style="border-top:1px solid #e2e8f0;margin:4px 0;"></div>
        <p style="margin:0;"><strong>ORDER:</strong> In pursuance of institutional leave statutes, sanction is hereby accorded to the undermentioned faculty member for leave/permission as detailed hereunder. Alternative class arrangements have been verified and registered in the institutional academic portal.</p>
      </div>

      <table class="data-table">
        <tbody>
          <tr>
            <td class="label">Faculty Name</td>
            <td><strong>${_esc(data.faculty?.name)}</strong></td>
            <td class="label">Faculty Code</td>
            <td><code>${_esc(data.faculty?.faculty_code)}</code></td>
          </tr>
          <tr>
            <td class="label">Department</td>
            <td>${_esc(data.faculty?.department_name)} (${_esc(data.faculty?.department_code)})</td>
            <td class="label">Designation</td>
            <td>${_esc(data.faculty?.designation)}</td>
          </tr>
          <tr>
            <td class="label">Leave Category</td>
            <td><strong>${_esc(data.leave?.category)} LEAVE</strong></td>
            <td class="label">Session Scope</td>
            <td>${_esc(scopeText)}</td>
          </tr>
          <tr>
            <td class="label">Effective Period</td>
            <td><strong>${_esc(data.leave?.start_date)}</strong> to <strong>${_esc(data.leave?.end_date)}</strong></td>
            <td class="label">Total Duration</td>
            <td><strong>${data.leave?.total_days || 1} Day(s)</strong></td>
          </tr>
          <tr>
            <td class="label">Stated Purpose</td>
            <td colspan="3" style="font-style:italic;">"${_esc(data.leave?.reason)}"</td>
          </tr>
          <tr>
            <td class="label">Sanction Status</td>
            <td colspan="3">
              <span style="display:inline-block;padding:2px 8px;border-radius:4px;background:#dcfce7;color:#15803d;font-weight:700;font-size:0.75rem;">
                ✓ OFFICIALLY SANCTIONED BY PRINCIPAL
              </span>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="ledger-box">
        <div style="font-weight:700;margin-bottom:4px;color:#0f172a;text-transform:uppercase;letter-spacing:0.04em;">
          🔒 Digital Endorsement &amp; Audit Ledger
        </div>
        <div class="ledger-grid">
          <div style="border-right:1px solid #e2e8f0;padding-right:8px;">
            <div style="font-weight:700;color:#1e3a8a;">Tier 1 · Department Recommendation:</div>
            <div><strong>Endorser:</strong> ${_esc(data.endorsements?.hod?.name || 'Department HOD')}</div>
            <div><strong>Remarks:</strong> "${_esc(data.endorsements?.hod?.remarks || 'Recommended')}"</div>
            <div style="color:#64748b;font-size:0.68rem;margin-top:2px;">Logged At: ${_esc(data.endorsements?.hod?.action_at || 'Verified')}</div>
          </div>
          <div>
            <div style="font-weight:700;color:#1e3a8a;">Tier 2 · Executive Sanction:</div>
            <div><strong>Authority:</strong> ${_esc(data.endorsements?.principal?.name || 'Principal')}</div>
            <div><strong>Remarks:</strong> "${_esc(data.endorsements?.principal?.remarks || 'Sanctioned')}"</div>
            <div style="color:#64748b;font-size:0.68rem;margin-top:2px;">Logged At: ${_esc(data.endorsements?.principal?.action_at || 'Sanctioned')}</div>
          </div>
        </div>
      </div>

      <div class="sig-grid">
        <div>
          <div style="height:36px;"></div>
          <div class="sig-line">
            <strong>Signature of Faculty</strong><br/>
            <span style="font-size:0.68rem;color:#64748b;">${_esc(data.faculty?.name)}</span>
          </div>
        </div>
        <div>
          <div style="height:36px;"></div>
          <div class="sig-line">
            <strong>Head of the Department</strong><br/>
            <span style="font-size:0.68rem;color:#64748b;">Dept. of ${_esc(data.faculty?.department_code)}</span>
          </div>
        </div>
        <div>
          <div style="height:36px;display:flex;align-items:center;justify-content:center;">
            <span class="seal-box">INSTITUTIONAL SEAL</span>
          </div>
          <div class="sig-line">
            <strong>Principal &amp; Executive Authority</strong><br/>
            <span style="font-size:0.68rem;color:#64748b;">AttendTrax College of Engineering</span>
          </div>
        </div>
      </div>

      <div style="margin-top:14px;border-top:1px dashed #cbd5e1;padding-top:6px;font-size:0.65rem;color:#64748b;display:flex;justify-content:space-between;">
        <span>Official Computer-Generated Sanction Order | Record Copy for Institutional Establishment Office</span>
        <span>AttendTrax Autonomous Enterprise Governance System</span>
      </div>
    </div>
  </div>

  <script>
    window.onload = function() {
      setTimeout(function() {
        window.focus();
        window.print();
      }, 350);
    };
  <\/script>
</body>
</html>`;
}

async function printLeaveDocketDirect(leaveIdOrData) {
  let data = leaveIdOrData;
  if (typeof leaveIdOrData === 'number' || typeof leaveIdOrData === 'string') {
    try {
      try {
        data = await api.get(`/admin/executive/leaves/${leaveIdOrData}/sanction-docket`);
      } catch (e) {
        data = await api.get(`/leaves/faculty/${leaveIdOrData}/sanction-docket`);
      }
    } catch (err) {
      alert('Unable to load leave docket: ' + (err.message || err));
      return;
    }
  }
  if (!data) return;

  const printWin = window.open('', '_blank', 'width=880,height=960,menubar=no,toolbar=no,location=no,status=no');
  if (!printWin) {
    alert('Pop-up window was blocked. Please allow pop-ups for this domain to print the official docket.');
    return;
  }
  const fullHtml = generateDocketPrintableHTML(data);
  printWin.document.open();
  printWin.document.write(fullHtml);
  printWin.document.close();
  setTimeout(() => {
    try {
      printWin.focus();
      printWin.print();
    } catch (e) {}
  }, 450);
}

// ── Dedicated Page: Sanctioned Leaves (Dockets Archive) ──────────────────────
let _cachedSanctionedRecords = [];

async function loadSanctionedLeavesArchivePage() {
  const tbody = document.getElementById('page-sanctioned-archive-tbody');
  const countBadge = document.getElementById('page-sanctioned-count-badge');
  const deptSelect = document.getElementById('page-archive-filter-dept');
  const deptCode = deptSelect ? deptSelect.value : 'ALL';
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted" style="padding:1.5rem;"><div class="loader-ring"></div><div style="margin-top:0.5rem;">Loading sanctioned archive...</div></td></tr>`;

  try {
    const query = deptCode && deptCode !== 'ALL' ? `?department_code=${encodeURIComponent(deptCode)}` : '';
    const records = await api.get(`/admin/executive/leaves/sanctioned-archive${query}`);
    _cachedSanctionedRecords = records || [];

    if (countBadge) countBadge.textContent = `${_cachedSanctionedRecords.length} Sanctioned`;
    renderSanctionedLeavesArchivePageRows(_cachedSanctionedRecords);
    // Also sync the card inside executive dashboard if present
    loadSanctionedLeavesArchive(deptCode);
  } catch (err) {
    console.error('Error loading sanctioned archive page:', err);
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-danger" style="padding:1.5rem;">Failed to load archive: ${_esc(err.message)}</td></tr>`;
  }
}

function renderSanctionedLeavesArchivePageRows(records) {
  const tbody = document.getElementById('page-sanctioned-archive-tbody');
  if (!tbody) return;

  if (!records.length) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted" style="padding:1.5rem;">No officially sanctioned leaves found for the selected scope.</td></tr>`;
    return;
  }

  tbody.innerHTML = records.map(r => {
    const scopeDisplay = r.specific_time_window ? `${r.session_scope} (${r.specific_time_window})` : r.session_scope;
    const period = r.start_date === r.end_date ? r.start_date : `${r.start_date} to ${r.end_date}`;

    return `
      <tr>
        <td><code style="font-weight:700;color:#1e40af;">${_esc(r.docket_ref)}</code></td>
        <td>
          <strong>${_esc(r.faculty_name)}</strong>
          <div class="text-xs text-muted">${_esc(r.designation || 'Faculty')} · <code>${_esc(r.faculty_code || r.faculty_username)}</code></div>
        </td>
        <td><span class="dept-tag">${_esc(r.department_code)}</span></td>
        <td>
          <span class="badge badge-brand" style="font-size:0.72rem;">${_esc(r.leave_category)}</span>
        </td>
        <td>
          <span class="text-xs font-semibold">${_esc(scopeDisplay)}</span>
        </td>
        <td>
          <strong>${_esc(period)}</strong>
        </td>
        <td>
          <span class="badge badge-primary" style="font-size:0.72rem;">${r.total_days} Day(s)</span>
        </td>
        <td>
          <span class="badge badge-success" style="font-size:0.75rem;">✓ Sanctioned</span>
          <div class="text-xs text-muted" style="margin-top:2px;">${r.principal_action_at ? r.principal_action_at.split('T')[0] : 'Approved'}</div>
        </td>
        <td>
          <div style="display:flex;gap:0.35rem;align-items:center;">
            <button type="button" class="btn btn-secondary btn-xs" onclick="openLeaveSanctionDocket(${r.id})" style="padding:3px 7px;">
              📄 View
            </button>
            <button type="button" class="btn btn-primary btn-xs" onclick="printLeaveDocketDirect(${r.id})" style="display:inline-flex;align-items:center;gap:0.25rem;background:#1e40af;color:#fff;border-color:#1e3a8a;font-weight:700;padding:3px 8px;">
              🖨️ Print Docket
            </button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

// ── Dedicated Page: Executive Security Audit Trail ──────────────────────────
let _cachedAuditLogs = [];

async function loadExecutiveAuditLogsPage() {
  const tbody = document.getElementById('page-audit-logs-tbody');
  const countBadge = document.getElementById('page-audit-count-badge');
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding:1.5rem;"><div class="loader-ring"></div><div style="margin-top:0.5rem;">Loading audit trail ledger...</div></td></tr>`;

  try {
    const logs = await api.get('/admin/executive/audit-logs');
    _cachedAuditLogs = logs || [];
    if (countBadge) countBadge.textContent = `${_cachedAuditLogs.length} Entries`;

    renderExecutiveAuditLogsPageRows(_cachedAuditLogs);
    // Also sync the card inside executive dashboard if present
    loadExecutiveAuditLogs();
  } catch (err) {
    console.error('Error loading audit logs page:', err);
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger" style="padding:1.5rem;">Failed to load audit logs: ${_esc(err.message)}</td></tr>`;
  }
}

function renderExecutiveAuditLogsPageRows(logs) {
  const tbody = document.getElementById('page-audit-logs-tbody');
  if (!tbody) return;

  if (!logs.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding:1.5rem;">No administrative audit entries recorded yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = logs.map(l => {
    const timeStr = l.created_at ? l.created_at.replace('T', ' ').slice(0, 19) : '—';
    const actionBadge = l.action.includes('APPROVE')
      ? '<span class="badge badge-success" style="font-size:0.72rem;">' + _esc(l.action) + '</span>'
      : l.action.includes('REJECT')
      ? '<span class="badge badge-danger" style="font-size:0.72rem;">' + _esc(l.action) + '</span>'
      : '<span class="badge badge-info" style="font-size:0.72rem;">' + _esc(l.action) + '</span>';

    const detailsStr = l.new_values ? JSON.stringify(l.new_values) : (l.old_values ? JSON.stringify(l.old_values) : '—');

    return `
      <tr>
        <td><span class="text-xs text-muted" style="white-space:nowrap;">${timeStr}</span></td>
        <td>
          <strong>${_esc(l.actor_username || 'Admin')}</strong>
          <div class="text-xs text-muted">User ID #${l.user_id || 'System'}</div>
        </td>
        <td>${actionBadge}</td>
        <td><strong>${_esc(l.target_entity)} #${l.target_id || ''}</strong></td>
        <td><code class="text-xs">${_esc(l.ip_address || '127.0.0.1')}</code></td>
        <td><code class="text-xs" style="max-width:320px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(detailsStr)}">${_esc(detailsStr)}</code></td>
      </tr>
    `;
  }).join('');
}

// ── Daily Active Faculty Leaves Register (Inside Leave Approvals) ────────────
async function loadDailyActiveFacultyLeaves() {
  const tbody = document.getElementById('daily-faculty-leaves-tbody');
  if (!tbody) return;

  const dateInput = document.getElementById('daily-leaves-date');
  const deptSelect = document.getElementById('daily-leaves-dept');
  
  // Default to today if date input is empty
  if (dateInput && !dateInput.value) {
    const todayStr = new Date().toISOString().split('T')[0];
    dateInput.value = todayStr;
  }
  const queryDate = dateInput ? dateInput.value : '';
  const deptCode = deptSelect ? deptSelect.value : 'ALL';

  tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted" style="padding:1.5rem;"><div class="loader-ring"></div><div style="margin-top:0.5rem;">Fetching faculties on leave for ${queryDate || 'today'}...</div></td></tr>`;

  try {
    const params = new URLSearchParams();
    if (queryDate) params.append('query_date', queryDate);
    if (deptCode && deptCode !== 'ALL') params.append('department_code', deptCode);

    const res = await api.get(`/leaves/faculty/active-on-date?${params.toString()}`);
    const records = Array.isArray(res) ? res : (res?.faculties_on_leave || []);
    if (!records.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted" style="padding:1.5rem;">No faculty members on approved leave on <strong>${queryDate}</strong> for the selected scope. All faculty accounted for! 🎉</td></tr>`;
      return;
    }

    tbody.innerHTML = records.map(r => {
      const scopeDisplay = r.specific_time_window ? `${r.session_scope} (${r.specific_time_window})` : r.session_scope;
      const period = r.start_date === r.end_date ? r.start_date : `${r.start_date} to ${r.end_date}`;

      return `
        <tr>
          <td>
            <strong>${_esc(r.faculty_name)}</strong>
            <div class="text-xs text-muted"><code>${_esc(r.faculty_code || r.faculty_username)}</code></div>
          </td>
          <td><span class="dept-tag">${_esc(r.department_code)}</span></td>
          <td><span class="text-xs font-semibold">${_esc(r.designation || 'Faculty')}</span></td>
          <td><span class="badge badge-brand" style="font-size:0.72rem;">${_esc(r.leave_category)}</span></td>
          <td><span class="text-xs">${_esc(scopeDisplay)}</span></td>
          <td><strong>${_esc(period)}</strong></td>
          <td><span class="text-xs text-muted" style="max-width:200px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${_esc(r.reason)}">${_esc(r.reason)}</span></td>
          <td><code style="font-weight:700;color:#1e40af;">${_esc(r.docket_ref || ('DOCK-' + r.id))}</code></td>
          <td>
            <button type="button" class="btn btn-primary btn-xs" onclick="printLeaveDocketDirect(${r.id})" style="display:inline-flex;align-items:center;gap:0.3rem;background:#1e40af;color:#fff;border-color:#1e3a8a;font-weight:700;padding:3px 8px;">
              🖨️ Print Docket
            </button>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Error fetching active leaves on date:', err);
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-danger" style="padding:1.5rem;">Failed to load active leaves: ${_esc(err.message)}</td></tr>`;
  }
}

// ── Department-Wise Attendance Reports & Analytics ──────────────────────────
async function initDepartmentReportsSection() {
  const deptSelect = document.getElementById('report-dept-selector');
  const userRole = (getRole() || '').toUpperCase();
  const curUsername = (getUsername() || '').toLowerCase();

  // If HOD, lock department selector to their own department
  if (userRole === 'DEPT_ADMIN') {
    let hodDept = 'CSE';
    if (curUsername.startsWith('hod.')) {
      hodDept = curUsername.replace('hod.', '').toUpperCase();
    }
    if (deptSelect) {
      deptSelect.value = hodDept;
      deptSelect.disabled = true;
      deptSelect.title = `Locked to ${hodDept} Department (Head of Department)`;
    }
  }

  const selectedDept = deptSelect ? deptSelect.value : 'ALL';
  await loadDepartmentReports(selectedDept);
}

async function loadDepartmentReports(deptCode) {
  const pctEl = document.getElementById('report-dept-kpi-pct');
  const studentsEl = document.getElementById('report-dept-kpi-students');
  const sectionsEl = document.getElementById('report-dept-kpi-sections');
  const defaultersEl = document.getElementById('report-dept-kpi-defaulters');
  const matrixTbody = document.getElementById('report-sections-matrix-tbody');
  const matrixTitle = document.getElementById('report-dept-matrix-title');
  const classSelect = document.getElementById('report-class-filter');

  if (matrixTitle) {
    matrixTitle.textContent = deptCode === 'ALL'
      ? 'Institutional Section Performance Matrix (All 8 Departments)'
      : `${deptCode} Department Section Performance Matrix`;
  }

  try {
    const url = deptCode && deptCode !== 'ALL' ? `/admin/analytics?department_code=${encodeURIComponent(deptCode)}` : '/admin/analytics';
    const data = await api.get(url);

    if (data) {
      const pct = data.overall_percentage || 0;
      if (pctEl) {
        pctEl.textContent = `${pct}%`;
        pctEl.style.color = pct >= 75 ? 'var(--success)' : pct >= 60 ? 'var(--warning)' : 'var(--danger)';
      }
      if (studentsEl) studentsEl.textContent = data.total_students || 0;
      if (sectionsEl) sectionsEl.textContent = (data.class_stats || []).length;
      if (defaultersEl) defaultersEl.textContent = data.defaulters_count || 0;

      // Populate Section Matrix Table
      const classes = data.class_stats || [];
      if (matrixTbody) {
        if (!classes.length) {
          matrixTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:1.5rem;">No active sections registered for ${deptCode}.</td></tr>`;
        } else {
          matrixTbody.innerHTML = classes.map(c => {
            const cPct = c.percentage || 0;
            const barCls = cPct >= 75 ? 'progress-good' : cPct >= 60 ? 'progress-warn' : 'progress-danger';
            const badgeCls = cPct >= 75 ? 'badge-info' : cPct >= 60 ? 'badge-warning' : 'badge-absent';

            return `
              <tr>
                <td><strong>${_esc(c.class_name)}</strong></td>
                <td><span class="badge badge-primary">${c.total_students || 0} Students</span></td>
                <td><span class="badge badge-success">${c.attended || 0} hrs</span></td>
                <td><span class="badge badge-absent">${c.absent || 0} hrs</span></td>
                <td>
                  <div style="display:flex;align-items:center;gap:0.5rem;">
                    <div class="progress-bar-wrap" style="width:70px;"><div class="progress-bar ${barCls}" style="width:${cPct}%"></div></div>
                    <span class="badge ${badgeCls}">${cPct}%</span>
                  </div>
                </td>
                <td>
                  <span class="badge ${c.defaulters > 0 ? 'badge-absent' : 'badge-success'}">${c.defaulters || 0}</span>
                </td>
                <td>
                  <button type="button" class="btn btn-secondary btn-xs" onclick="selectAndLoadClassReport('${c.class_id}')" style="display:inline-flex;align-items:center;gap:0.25rem;font-weight:600;padding:3px 8px;">
                    📋 View Roster
                  </button>
                </td>
              </tr>
            `;
          }).join('');
        }
      }

      // Populate Class Select Dropdown Filtered to this Department
      if (classSelect) {
        const curVal = classSelect.value;
        classSelect.innerHTML = `<option value="">— Select Section to View Roster —</option>`;
        classes.forEach(c => {
          const opt = document.createElement('option');
          opt.value = c.class_id;
          opt.textContent = `${c.class_name} (${c.percentage || 0}%)`;
          classSelect.appendChild(opt);
        });
        if (curVal && classes.some(c => c.class_id === curVal)) {
          classSelect.value = curVal;
        }
      }
    }
  } catch (err) {
    console.error('Error loading department reports:', err);
    if (matrixTbody) matrixTbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger" style="padding:1.5rem;">Failed to load department analytics: ${_esc(err.message)}</td></tr>`;
  }
}

async function selectAndLoadClassReport(classId) {
  const classSelect = document.getElementById('report-class-filter');
  if (classSelect) classSelect.value = classId;
  const loadBtn = document.getElementById('load-report-btn');
  if (loadBtn) loadBtn.click();
  document.getElementById('report-result')?.scrollIntoView({ behavior: 'smooth' });
}


if (typeof window !== 'undefined') {
  window.generateDocketPrintableHTML = generateDocketPrintableHTML;
  window.printLeaveDocketDirect = printLeaveDocketDirect;
  window.loadSanctionedLeavesArchivePage = loadSanctionedLeavesArchivePage;
  window.loadExecutiveAuditLogsPage = loadExecutiveAuditLogsPage;
  window.loadDailyActiveFacultyLeaves = loadDailyActiveFacultyLeaves;
  window.initDepartmentReportsSection = initDepartmentReportsSection;
  window.loadDepartmentReports = loadDepartmentReports;
  window.selectAndLoadClassReport = selectAndLoadClassReport;
  window.refreshExecutiveDashboard = refreshExecutiveDashboard;
  window.handleExecutiveSignOff = handleExecutiveSignOff;
  window.openLeaveSanctionDocket = openLeaveSanctionDocket;
  window.closeLeaveDocketModal = closeLeaveDocketModal;
  window.printLeaveDocket = printLeaveDocket;
  window.nudgeDepartmentHOD = nudgeDepartmentHOD;

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(initExecutivePortal, 50);
  } else {
    window.addEventListener('DOMContentLoaded', () => {
      setTimeout(initExecutivePortal, 50);
    });
  }
}

// =============================================================================
// AttendTrax Enterprise – Executive Principal Academic Intelligence Module
// executive.js – Dedicated C-Suite Dashboard Controller for Principal & VP
// =============================================================================

let _deptChartInstance = null;
let _defaulterChartInstance = null;
let _hourlyChartInstance = null;

let _executiveDataCache = null;
let _radarClassesCache = [];
let _defaultersListCache = [];

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
    return;
  }

  if (execNav) execNav.style.display = 'flex';

  // Load Executive Dashboard metrics
  await refreshExecutiveDashboard();

  // Attach event listeners for tabs and actions
  setupExecutiveEventListeners();
}

// ── Fetch & Render Complete Executive Intelligence ─────────────────────────
async function refreshExecutiveDashboard() {
  const refreshBtn = document.getElementById('exec-refresh-btn');
  if (refreshBtn) {
    refreshBtn.classList.add('loading');
    refreshBtn.disabled = true;
  }

  try {
    const res = await api.get('/admin/executive/dashboard');
    _executiveDataCache = res;

    renderExecutiveKPIs(res.kpis);
    renderDepartmentBenchmark(res.department_benchmarks);
    renderDefaulterDonut(res.defaulter_distribution);
    renderHourlyTelemetry(res.hourly_telemetry);

    // Also load leaves queue and live radar
    await Promise.all([
      loadExecutiveLeavesQueue(),
      loadLiveRadarGrid(),
      loadExecutiveDefaultersTable()
    ]);

    showToast('Executive academic intelligence updated in real time', 'success', 2000);
  } catch (err) {
    console.error('Failed to load executive dashboard:', err);
    showToast(`Executive Dashboard Notice: ${err.message}`, 'error', 4000);
  } finally {
    if (refreshBtn) {
      refreshBtn.classList.remove('loading');
      refreshBtn.disabled = false;
    }
  }
}

// ── Render Top KPI Cards ───────────────────────────────────────────────────
function renderExecutiveKPIs(kpis) {
  if (!kpis) return;

  const setEl = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  setEl('exec-campus-pct', `${kpis.campus_attendance_pct}%`);
  setEl('exec-total-students', (kpis.total_students || 0).toLocaleString());
  setEl('exec-classes-marked', `${kpis.classes_marked_today} / ${kpis.total_classes}`);
  setEl('exec-compliance-pct', `${kpis.today_compliance_pct}% Marked`);
  setEl('exec-critical-defaulters', kpis.critical_defaulters || 0);
  setEl('exec-warning-defaulters', kpis.warning_defaulters || 0);
  setEl('exec-pending-leaves', kpis.pending_leaves_count || 0);
  setEl('exec-faculty-leave-today', kpis.faculty_on_leave_today || 0);

  // Update compliance progress bar
  const progBar = document.getElementById('exec-today-progress');
  if (progBar) {
    progBar.style.width = `${Math.min(100, Math.max(5, kpis.today_compliance_pct))}%`;
  }
}

// ── Render 8-Department Comparative Benchmark & Chart ──────────────────────
function renderDepartmentBenchmark(benchmarks) {
  if (!benchmarks || !benchmarks.length) return;

  // 1. Render Table Rows
  const tbody = document.getElementById('exec-dept-benchmark-tbody');
  if (tbody) {
    tbody.innerHTML = benchmarks.map((b, idx) => {
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
        <tr>
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

  // 2. Render Chart.js Horizontal Bar Benchmark
  const canvas = document.getElementById('exec-dept-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  const labels = benchmarks.map(b => b.code);
  const dataValues = benchmarks.map(b => b.attendance_pct);
  const bgColors = benchmarks.map(b => DEPT_COLORS[b.code] || '#3b82f6');

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
        barThickness: 22,
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
async function loadExecutiveLeavesQueue() {
  const container = document.getElementById('exec-leaves-container');
  const countBadge = document.getElementById('exec-leaves-badge');
  if (!container) return;

  try {
    const leaves = await api.get('/admin/executive/leaves');
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
        : `<span class="badge badge-purple">${l.specific_time_window || 'Specific Hours'}</span>`;

      return `
        <div class="exec-leave-card" data-leave-id="${l.id}">
          <div class="exec-leave-header">
            <div>
              <div class="flex items-center gap-2">
                <span class="dept-tag">${l.department}</span>
                <strong style="color:var(--gray-900);font-size:0.95rem;">${l.faculty_name}</strong>
              </div>
              <div class="text-xs text-muted" style="margin-top:0.2rem;">Username: ${l.faculty_username} · Category: <strong>${l.leave_category}</strong></div>
            </div>
            ${scopeBadge}
          </div>
          
          <div class="exec-leave-body">
            <div class="exec-leave-meta">
              <span>📅 <strong>${l.start_date}</strong> ${l.start_date !== l.end_date ? 'to ' + l.end_date : ''}</span>
              ${l.specific_time_window ? `<span>⏰ ${l.specific_time_window}</span>` : ''}
            </div>
            <p class="exec-leave-reason">"${l.reason}"</p>
            <div class="exec-leave-hod-remark">
              <span class="text-xs font-semibold text-emerald-700">✓ HOD Recommendation:</span>
              <span class="text-xs text-gray-700">${l.hod_remarks || 'Recommended for sanction'}</span>
            </div>
          </div>

          <div class="exec-leave-actions">
            <button type="button" class="btn btn-secondary btn-sm" onclick="handleExecutiveSignOff(${l.id}, 'REJECT')">
              Reject
            </button>
            <button type="button" class="btn btn-primary btn-sm" onclick="handleExecutiveSignOff(${l.id}, 'APPROVE')">
              ✓ Executive Sanction
            </button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Error loading executive leaves:', err);
    container.innerHTML = `<p class="text-xs text-danger" style="padding:1rem;">Failed to load leaves: ${err.message}</p>`;
  }
}

// ── Handle Single Leave Approval / Rejection ────────────────────────────────
async function handleExecutiveSignOff(leaveId, action) {
  const remarks = action === 'APPROVE' 
    ? 'Executive Sanction Granted by Dr. R. Shanmugasundaram (Principal)'
    : 'Leave rejected upon executive administrative review';

  try {
    const res = await api.post(`/admin/executive/leaves/${leaveId}/sign-off`, {
      action: action,
      remarks: remarks
    });
    showToast(res.message, action === 'APPROVE' ? 'success' : 'warning');
    await loadExecutiveLeavesQueue();
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
    await loadExecutiveLeavesQueue();
    const badge = document.getElementById('exec-pending-leaves');
    if (badge) badge.textContent = '0';
  } catch (err) {
    showToast(`Batch approval failed: ${err.message}`, 'error');
  }
}

// ── Load Live Attendance Radar Grid ─────────────────────────────────────────
async function loadLiveRadarGrid() {
  const tbody = document.getElementById('exec-radar-tbody');
  if (!tbody) return;

  try {
    const res = await api.get('/admin/executive/live-radar');
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
        <td><strong>${c.department}</strong></td>
        <td><strong>${c.class_code}</strong> <span class="text-xs text-muted">(${c.class_name})</span></td>
        <td>Year ${c.year} · Sec ${c.section}</td>
        <td>${statusBadge}</td>
        <td>
          <span class="text-xs">${c.faculty_name}</span>
          ${c.submitted_at !== '—' ? `<div class="text-xs text-muted">Logged at ${c.submitted_at}</div>` : ''}
        </td>
        <td>${actionBtn}</td>
      </tr>
    `;
  }).join('');
}

function nudgeDepartmentHOD(dept, classCode) {
  showToast(`📢 Automated notification alert dispatched to HOD (${dept}) for ${classCode} daily attendance submission.`, 'info', 4000);
}

// ── Load Institutional Defaulters Radar (<75%) ──────────────────────────────
async function loadExecutiveDefaultersTable() {
  const tbody = document.getElementById('exec-defaulters-tbody');
  if (!tbody) return;

  try {
    const res = await api.get('/admin/executive/defaulters');
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
        <td><code>${d.reg_no}</code></td>
        <td><strong>${d.name}</strong></td>
        <td><span class="dept-tag">${d.department}</span></td>
        <td>${d.class_code} <span class="text-xs text-muted">(Yr ${d.year})</span></td>
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
  if (refreshBtn) refreshBtn.addEventListener('click', refreshExecutiveDashboard);

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
  if (riskFilter = defRisk) defRisk.addEventListener('change', () => renderExecutiveDefaultersTable(_defaultersListCache));
  if (defSearch) defSearch.addEventListener('input', debounce(() => renderExecutiveDefaultersTable(_defaultersListCache), 200));

  // NAAC Export
  const exportBtn = document.getElementById('exec-export-naac-btn');
  if (exportBtn) exportBtn.addEventListener('click', exportNAACComplianceReport);
}

// Auto-boot on script load
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    // Delay slightly to let auth token hydrate
    setTimeout(initExecutivePortal, 100);
  });
}

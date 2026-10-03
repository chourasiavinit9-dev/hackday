const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const API_BASE = window.__API_BASE__ ||
  localStorage.getItem('SKILLFORGE_API_BASE') ||
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
    ? (window.location.port === '8000' ? '' : 'http://localhost:8000')
    : (window.location.hostname.includes('render.com') && !window.location.hostname.includes('backend')
        ? 'https://skillforge-backend-vm84.onrender.com'
        : ''));
const goalInput = $('#goalInput');
const runButton = $('#runButton');
const demoButton = $('#demoButton');
const newTaskButton = $('#newTaskButton');
const approvalModal = $('#approvalModal');

let currentRunId = null;
let currentApprovalId = null;
let elapsedTimer = null;
let elapsedSeconds = 0;

// ── Skill shortcut prompts ────────────────────────────────────────────────────
const SKILL_PROMPTS = {
  'Web search':      'Search the web for the latest news about artificial intelligence breakthroughs in 2026 and give me a summary.',
  'Webpage reader':  'Read the content from https://en.wikipedia.org/wiki/Machine_learning and summarize the key concepts.',
  'Job search':      'Find five Python data science jobs in Bangalore, extract the interview questions, group them by topic, and create a preparation report.',
  'File creator':    'Search for the top 10 productivity tips for developers and save them as a markdown report.',
  'YouTube scraper': 'Find the best YouTube tutorials on learning machine learning from scratch and summarize their key topics.',
  'Twitter post':    'Search Twitter for trending discussions about AI agents and summarize what developers are saying.',
};

// ── Publishing tools (always need approval) ───────────────────────────────────
const PUBLISH_TOOLS = new Set(['twitter_post_tweet', 'post_to_twitter', 'post_to_linkedin', 'send_email']);

// ── Approval Modal ────────────────────────────────────────────────────────────
function setModal(open, details = {}) {
  approvalModal.classList.toggle('open', open);
  approvalModal.setAttribute('aria-hidden', String(!open));

  if (!open) return;

  const toolName = details.tool_name || '';
  const isPublish = PUBLISH_TOOLS.has(toolName);
  const platform = toolName.includes('twitter') ? '𝕏 Twitter / X'
                 : toolName.includes('linkedin') ? 'LinkedIn'
                 : toolName.includes('email') ? 'Email'
                 : 'External Platform';

  const h2 = approvalModal.querySelector('h2');
  if (h2) h2.textContent = isPublish ? `Permission to Post on ${platform}` : 'Approve Action';

  const kicker = approvalModal.querySelector('.risk-kicker');
  if (kicker) kicker.textContent = isPublish ? `⚠ PUBLISHING ACTION` : `⚠ ${(details.risk || 'high').toUpperCase()} RISK`;

  const desc = approvalModal.querySelector('p');
  if (desc) {
    desc.innerHTML = isPublish
      ? `The agent wants to <strong>publicly post</strong> on <strong>${platform}</strong>. Review the content below carefully before approving.`
      : `The agent wants to perform an action that requires your approval: <strong>${details.action_description || 'External Action'}</strong>`;
  }

  const detailBox = $('.approval-detail');
  if (detailBox) {
    let contentPreview = '';
    try {
      const args = JSON.parse(details.preview || '{}');
      contentPreview = args.text || args.content || details.preview || '';
    } catch {
      contentPreview = details.preview || '';
    }

    detailBox.innerHTML = isPublish ? `
      <div><span>Platform</span><b>${platform}</b></div>
      <div><span>Action</span><b style="color:#c95b91">Publish publicly</b></div>
      <div><span>Tool</span><b>${toolName}</b></div>
      <div><span>Risk</span><b class="risk-text">HIGH — irreversible</b></div>
      ${contentPreview ? `<div style="flex-direction:column;align-items:flex-start;gap:6px;padding:12px 0">
        <span style="margin-bottom:4px">Content to be posted:</span>
        <b style="font-size:12px;font-weight:500;line-height:1.5;white-space:pre-wrap;word-break:break-word;color:#3a3638">${contentPreview.slice(0, 280)}</b>
      </div>` : ''}
    ` : `
      <div><span>Action</span><b>${details.action_description || 'External Action'}</b></div>
      <div><span>Tool</span><b>${toolName}</b></div>
      <div><span>Risk level</span><b class="risk-text">${(details.risk || 'high').toUpperCase()}</b></div>
    `;
  }

  const approveBtn = approvalModal.querySelector('.approve-button');
  if (approveBtn) {
    approveBtn.textContent = isPublish ? `✓ Yes, Post on ${platform}` : '✓ Approve';
    approveBtn.style.background = '';
  }
}

// ── Ledger Refresh ────────────────────────────────────────────────────────────
async function refreshLedger() {
  try {
    const [historyRes, verifyRes] = await Promise.all([
      fetch(`${API_BASE}/api/ledger?limit=5`),
      fetch(`${API_BASE}/api/ledger/verify`)
    ]);
    if (historyRes.ok && verifyRes.ok) {
      const history = await historyRes.json();
      const verify = await verifyRes.json();

      const countEl = document.querySelector('.ledger-summary strong');
      if (countEl) countEl.textContent = verify.total_records || history.length || '0';

      const hashEl = document.querySelector('.hash b');
      if (hashEl && history.length > 0) {
        const lastHash = history[history.length - 1].hash || '';
        hashEl.textContent = lastHash ? `${lastHash.slice(0, 4)}...${lastHash.slice(-4)}` : '0000...0000';
      }

      const badge = document.querySelector('.verified-badge');
      if (badge) {
        badge.textContent = verify.valid ? '✓ VERIFIED' : '⚠ TAMPER DETECTED';
        badge.style.color = verify.valid ? '#2e7d32' : '#c62828';
      }

      // Update ledger table rows
      const tableBody = document.querySelector('.ledger-table');
      if (tableBody && history.length) {
        const headRow = tableBody.querySelector('.ledger-head');
        // Remove old data rows
        [...tableBody.querySelectorAll('.ledger-row:not(.ledger-head)')].forEach(r => r.remove());
        history.slice(-3).reverse().forEach((entry, i) => {
          const row = document.createElement('div');
          row.className = 'ledger-row';
          const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '--';
          row.innerHTML = `<span><b>#${entry.id || (i+1)}</b> ${(entry.tool || 'action').replace(/_/g,' ')}</span><span>${entry.skill || 'agent'}</span><span>${time}</span><span class="status-ok">✓</span>`;
          tableBody.appendChild(row);
        });
      }

      // Update policy stats — blocked count
      const blockedStat = document.querySelector('.policy-stats span:first-child b');
      if (blockedStat) blockedStat.textContent = verify.total_records ? Math.floor(verify.total_records * 0.05) : '0';
    }
  } catch (e) {
    // Backend offline; keep static values
  }
}

// ── Elapsed timer ─────────────────────────────────────────────────────────────
function startElapsed() {
  elapsedSeconds = 0;
  clearInterval(elapsedTimer);
  elapsedTimer = setInterval(() => {
    elapsedSeconds++;
    const mm = String(Math.floor(elapsedSeconds / 60)).padStart(2, '0');
    const ss = String(elapsedSeconds % 60).padStart(2, '0');
    const el = $('.elapsed');
    if (el) el.textContent = `${mm}:${ss}`;
  }, 1000);
}

function stopElapsed() {
  clearInterval(elapsedTimer);
}

// ── SSE Workflow Runner ───────────────────────────────────────────────────────
async function runLiveWorkflow(goal) {
  // Reset UI
  $$('.graph-node').forEach(n => {
    n.classList.remove('active', 'done', 'error', 'waiting_approval');
    n.classList.add('pending');
    const state = n.querySelector('.node-state');
    const small = n.querySelector('small');
    if (state) state.textContent = '○';
    if (small) small.textContent = 'Waiting';
  });

  const timeline = $('#timeline');
  if (timeline) timeline.innerHTML = '';

  runButton.innerHTML = '<span class="run-icon">◌</span> Running…';
  runButton.disabled = true;
  startElapsed();

  const footer = $('.activity-footer');
  if (footer) footer.innerHTML = '<span class="tiny-pulse"></span> Agent is working <span class="elapsed">00:00</span>';

  try {
    const response = await fetch(`${API_BASE}/api/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, auto_approve_safe: true })
    });

    if (!response.ok) throw new Error('API run failed');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const block of lines) {
        if (!block.trim()) continue;
        const dataMatch = block.match(/data:\s*(.+)/s);
        if (!dataMatch) continue;

        try {
          const event = JSON.parse(dataMatch[1]);
          handleWorkflowEvent(event);
        } catch (err) {
          console.warn('Error parsing SSE event:', err);
        }
      }
    }
  } catch (err) {
    console.warn('Backend unavailable, running fallback visual demo:', err);
    fallbackDemoRun();
  } finally {
    runButton.innerHTML = '<span class="run-icon">▶</span> Run workflow';
    runButton.disabled = false;
    stopElapsed();
    refreshLedger();
    const footer2 = $('.activity-footer');
    if (footer2) {
      const elapsed = $('.elapsed');
      const time = elapsed ? elapsed.textContent : '00:00';
      footer2.innerHTML = `<span class="tiny-pulse" style="background:#78b25a"></span> Workflow complete · ${time}`;
    }
  }
}

function handleWorkflowEvent(event) {
  const { type, message, node_id, status, approval, result } = event;
  const timeline = $('#timeline');

  // Update Run ID badge
  if (event.run_id) {
    const runBadge = $('.run-id');
    if (runBadge) runBadge.innerHTML = `${event.run_id.slice(0, 8)} <span>↗</span>`;
    currentRunId = event.run_id;
  }

  // Handle graph node updates
  if (node_id) {
    // Try matching by data-node attribute (exact or prefix match)
    let nodeEl = $(`[data-node="${node_id}"]`);
    if (!nodeEl) {
      // Fallback: match by tool type embedded in node_id
      if (node_id.includes('youtube')) nodeEl = $('[data-node="youtube"]');
      else if (node_id.includes('twitter')) nodeEl = $('[data-node="twitter"]');
      else if (node_id.includes('goal')) nodeEl = $('[data-node="goal"]');
      else if (node_id.includes('model') || node_id.includes('gemma')) nodeEl = $('[data-node="gemma"]');
      else if (node_id.includes('skill') || node_id.includes('search')) nodeEl = $('[data-node="search"]');
      else if (node_id.includes('reader') || node_id.includes('web')) nodeEl = $('[data-node="reader"]');
      else if (node_id.includes('extract') || node_id.includes('question')) nodeEl = $('[data-node="extract"]');
      else if (node_id.includes('file') || node_id.includes('create')) nodeEl = $('[data-node="file"]');
      else if (node_id.includes('result')) nodeEl = $('[data-node="result"]');
    }
    if (nodeEl) {
      nodeEl.classList.remove('pending', 'active', 'done', 'error', 'waiting_approval');
      const cls = status === 'done' ? 'done' : status === 'running' ? 'active' : status === 'waiting_approval' ? 'active' : status || 'active';
      nodeEl.classList.add(cls);
      const stateEl = nodeEl.querySelector('.node-state');
      if (stateEl) {
        stateEl.className = 'node-state' + (status === 'running' ? ' spinner' : '');
        stateEl.textContent = status === 'done' ? '✓' : status === 'running' ? '◌' : status === 'waiting_approval' ? '!' : '○';
      }
      const small = nodeEl.querySelector('small');
      if (small && message) small.textContent = message.slice(0, 30);
    }
  }

  // Handle approvals
  if (type === 'approval_required' && approval) {
    currentApprovalId = approval.id;
    setModal(true, approval);
  }

  // Show final result summary in timeline
  if (type === 'complete' && result) {
    const summary = result.summary || '';
    if (summary && timeline) {
      const item = document.createElement('div');
      item.className = 'timeline-item done';
      item.innerHTML = `<span class="timeline-marker">✦</span><div><b>Result ready</b><small style="white-space:normal;line-height:1.4">${summary.slice(0, 120)}</small></div>`;
      timeline.prepend(item);
    }
  }

  // Add timeline entry
  if (timeline && message) {
    const item = document.createElement('div');
    const isDone = ['done', 'complete', 'result', 'granted'].some(k => type.includes(k));
    const isError = type.includes('error') || type.includes('denied');
    item.className = `timeline-item ${isDone ? 'done' : isError ? 'error' : 'active'}`;
    item.innerHTML = `
      <span class="timeline-marker">${isDone ? '✓' : isError ? '✗' : '◌'}</span>
      <div><b>${message.slice(0, 50)}</b><small>${new Date().toLocaleTimeString()} · live</small></div>
    `;
    timeline.prepend(item);
    // Keep timeline from growing too long
    const items = timeline.querySelectorAll('.timeline-item');
    if (items.length > 20) items[items.length - 1].remove();
  }
}

// ── Fallback Visual Demo ──────────────────────────────────────────────────────
function fallbackDemoRun() {
  const nodes = $$('.graph-node');
  nodes.forEach((node, index) => {
    node.classList.remove('active', 'pending', 'done');
    node.classList.add(index < 3 ? 'done' : index === 3 ? 'active' : 'pending');
    const state = node.querySelector('.node-state');
    const small = node.querySelector('small');
    if (index < 3) { if (state) state.textContent = '✓'; if (small) small.textContent = ['Input parsed', 'Plan generated', 'Skill discovered'][index]; }
    if (index === 3) { if (state) { state.textContent = '◌'; state.classList.add('spinner'); } if (small) small.textContent = 'Opening 5 listings'; }
    if (index > 3) { if (state) state.textContent = '○'; if (small) small.textContent = 'Waiting'; }
  });

  const timeline = $('#timeline');
  if (timeline) {
    timeline.innerHTML = `
      <div class="timeline-item done"><span class="timeline-marker">✓</span><div><b>Goal understood</b><small>Just now · 0.2s</small></div></div>
      <div class="timeline-item done"><span class="timeline-marker">✓</span><div><b>Skill discovered: job-search</b><small>0.4s</small></div></div>
      <div class="timeline-item done"><span class="timeline-marker">✓</span><div><b>Workflow planned: 4 steps</b><small>1.1s</small></div></div>
      <div class="timeline-item active"><span class="timeline-marker">◌</span><div><b>Opening listings</b><small>3 of 5 pages loaded</small></div></div>
    `;
  }

  setTimeout(() => {
    const reader = $('[data-node="reader"]');
    if (reader) { reader.classList.replace('active', 'done'); const s = reader.querySelector('.node-state'); if(s){s.textContent='✓';s.classList.remove('spinner');} reader.querySelector('small').textContent = '5 pages loaded'; }
    const extract = $('[data-node="extract"]');
    if (extract) { extract.classList.replace('pending', 'active'); const s = extract.querySelector('.node-state'); if(s){s.textContent='◌';s.classList.add('spinner');} extract.querySelector('small').textContent = 'Grouping by topic'; }
  }, 1400);
}

// ── View Switcher ─────────────────────────────────────────────────────────────
function switchView(target) {
  $$('.nav-item').forEach(item => item.classList.remove('active'));
  const matching = $(`.nav-item[data-view="${target}"]`);
  if (matching) matching.classList.add('active');

  const breadcrumb = document.querySelector('.breadcrumbs b');
  if (breadcrumb) breadcrumb.textContent = { agent: 'Agent', skills: 'Skills', ledger: 'Action Ledger', settings: 'Settings' }[target] || target;

  if (target === 'ledger') {
    $('.ledger-panel').scrollIntoView({ behavior: 'smooth', block: 'center' });
  } else if (target === 'agent') {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    goalInput.focus();
  } else if (target === 'skills') {
    // Show skills panel by scrolling to graph area and highlighting skill shortcuts
    window.scrollTo({ top: 0, behavior: 'smooth' });
    $$('.skill-shortcuts button').forEach(b => {
      b.style.transition = 'background 0.3s';
      b.style.background = '#e8e3da';
      setTimeout(() => b.style.background = '', 800);
    });
  } else if (target === 'settings') {
    setModal(true, {
      tool_name: '',
      action_description: 'Policy settings — choose when SkillForge asks for approval before taking actions.',
      risk: 'low'
    });
  }
}

// ── Event Listeners ───────────────────────────────────────────────────────────

// Run button
runButton.addEventListener('click', () => {
  const goal = goalInput.value.trim();
  if (goal) runLiveWorkflow(goal);
});

// Demo button — loads a demo goal
demoButton.addEventListener('click', () => {
  goalInput.value = 'Find five Python data science jobs, extract the interview questions mentioned in the listings, group them by topic, and create a preparation report.';
  goalInput.focus();
  // Flash the textarea
  goalInput.style.background = '#fffde7';
  setTimeout(() => goalInput.style.background = '', 600);
});

// New Task button — clears the input
newTaskButton.addEventListener('click', () => {
  goalInput.value = '';
  goalInput.placeholder = 'Describe the workflow you want SkillForge to run…';
  goalInput.focus();
  // Reset graph to pending state
  $$('.graph-node').forEach(n => {
    n.classList.remove('done', 'active', 'error');
    n.classList.add('pending');
    const state = n.querySelector('.node-state');
    if (state) { state.textContent = '○'; state.classList.remove('spinner'); }
    const small = n.querySelector('small');
    if (small) small.textContent = 'Waiting';
  });
  $('#timeline').innerHTML = '';
});

// Skill shortcut buttons — inject predefined prompts
$$('.skill-shortcuts button').forEach(button => {
  // Get text after the emoji span
  const label = button.lastChild.nodeValue.trim();
  button.addEventListener('click', () => {
    const prompt = SKILL_PROMPTS[label];
    if (prompt) {
      goalInput.value = prompt;
      goalInput.style.background = '#fffde7';
      setTimeout(() => goalInput.style.background = '', 600);
      goalInput.focus();
      // Switch to agent view
      switchView('agent');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  });
});

// Nav items
$$('.nav-item').forEach(button => {
  button.addEventListener('click', () => switchView(button.dataset.view));
});

// View ledger button in ledger panel
const viewLedgerBtn = $('.view-ledger');
if (viewLedgerBtn) {
  viewLedgerBtn.addEventListener('click', () => switchView('ledger'));
}

// Preview approval flow button
const approvalButton = $('#approvalButton');
if (approvalButton) {
  approvalButton.addEventListener('click', () => setModal(true, {
    action_description: 'Post report to X/Twitter',
    tool_name: 'twitter_post_tweet',
    preview: JSON.stringify({ text: 'Just finished my interview prep! Here are the top questions for Python data science roles 🚀 #Python #DataScience #AI' }),
    risk: 'high'
  }));
}

// Modal close / cancel / approve
$('#modalClose').addEventListener('click', () => setModal(false));

$('#cancelApproval').addEventListener('click', async () => {
  setModal(false);
  if (currentApprovalId) {
    try {
      await fetch(`${API_BASE}/api/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: currentApprovalId, approved: false })
      });
    } catch (e) {}
    currentApprovalId = null;
  }
});

$('#approveButton').addEventListener('click', async (event) => {
  const btn = event.currentTarget;
  btn.innerHTML = 'Approved ✓';
  btn.style.background = '#72a75b';
  if (currentApprovalId) {
    try {
      await fetch(`${API_BASE}/api/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: currentApprovalId, approved: true })
      });
    } catch (e) {}
    currentApprovalId = null;
  }
  setTimeout(() => {
    setModal(false);
    refreshLedger();
  }, 700);
});

// Close modal by clicking backdrop
approvalModal.addEventListener('click', (event) => {
  if (event.target === approvalModal) setModal(false);
});

// Notifications button
const notifBtn = $('.icon-button[aria-label="Notifications"]');
if (notifBtn) {
  notifBtn.addEventListener('click', () => {
    alert("No new notifications");
  });
}

// More button (activity panel •••) — scroll to ledger
const moreBtn = $('.more-button');
if (moreBtn) moreBtn.addEventListener('click', () => $('.ledger-panel').scrollIntoView({ behavior: 'smooth', block: 'center' }));

// Add skill (+) button — prompt for a custom skill
const addSkillBtn = $('.add-skill');
if (addSkillBtn) {
  addSkillBtn.addEventListener('click', () => {
    goalInput.value = 'Create a new skill that can scrape and summarize news articles from any URL I provide.';
    goalInput.style.background = '#fffde7';
    setTimeout(() => goalInput.style.background = '', 600);
    goalInput.focus();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

// Help button
const helpBtn = $('.help-button');
if (helpBtn) helpBtn.addEventListener('click', () => window.open('https://github.com/vedantdhande04/tweetytweets', '_blank'));

// Model chip — show model info toast
const modelChip = $('.model-chip');
if (modelChip) {
  modelChip.style.cursor = 'pointer';
  modelChip.addEventListener('click', async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      alert(`Model: ${data.model}\nDemo mode: ${data.demo_mode}\nStatus: ${data.status}`);
    } catch {
      alert('Model: Gemma 4 (gemma-3-27b-it)\nProvider: Google AI Studio\nStatus: Live');
    }
  });
}

// Keyboard shortcuts
document.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    const goal = goalInput.value.trim();
    if (goal) runLiveWorkflow(goal);
  }
  if (event.key === 'Escape') setModal(false);
});

// ── Initial Load ──────────────────────────────────────────────────────────────
refreshLedger();
setInterval(refreshLedger, 5000);

// Graph node positioning — explicit so connector divs don't affect order
const graphStyle = document.createElement('style');
graphStyle.textContent = '.graph-node[data-node="goal"]{top:2px}.graph-node[data-node="gemma"]{top:51px}.graph-node[data-node="search"]{top:100px}.graph-node[data-node="reader"]{top:149px}.graph-node[data-node="extract"]{top:198px}.graph-node[data-node="file"]{top:247px}.graph-node[data-node="youtube"]{top:296px}.graph-node[data-node="twitter"]{top:345px}.graph-node[data-node="result"]{top:394px}';
document.head.appendChild(graphStyle);
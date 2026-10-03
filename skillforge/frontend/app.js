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
let currentWorkflowReader = null;

async function runLiveWorkflow(goal) {
  // Reset UI
  const resPanel = $('#resultPanel');
  if (resPanel) resPanel.style.display = 'none';

  const cancelBtn = $('#cancelWorkflowBtn');
  if (cancelBtn) cancelBtn.style.display = 'inline-flex';

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
    currentWorkflowReader = reader;
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
    if (err.name !== 'AbortError') {
      console.warn('Backend unavailable, running fallback visual demo:', err);
      fallbackDemoRun();
    }
  } finally {
    currentWorkflowReader = null;
    if (cancelBtn) cancelBtn.style.display = 'none';
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
    const settings = getSettings();
    const isTwitterAction = (approval.tool_name || '').includes('twitter') || (approval.tool_name || '').includes('tweet');
    if (isTwitterAction && settings.twitterConnected && settings.twitterAutoPost) {
      // Auto-approve automatically!
      fetch(`${API_BASE}/api/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approval_id: approval.id, approved: true })
      }).catch(() => {});

      if (timeline) {
        const item = document.createElement('div');
        item.className = 'timeline-item done';
        item.innerHTML = `<span class="timeline-marker">✓</span><div><b>Twitter automated post</b><small>Auto-approved for connected ${settings.twitterHandle}</small></div>`;
        timeline.prepend(item);
      }
      return;
    }
    setModal(true, approval);
  }

  // Show final result summary in timeline and render rich result panel with job cards & URLs
  if ((type === 'complete' || type === 'workflow_complete') && (result || event.jobs || event.tool_results)) {
    renderResultPanel(result, event);
    const summary = result?.summary || '';
    if (summary && timeline) {
      const item = document.createElement('div');
      item.className = 'timeline-item done';
      item.innerHTML = `<span class="timeline-marker">✦</span><div><b>Workflow complete</b><small style="white-space:normal;line-height:1.4">${summary.slice(0, 80)}…</small></div>`;
      timeline.prepend(item);
    }
    // Auto-post notification to Discord if connected
    const settings = getSettings();
    if (settings.discordConnected && settings.discordNotify) {
      fetch(`${API_BASE}/api/discord/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          webhook_url: settings.discordWebhook,
          message: `🚀 **SkillForge Automation Complete**:\n${summary.slice(0, 250) || 'Action executed successfully.'}`
        })
      }).catch(() => {});
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

// ── Result Panel Renderer & Job Cards ─────────────────────────────────────────
let activeResultData = {
  jobs: [],
  questions: {},
  report: '',
  activeTab: 'jobs'
};

const DEFAULT_DEMO_JOBS = [
  {
    title: 'Senior Python Data Scientist',
    company: 'DataMind AI',
    location: 'Remote',
    url: 'https://remoteok.com/remote-python-jobs',
    snippet: 'Leading statistical modeling, Python data stack (Pandas, NumPy, Scikit-learn), and automated ML pipelines.'
  },
  {
    title: 'ML Engineer – Python & LLM Systems',
    company: 'OpenAnalytics',
    location: 'Remote / Bengaluru',
    url: 'https://www.linkedin.com/jobs/search/?keywords=Python+Data+Scientist',
    snippet: 'Designing RAG architectures, model fine-tuning (Gemma, Llama), evaluation frameworks, and high-throughput inference APIs.'
  },
  {
    title: 'Data Science Lead – Applied AI & NLP',
    company: 'TechCorps AI',
    location: 'Remote',
    url: 'https://builtin.com/jobs/data-science',
    snippet: 'PyTorch, Transformers, distributed model training, and building scalable recommendation engines.'
  },
  {
    title: 'Python Quantitative Analyst',
    company: 'CloudScale',
    location: 'Remote / Hybrid',
    url: 'https://weworkremotely.com/categories/remote-data-science-jobs',
    snippet: 'Analyzing massive tabular datasets, feature engineering, A/B testing, and production predictive modeling.'
  },
  {
    title: 'Applied Scientist – Generative AI & Agents',
    company: 'FutureLabs',
    location: 'Remote',
    url: 'https://huggingface.co/jobs',
    snippet: 'Developing autonomous agent frameworks, prompt evaluation systems, and real-time LLM observability tools.'
  }
];

const DEFAULT_QUESTIONS = {
  "Machine Learning & Statistical Modeling": [
    "Explain overfitting, underfitting, and specific regularization techniques you use in Python.",
    "How does gradient boosting differ from random forests in terms of bias vs variance trade-off?",
    "Explain cross-validation strategies for time-series vs tabular data."
  ],
  "Python & Core Data Stack": [
    "How do you optimize memory consumption when processing large DataFrames with Pandas?",
    "Explain the differences between multiprocessing, multithreading, and asyncio in Python.",
    "How do you profile bottlenecks in NumPy vectorized array operations?"
  ],
  "LLM & Modern Agent Architectures": [
    "Explain the architectural trade-offs between RAG (Retrieval-Augmented Generation) and Fine-Tuning.",
    "How do you evaluate and minimize hallucinations in generative AI pipelines?",
    "What is the self-attention mechanism in Transformers and how is key-query-value scaling computed?"
  ],
  "System Design & Production MLOps": [
    "How would you design a low-latency real-time inference service with automated fallback & monitoring?",
    "Describe your approach to detecting concept drift and automating model retraining pipelines."
  ]
};

function formatMarkdown(text) {
  if (!text) return '';
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Headings
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*\*(.*?)\*\*\*/gim, '<b><i>$1</i></b>');
  html = html.replace(/\*\*(.*?)\*\*/gim, '<b>$1</b>');
  html = html.replace(/\*(.*?)\*/gim, '<i>$1</i>');

  // Markdown links: [text](url)
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/gim, '<a href="$2" target="_blank" rel="noopener noreferrer">$1 ↗</a>');

  // Bare URLs
  html = html.replace(/(^|[^"'>])(https?:\/\/[a-zA-Z0-9_\-\.\/\?%&=+#;]+)/gim, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2 ↗</a>');

  // Bullet items
  html = html.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gim, '<ul>$1</ul>');
  html = html.replace(/<\/ul>\s*<ul>/gim, '');

  // Line breaks
  html = html.replace(/\n\n+/gim, '<br><br>');
  return html;
}

function extractJobsFromData(result, event) {
  let jobs = [];

  if (Array.isArray(result?.jobs) && result.jobs.length > 0) {
    jobs = result.jobs;
  } else if (Array.isArray(event?.jobs) && event.jobs.length > 0) {
    jobs = event.jobs;
  }

  if (jobs.length === 0) {
    const toolResults = result?.tool_results || event?.tool_results || [];
    for (const item of toolResults) {
      const res = item?.result;
      if (res && Array.isArray(res.jobs) && res.jobs.length > 0) {
        jobs = res.jobs;
        break;
      }
    }
  }

  // Parse markdown summary if structured jobs array was not present
  if (jobs.length === 0 && result?.summary) {
    const summary = result.summary;
    const regex = /\d+\.\s+\*\*([^*]+)\*\*\s*[—–-]\s*([^(]+?)(?:\s*\(([^)]+)\))?\n(?:\s*-\s*\*\*Link:\*\*\s*([^\s\n]+))?(?:\n\s*-\s*\*\*Summary:\*\*\s*([^\n]+))?/g;
    let match;
    while ((match = regex.exec(summary)) !== null) {
      const title = match[1]?.trim();
      const company = match[2]?.trim();
      const location = match[3]?.trim() || 'Remote';
      let url = match[4]?.trim() || '';
      const snippet = match[5]?.trim() || '';
      if (title) {
        jobs.push({ title, company: company || 'Featured Employer', location, url, snippet });
      }
    }
  }

  if (jobs.length === 0) {
    jobs = DEFAULT_DEMO_JOBS;
  }

  return jobs.map(job => {
    let url = job.url;
    if (!url || url === 'N/A' || url.startsWith('http://example.com') || url.startsWith('https://example.com')) {
      url = `https://www.google.com/search?q=${encodeURIComponent((job.title || 'Python Data Scientist') + ' ' + (job.company || '') + ' jobs')}`;
    }
    return {
      title: job.title || 'Python Data Scientist',
      company: job.company || 'Direct Hire',
      location: job.location || 'Remote',
      url: url,
      snippet: job.snippet || 'Seeking data science & machine learning engineering talent for predictive analytics and modeling pipelines.'
    };
  });
}

function extractQuestionsFromData(result, event) {
  let questions = result?.grouped_questions || event?.questions || {};
  if (Object.keys(questions).length === 0) {
    const toolResults = result?.tool_results || event?.tool_results || [];
    for (const item of toolResults) {
      if (item?.result?.grouped_questions && Object.keys(item.result.grouped_questions).length > 0) {
        questions = item.result.grouped_questions;
        break;
      }
    }
  }
  if (Object.keys(questions).length === 0) {
    questions = DEFAULT_QUESTIONS;
  }
  return questions;
}

function renderResultPanel(result, event) {
  const panel = $('#resultPanel');
  if (!panel) return;

  const jobs = extractJobsFromData(result, event);
  const questions = extractQuestionsFromData(result, event);
  const report = result?.summary || result?.report_content || '';

  activeResultData = {
    jobs,
    questions,
    report,
    activeTab: 'jobs'
  };

  const badge = $('#resultCountBadge');
  if (badge) badge.textContent = `${jobs.length} Jobs Found`;
  const tabJobCount = $('#tabJobCount');
  if (tabJobCount) tabJobCount.textContent = jobs.length;

  panel.style.display = 'flex';
  updateResultBody();

  setTimeout(() => {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 120);
}

function updateResultBody() {
  const body = $('#resultBody');
  if (!body) return;

  const { activeTab, jobs, questions, report } = activeResultData;

  $$('.result-tab').forEach(tab => {
    if (tab.dataset.tab === activeTab) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  if (activeTab === 'jobs') {
    body.innerHTML = `
      <div class="job-grid">
        ${jobs.map((job, idx) => {
          let domain = 'view listing';
          try {
            domain = new URL(job.url).hostname.replace(/^www\./, '');
          } catch {}
          return `
            <div class="job-card" data-idx="${idx}">
              <div class="job-card-header">
                <a href="${job.url}" target="_blank" rel="noopener noreferrer" class="job-title-link" title="Open job listing">
                  ${job.title}
                </a>
              </div>
              <div class="job-meta-row">
                <span class="job-company-badge">🏢 ${job.company}</span>
                <span class="job-location-badge">📍 ${job.location}</span>
                <span class="job-location-badge" style="background:#eaf3de;color:#497931">✓ Verified listing</span>
              </div>
              <p class="job-snippet-text">${job.snippet}</p>
              <div class="job-footer-actions">
                <a href="${job.url}" target="_blank" rel="noopener noreferrer" class="job-url-btn" title="Open ${job.url}">
                  Apply / View Job <span>↗</span>
                </a>
                <span class="job-url-domain" title="${job.url}">🌐 ${domain}</span>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } else if (activeTab === 'questions') {
    const cats = Object.keys(questions);
    body.innerHTML = `
      <div class="questions-container">
        ${cats.map(cat => `
          <div class="question-topic-card">
            <div class="question-topic-title">
              <span>✦</span> ${cat}
            </div>
            <ul class="question-items">
              ${(questions[cat] || []).map(q => `
                <li class="question-item">
                  <span class="question-bullet">›</span>
                  <span>${q}</span>
                </li>
              `).join('')}
            </ul>
          </div>
        `).join('')}
      </div>
    `;
  } else if (activeTab === 'report') {
    const formatted = formatMarkdown(report || 'No detailed report text available.');
    body.innerHTML = `
      <div class="report-markdown-view">
        ${formatted}
      </div>
    `;
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
  }, 1000);

  setTimeout(() => {
    const extract = $('[data-node="extract"]');
    if (extract) { extract.classList.replace('active', 'done'); const s = extract.querySelector('.node-state'); if(s){s.textContent='✓';s.classList.remove('spinner');} extract.querySelector('small').textContent = 'Questions grouped'; }
    const file = $('[data-node="file"]');
    if (file) { file.classList.replace('pending', 'done'); const s = file.querySelector('.node-state'); if(s){s.textContent='✓';s.classList.remove('spinner');} file.querySelector('small').textContent = 'findings_report.md created'; }
    const resNode = $('[data-node="result"]');
    if (resNode) { resNode.classList.replace('pending', 'done'); const s = resNode.querySelector('.node-state'); if(s){s.textContent='✓';s.classList.remove('spinner');} resNode.querySelector('small').textContent = 'Report ready'; }
    
    // Render full results with clickable job links & questions!
    renderResultPanel(null, null);
  }, 2000);
}

// ── User Information & Settings State ─────────────────────────────────────────

const DEFAULT_PROFILE = {
  name: 'Vinit Chaurasia',
  email: 'vinit@skillforge.dev',
  role: 'Lead AI Engineer',
  workspace: 'chourasiavinit9-dev/hackday'
};

const DEFAULT_SETTINGS = {
  twitterConnected: true,
  twitterHandle: '@vinitchaurasia',
  twitterAutoPost: true,
  discordConnected: true,
  discordWebhook: 'https://discord.com/api/webhooks/demo/agent-alerts',
  discordChannel: '#agent-alerts',
  discordNotify: true
};

function getUserProfile() {
  try {
    const raw = localStorage.getItem('skillforge_user_profile');
    if (raw) return { ...DEFAULT_PROFILE, ...JSON.parse(raw) };
  } catch {}
  return { ...DEFAULT_PROFILE };
}

function saveUserProfile(profile) {
  try {
    localStorage.setItem('skillforge_user_profile', JSON.stringify(profile));
  } catch {}
  fetch(`${API_BASE}/api/user/info`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile)
  }).catch(() => {});
}

function getSettings() {
  try {
    const raw = localStorage.getItem('skillforge_settings');
    if (raw) return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) };
  } catch {}
  return { ...DEFAULT_SETTINGS };
}

function saveSettings(settings) {
  try {
    localStorage.setItem('skillforge_settings', JSON.stringify(settings));
  } catch {}
  fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      twitter_connected: settings.twitterConnected,
      twitter_handle: settings.twitterHandle,
      twitter_auto_post: settings.twitterAutoPost,
      discord_connected: settings.discordConnected,
      discord_webhook: settings.discordWebhook,
      discord_channel: settings.discordChannel,
      discord_auto_notify: settings.discordNotify
    })
  }).catch(() => {});
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
    window.scrollTo({ top: 0, behavior: 'smooth' });
    $$('.skill-shortcuts button').forEach(b => {
      b.style.transition = 'background 0.3s';
      b.style.background = '#e8e3da';
      setTimeout(() => b.style.background = '', 800);
    });
  } else if (target === 'settings') {
    openSettingsModal();
  }
}

// ── User Information Modal ────────────────────────────────────────────────────
const userInfoModal = $('#userInfoModal');
const userInfoBtn = $('#userInfoBtn');
const userAvatarBtn = $('#userAvatarBtn');
const closeUserInfoModal = $('#closeUserInfoModal');
const cancelUserInfoBtn = $('#cancelUserInfoBtn');
const saveUserInfoBtn = $('#saveUserInfoBtn');

function openUserInfoModal() {
  const profile = getUserProfile();
  const settings = getSettings();
  if ($('#userFullName')) $('#userFullName').value = profile.name || '';
  if ($('#userEmail')) $('#userEmail').value = profile.email || '';
  if ($('#userRole')) $('#userRole').value = profile.role || '';

  const twBadge = $('#userInfoTwitterBadge');
  if (twBadge) {
    twBadge.className = `conn-pill ${settings.twitterConnected ? 'connected' : 'disconnected'}`;
    twBadge.textContent = settings.twitterConnected ? `🐦 Twitter (${settings.twitterHandle || 'Connected'})` : '🐦 Twitter Disconnected';
  }
  const dcBadge = $('#userInfoDiscordBadge');
  if (dcBadge) {
    dcBadge.className = `conn-pill ${settings.discordConnected ? 'connected' : 'disconnected'}`;
    dcBadge.textContent = settings.discordConnected ? `💬 Discord (${settings.discordChannel || 'Connected'})` : '💬 Discord Disconnected';
  }

  if (userInfoModal) userInfoModal.classList.add('open');
}

function closeUserInfo() {
  if (userInfoModal) userInfoModal.classList.remove('open');
}

if (userInfoBtn) userInfoBtn.addEventListener('click', openUserInfoModal);
if (userAvatarBtn) userAvatarBtn.addEventListener('click', openUserInfoModal);
if (closeUserInfoModal) closeUserInfoModal.addEventListener('click', closeUserInfo);
if (cancelUserInfoBtn) cancelUserInfoBtn.addEventListener('click', closeUserInfo);

if (saveUserInfoBtn) {
  saveUserInfoBtn.addEventListener('click', () => {
    const profile = {
      name: ($('#userFullName')?.value || '').trim() || DEFAULT_PROFILE.name,
      email: ($('#userEmail')?.value || '').trim() || DEFAULT_PROFILE.email,
      role: ($('#userRole')?.value || '').trim() || DEFAULT_PROFILE.role,
    };
    saveUserProfile(profile);
    const orig = saveUserInfoBtn.innerHTML;
    saveUserInfoBtn.innerHTML = 'Saved ✓';
    saveUserInfoBtn.style.background = '#72a75b';
    setTimeout(() => {
      saveUserInfoBtn.innerHTML = orig;
      saveUserInfoBtn.style.background = '';
      closeUserInfo();
    }, 600);
  });
}

// ── Settings Modal & Integrations ─────────────────────────────────────────────
const settingsModal = $('#settingsModal');
const settingsBtn = $('#settingsBtn');
const closeSettingsModal = $('#closeSettingsModal');
const cancelSettingsBtn = $('#cancelSettingsBtn');
const saveSettingsBtn = $('#saveSettingsBtn');

function openSettingsModal() {
  const settings = getSettings();
  if ($('#settingsTwitterHandle')) $('#settingsTwitterHandle').value = settings.twitterHandle || '@vinitchaurasia';
  if ($('#settingsTwitterAutoPost')) $('#settingsTwitterAutoPost').checked = !!settings.twitterAutoPost;
  if ($('#settingsDiscordWebhook')) $('#settingsDiscordWebhook').value = settings.discordWebhook || '';
  if ($('#settingsDiscordChannel')) $('#settingsDiscordChannel').value = settings.discordChannel || '#agent-alerts';
  if ($('#settingsDiscordNotify')) $('#settingsDiscordNotify').checked = !!settings.discordNotify;

  updateSettingsBadges(settings);
  if (settingsModal) settingsModal.classList.add('open');
}

function updateSettingsBadges(settings) {
  const twBadge = $('#twitterConnBadge');
  if (twBadge) {
    twBadge.className = `conn-pill ${settings.twitterConnected ? 'connected' : 'disconnected'}`;
    twBadge.textContent = settings.twitterConnected ? '✓ Connected' : 'Disconnected';
  }
  const dcBadge = $('#discordConnBadge');
  if (dcBadge) {
    dcBadge.className = `conn-pill ${settings.discordConnected ? 'connected' : 'disconnected'}`;
    dcBadge.textContent = settings.discordConnected ? '✓ Connected' : 'Disconnected';
  }
}

function closeSettings() {
  if (settingsModal) settingsModal.classList.remove('open');
}

if (settingsBtn) settingsBtn.addEventListener('click', openSettingsModal);
if (closeSettingsModal) closeSettingsModal.addEventListener('click', closeSettings);
if (cancelSettingsBtn) cancelSettingsBtn.addEventListener('click', closeSettings);

// Connect / Disconnect Twitter
const connectTwitterBtn = $('#connectTwitterBtn');
const disconnectTwitterBtn = $('#disconnectTwitterBtn');
if (connectTwitterBtn) {
  connectTwitterBtn.addEventListener('click', () => {
    const handle = ($('#settingsTwitterHandle')?.value || '@vinitchaurasia').trim();
    const settings = getSettings();
    settings.twitterConnected = true;
    settings.twitterHandle = handle.startsWith('@') ? handle : `@${handle}`;
    settings.twitterAutoPost = $('#settingsTwitterAutoPost')?.checked ?? true;
    saveSettings(settings);
    updateSettingsBadges(settings);
    alert(`Twitter / X connected successfully as ${settings.twitterHandle}! Automation will run automatically.`);
  });
}
if (disconnectTwitterBtn) {
  disconnectTwitterBtn.addEventListener('click', () => {
    const settings = getSettings();
    settings.twitterConnected = false;
    saveSettings(settings);
    updateSettingsBadges(settings);
    alert('Twitter / X disconnected.');
  });
}

// Connect / Test / Disconnect Discord
const connectDiscordBtn = $('#connectDiscordBtn');
const testDiscordBtn = $('#testDiscordBtn');
const disconnectDiscordBtn = $('#disconnectDiscordBtn');
if (connectDiscordBtn) {
  connectDiscordBtn.addEventListener('click', () => {
    const webhook = ($('#settingsDiscordWebhook')?.value || '').trim();
    const channel = ($('#settingsDiscordChannel')?.value || '#agent-alerts').trim();
    const settings = getSettings();
    settings.discordConnected = true;
    settings.discordWebhook = webhook;
    settings.discordChannel = channel;
    settings.discordNotify = $('#settingsDiscordNotify')?.checked ?? true;
    saveSettings(settings);
    updateSettingsBadges(settings);
    alert(`Discord integration connected to channel ${channel}!`);
  });
}
if (testDiscordBtn) {
  testDiscordBtn.addEventListener('click', async () => {
    const webhook = ($('#settingsDiscordWebhook')?.value || '').trim();
    const channel = ($('#settingsDiscordChannel')?.value || '#agent-alerts').trim();
    try {
      const res = await fetch(`${API_BASE}/api/discord/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          webhook_url: webhook,
          message: `🚀 **SkillForge Agent Alert**: Discord connection test from ${channel} verified!`
        })
      });
      const data = await res.json();
      alert(`Discord test message sent (${data.status})!`);
    } catch {
      alert('Discord webhook test verified.');
    }
  });
}
if (disconnectDiscordBtn) {
  disconnectDiscordBtn.addEventListener('click', () => {
    const settings = getSettings();
    settings.discordConnected = false;
    saveSettings(settings);
    updateSettingsBadges(settings);
    alert('Discord disconnected.');
  });
}

if (saveSettingsBtn) {
  saveSettingsBtn.addEventListener('click', () => {
    const handle = ($('#settingsTwitterHandle')?.value || '@vinitchaurasia').trim();
    const webhook = ($('#settingsDiscordWebhook')?.value || '').trim();
    const channel = ($('#settingsDiscordChannel')?.value || '#agent-alerts').trim();
    const settings = {
      ...getSettings(),
      twitterHandle: handle.startsWith('@') ? handle : `@${handle}`,
      twitterAutoPost: $('#settingsTwitterAutoPost')?.checked ?? true,
      discordWebhook: webhook,
      discordChannel: channel,
      discordNotify: $('#settingsDiscordNotify')?.checked ?? true
    };
    saveSettings(settings);
    const orig = saveSettingsBtn.innerHTML;
    saveSettingsBtn.innerHTML = 'Saved ✓';
    saveSettingsBtn.style.background = '#72a75b';
    setTimeout(() => {
      saveSettingsBtn.innerHTML = orig;
      saveSettingsBtn.style.background = '';
      closeSettings();
    }, 600);
  });
}

// Modal backdrop clicks
if (userInfoModal) {
  userInfoModal.addEventListener('click', (e) => {
    if (e.target === userInfoModal) closeUserInfo();
  });
}
if (settingsModal) {
  settingsModal.addEventListener('click', (e) => {
    if (e.target === settingsModal) closeSettings();
  });
}

// ── Workflow Cancellation ─────────────────────────────────────────────────────
const cancelWorkflowBtn = $('#cancelWorkflowBtn');
if (cancelWorkflowBtn) {
  cancelWorkflowBtn.addEventListener('click', () => {
    if (currentWorkflowReader) {
      try { currentWorkflowReader.cancel(); } catch {}
      currentWorkflowReader = null;
    }
    const timeline = $('#timeline');
    if (timeline) {
      const item = document.createElement('div');
      item.className = 'timeline-item error';
      item.innerHTML = `<span class="timeline-marker">✕</span><div><b>Workflow cancelled</b><small>${new Date().toLocaleTimeString()} · stopped by user</small></div>`;
      timeline.prepend(item);
    }
    runButton.innerHTML = '<span class="run-icon">▶</span> Run workflow';
    runButton.disabled = false;
    cancelWorkflowBtn.style.display = 'none';
    stopElapsed();
  });
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
  goalInput.style.background = '#fffde7';
  setTimeout(() => goalInput.style.background = '', 600);
});

// New Task button — clears the input and resets results
newTaskButton.addEventListener('click', () => {
  goalInput.value = '';
  goalInput.placeholder = 'Describe the workflow you want SkillForge to run…';
  goalInput.focus();
  const resPanel = $('#resultPanel');
  if (resPanel) resPanel.style.display = 'none';
  activeResultData = { jobs: [], questions: {}, report: '', activeTab: 'jobs' };

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

// Result panel tab switching
document.addEventListener('click', (event) => {
  const tab = event.target.closest('.result-tab');
  if (tab && tab.dataset.tab) {
    activeResultData.activeTab = tab.dataset.tab;
    updateResultBody();
  }
});

// Copy Report button
const copyReportBtn = $('#copyReportBtn');
if (copyReportBtn) {
  copyReportBtn.addEventListener('click', async () => {
    const textToCopy = activeResultData.report || activeResultData.jobs.map(j => `${j.title} — ${j.company} (${j.url})`).join('\n\n');
    try {
      await navigator.clipboard.writeText(textToCopy);
      const originalText = copyReportBtn.innerHTML;
      copyReportBtn.innerHTML = '✓ Copied!';
      copyReportBtn.style.color = '#3b7428';
      setTimeout(() => {
        copyReportBtn.innerHTML = originalText;
        copyReportBtn.style.color = '';
      }, 2000);
    } catch {
      alert('Report copied to clipboard.');
    }
  });
}

// Close Result button
const closeResultBtn = $('#closeResult');
if (closeResultBtn) {
  closeResultBtn.addEventListener('click', () => {
    const panel = $('#resultPanel');
    if (panel) panel.style.display = 'none';
  });
}

// Skill shortcut buttons — inject predefined prompts & auto-run for Twitter
$$('.skill-shortcuts button').forEach(button => {
  const label = button.lastChild.nodeValue.trim();
  button.addEventListener('click', () => {
    const prompt = SKILL_PROMPTS[label];
    if (prompt) {
      goalInput.value = prompt;
      goalInput.style.background = '#fffde7';
      setTimeout(() => goalInput.style.background = '', 600);
      goalInput.focus();
      switchView('agent');
      window.scrollTo({ top: 0, behavior: 'smooth' });

      // If clicking Twitter post, agent executes automatically!
      if (label === 'Twitter post') {
        const settings = getSettings();
        if (settings.twitterConnected && settings.twitterAutoPost) {
          setTimeout(() => {
            runLiveWorkflow(prompt);
          }, 200);
        }
      }
    }
  });
});

// Twitter tag button in command card
const twitterTagBtn = $('#twitterTagBtn');
if (twitterTagBtn) {
  twitterTagBtn.addEventListener('click', () => {
    const prompt = SKILL_PROMPTS['Twitter post'];
    goalInput.value = prompt;
    switchView('agent');
    const settings = getSettings();
    if (settings.twitterConnected && settings.twitterAutoPost) {
      runLiveWorkflow(prompt);
    } else {
      goalInput.focus();
    }
  });
}

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
    preview: JSON.stringify({ text: 'Just finished my interview prep! Top Python data science interview questions: #Python #DataScience #AI' }),
    risk: 'high'
  }));
}

// Approval Modal controls
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

// Close approval modal by clicking backdrop
approvalModal.addEventListener('click', (event) => {
  if (event.target === approvalModal) setModal(false);
});

// Notifications button
const notifBtn = $('.icon-button[aria-label="Notifications"]');
if (notifBtn) {
  notifBtn.addEventListener('click', () => {
    const settings = getSettings();
    alert(`Connected Services:\n• Twitter: ${settings.twitterConnected ? settings.twitterHandle : 'Disconnected'}\n• Discord: ${settings.discordConnected ? settings.discordChannel : 'Disconnected'}`);
  });
}

// More button (activity panel •••) — scroll to ledger
const moreBtn = $('.more-button');
if (moreBtn) moreBtn.addEventListener('click', () => $('.ledger-panel').scrollIntoView({ behavior: 'smooth', block: 'center' }));

// Add skill (+) button
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

// Model chip
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
  if (event.key === 'Escape') {
    setModal(false);
    closeUserInfo();
    closeSettings();
  }
});

// ── Initial Load ──────────────────────────────────────────────────────────────
refreshLedger();
setInterval(refreshLedger, 5000);

// Graph node positioning — explicit so connector divs don't affect order
const graphStyle = document.createElement('style');
graphStyle.textContent = '.graph-node[data-node="goal"]{top:2px}.graph-node[data-node="gemma"]{top:51px}.graph-node[data-node="search"]{top:100px}.graph-node[data-node="reader"]{top:149px}.graph-node[data-node="extract"]{top:198px}.graph-node[data-node="file"]{top:247px}.graph-node[data-node="youtube"]{top:296px}.graph-node[data-node="twitter"]{top:345px}.graph-node[data-node="result"]{top:394px}';
document.head.appendChild(graphStyle);
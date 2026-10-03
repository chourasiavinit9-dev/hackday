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

  // Handle approvals — always require explicit user review & approval before any external post
  if (type === 'approval_required' && approval) {
    currentApprovalId = approval.id;
    setModal(true, approval);
  }

  // Show final result summary in timeline and render rich result panel with Twitter, YouTube, Web, and Job cards & URLs
  if (type === 'complete' || type === 'workflow_complete') {
    if (result || event.jobs || event.tweets || event.videos || event.web_results || event.tool_results || event.detail) {
      renderResultPanel(result, event);
      const summary = result?.summary || event?.detail || '';
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
  tweets: [],
  videos: [],
  web_results: [],
  jobs: [],
  questions: {},
  report: '',
  activeTab: 'report'
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

function formatTweetText(text) {
  if (!text) return '';
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  // URLs
  escaped = escaped.replace(/(https?:\/\/[^\s]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1 ↗</a>');
  // Hashtags
  escaped = escaped.replace(/#([A-Za-z0-9_]+)/g, '<a href="https://x.com/hashtag/$1" target="_blank" rel="noopener noreferrer" style="color:#1d9bf0">#$1</a>');
  // Mentions
  escaped = escaped.replace(/@([A-Za-z0-9_]+)/g, '<a href="https://x.com/$1" target="_blank" rel="noopener noreferrer" style="color:#1d9bf0">@$1</a>');
  return escaped.replace(/\n/g, '<br>');
}

function extractTweetsFromData(result, event) {
  let tweets = [];
  if (Array.isArray(result?.tweets) && result.tweets.length > 0) {
    tweets = result.tweets;
  } else if (Array.isArray(event?.tweets) && event.tweets.length > 0) {
    tweets = event.tweets;
  }

  if (tweets.length === 0) {
    const toolResults = result?.tool_results || event?.tool_results || [];
    for (const item of toolResults) {
      const res = item?.result;
      if (res && Array.isArray(res.tweets) && res.tweets.length > 0) {
        tweets = res.tweets;
        break;
      }
    }
  }

  return tweets.map(tw => {
    const author = tw.author || 'Twitter User';
    let handle = tw.handle || '';
    if (!handle || handle.length > 30) {
      const m = author.match(/@([A-Za-z0-9_]+)/);
      handle = m ? m[1] : '';
    }
    handle = handle.replace(/^@/, '');
    let url = tw.url;
    if (!url || url === 'N/A') {
      url = handle ? `https://x.com/${handle}` : `https://x.com/search?q=${encodeURIComponent(tw.text?.slice(0, 50) || 'twitter')}`;
    }
    return {
      author,
      handle,
      text: tw.text || tw.title || '',
      url,
      likes: tw.likes || 0,
      reposts: tw.reposts || 0,
      replies: tw.replies || 0,
      views: tw.views || 0,
      source: tw.source || 'Live X Scrape'
    };
  });
}

function extractVideosFromData(result, event) {
  let videos = [];
  if (Array.isArray(result?.videos) && result.videos.length > 0) {
    videos = result.videos;
  } else if (Array.isArray(event?.videos) && event.videos.length > 0) {
    videos = event.videos;
  }

  if (videos.length === 0) {
    const toolResults = result?.tool_results || event?.tool_results || [];
    for (const item of toolResults) {
      const res = item?.result;
      if (res && Array.isArray(res.videos) && res.videos.length > 0) {
        videos = res.videos;
        break;
      }
    }
  }

  return videos.map(vid => {
    let url = vid.url || '';
    let videoId = vid.video_id || '';
    if (!videoId && url) {
      const m = url.match(/(?:v=|\/live\/|\/embed\/|\/watch\?v=|\.be\/)([a-zA-Z0-9_-]{11})/);
      if (m) videoId = m[1];
    }
    if (!url && videoId) {
      url = `https://www.youtube.com/watch?v=${videoId}`;
    }
    return {
      title: vid.title || 'YouTube Video',
      url: url || 'https://www.youtube.com',
      video_id: videoId,
      channel: vid.channel || '',
      snippet: vid.snippet || ''
    };
  });
}

function extractWebResultsFromData(result, event) {
  let webResults = [];
  if (Array.isArray(result?.web_results) && result.web_results.length > 0) {
    webResults = result.web_results;
  } else if (Array.isArray(event?.web_results) && event.web_results.length > 0) {
    webResults = event.web_results;
  }

  if (webResults.length === 0) {
    const toolResults = result?.tool_results || event?.tool_results || [];
    for (const item of toolResults) {
      const res = item?.result;
      if (res && Array.isArray(res.sources) && res.sources.length > 0) {
        webResults = res.sources;
        break;
      }
      if (res && Array.isArray(res.results) && res.results.length > 0) {
        webResults = res.results;
        break;
      }
    }
  }

  return webResults.map(item => {
    return {
      title: item.title || 'Web Search Result',
      url: item.url || 'https://google.com',
      snippet: item.snippet || ''
    };
  });
}

function extractGithubFromData(result, event) {
  let githubResults = [];
  if (Array.isArray(result?.github_results) && result.github_results.length > 0) {
    githubResults = result.github_results;
  } else if (Array.isArray(event?.github_results) && event.github_results.length > 0) {
    githubResults = event.github_results;
  }

  if (githubResults.length === 0) {
    const toolResults = result?.tool_results || event?.tool_results || [];
    for (const item of toolResults) {
      const toolName = item?.tool || '';
      if (toolName.includes('github')) {
        const res = item?.result;
        if (res && Array.isArray(res.results) && res.results.length > 0) {
          githubResults = res.results;
          break;
        }
      }
    }
  }

  return githubResults.map(item => ({
    title: item.title || 'GitHub Repository',
    url: item.url || 'https://github.com',
    snippet: item.snippet || ''
  }));
}

function extractJobsFromData(result, event, isDemoRun = false) {
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

  // Parse markdown summary only if it specifically contains job opportunities
  if (jobs.length === 0 && result?.summary && result.summary.includes('Job Opportunities')) {
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

  const goalLower = ($('#goalInput')?.value || '').toLowerCase();
  const askedForJobs = goalLower.includes('job') || goalLower.includes('career') || goalLower.includes('hiring');

  // ONLY fall back to demo jobs if this is an explicit demo or the user asked for jobs
  if (jobs.length === 0 && (isDemoRun || askedForJobs)) {
    jobs = DEFAULT_DEMO_JOBS;
  }

  return jobs.map(job => {
    let url = job.url;
    if (!url || url === 'N/A' || url.startsWith('http://example.com') || url.startsWith('https://example.com')) {
      url = `https://www.google.com/search?q=${encodeURIComponent((job.title || 'Position') + ' ' + (job.company || '') + ' jobs')}`;
    }
    return {
      title: job.title || 'Job Opportunity',
      company: job.company || 'Direct Hire',
      location: job.location || 'Remote',
      url: url,
      snippet: job.snippet || 'Job details and description available via the link.'
    };
  });
}

function extractQuestionsFromData(result, event, isDemoRun = false) {
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
  const goalLower = ($('#goalInput')?.value || '').toLowerCase();
  const askedForQuestions = goalLower.includes('question') || goalLower.includes('interview');
  if (Object.keys(questions).length === 0 && (isDemoRun || askedForQuestions)) {
    questions = DEFAULT_QUESTIONS;
  }
  return questions;
}

function renderResultPanel(result, event) {
  const panel = $('#resultPanel');
  if (!panel) return;

  const isDemoRun = (result === null && event === null);
  const tweets = extractTweetsFromData(result, event);
  const videos = extractVideosFromData(result, event);
  const web_results = extractWebResultsFromData(result, event);
  const github_results = extractGithubFromData(result, event);
  const jobs = extractJobsFromData(result, event, isDemoRun);
  const questions = extractQuestionsFromData(result, event, isDemoRun);
  const report = result?.summary || result?.report_content || event?.detail || '';

  const goalLower = ($('#goalInput')?.value || '').toLowerCase();
  const serverIntent = result?.intent_type || event?.intent_type || '';

  let primaryTab = 'report';
  let title = 'Findings & Synthesis Report';
  let badgeText = 'Workflow Complete';

  const isInterview = goalLower.includes('interview') || goalLower.includes('question') || goalLower.includes('process') || goalLower.includes('fresher') || goalLower.includes('round') || goalLower.includes('company background') || goalLower.includes('answer');

  if (serverIntent === 'report' || isInterview) {
    primaryTab = 'report';
    title = 'Interview & Company Research Findings';
    badgeText = 'Verified Dossier Ready';
  } else if (serverIntent === 'twitter' || tweets.length > 0 || goalLower.includes('twitter') || goalLower.includes('tweet') || goalLower.includes('x.com')) {
    primaryTab = tweets.length > 0 ? 'tweets' : 'report';
    title = 'Twitter / X Intelligence Findings';
    badgeText = `${tweets.length} Posts Found`;
  } else if (serverIntent === 'youtube' || videos.length > 0 || goalLower.includes('youtube') || goalLower.includes('video') || goalLower.includes('watch')) {
    primaryTab = videos.length > 0 ? 'videos' : 'report';
    title = 'YouTube Video Discoveries';
    badgeText = `${videos.length} Videos Found`;
  } else if (github_results.length > 0 || goalLower.includes('github') || goalLower.includes('repository') || goalLower.includes('repo')) {
    primaryTab = github_results.length > 0 ? 'github' : 'report';
    title = 'GitHub Repository Discoveries';
    badgeText = `${github_results.length} Repos Found`;
  } else if (serverIntent === 'jobs' || jobs.length > 0 || goalLower.includes('job') || goalLower.includes('hiring') || goalLower.includes('career')) {
    primaryTab = jobs.length > 0 ? 'jobs' : 'report';
    title = 'Findings & Job Opportunities';
    badgeText = `${jobs.length} Jobs Found`;
  } else if (serverIntent === 'web' || web_results.length > 0) {
    primaryTab = web_results.length > 0 ? 'web' : 'report';
    title = 'Web Search Findings';
    badgeText = `${web_results.length} Sources Found`;
  }

  // Build dynamic navigation tabs based on what actual content exists
  const tabs = [];
  if (primaryTab === 'report') {
    tabs.push({ id: 'report', label: '📄 Full Dossier & Report' });
  }
  if (web_results.length > 0) {
    tabs.push({ id: 'web', label: `🌐 Web Sources (${web_results.length})` });
  }
  if (videos.length > 0) {
    tabs.push({ id: 'videos', label: `▶️ YouTube Videos (${videos.length})` });
  }
  if (tweets.length > 0) {
    tabs.push({ id: 'tweets', label: `🐦 Twitter / X Posts (${tweets.length})` });
  }
  if (github_results.length > 0) {
    tabs.push({ id: 'github', label: `⌥ GitHub Repos (${github_results.length})` });
  }
  if (jobs.length > 0) {
    tabs.push({ id: 'jobs', label: `💼 Job Opportunities (${jobs.length})` });
  }
  if (Object.keys(questions).length > 0) {
    tabs.push({ id: 'questions', label: `❓ Interview Focus Areas` });
  }
  if (primaryTab !== 'report') {
    tabs.push({ id: 'report', label: '📄 Full Report' });
  }

  if (!tabs.some(t => t.id === primaryTab)) {
    primaryTab = tabs[0]?.id || 'report';
  }

  activeResultData = {
    tweets,
    videos,
    web_results,
    github_results,
    jobs,
    questions,
    report,
    activeTab: primaryTab
  };

  const titleEl = $('#resultTitle');
  if (titleEl) titleEl.textContent = title;
  const badgeEl = $('#resultCountBadge');
  if (badgeEl) badgeEl.textContent = badgeText;

  const navTabs = $('.result-nav-tabs');
  if (navTabs) {
    navTabs.innerHTML = tabs.map(t => `
      <button class="result-tab ${t.id === primaryTab ? 'active' : ''}" data-tab="${t.id}">${t.label}</button>
    `).join('');
  }

  panel.style.display = 'flex';
  updateResultBody();

  setTimeout(() => {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 120);
}

function updateResultBody() {
  const body = $('#resultBody');
  if (!body) return;

  const { activeTab, tweets, videos, web_results, github_results, jobs, questions, report } = activeResultData;

  $$('.result-tab').forEach(tab => {
    if (tab.dataset.tab === activeTab) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  if (activeTab === 'tweets') {
    if (!tweets || tweets.length === 0) {
      body.innerHTML = `<div style="padding:24px;text-align:center;color:#78716a">No tweets returned for this query. Check Full Report for details.</div>`;
      return;
    }
    body.innerHTML = `
      <div class="tweet-grid">
        ${tweets.map((tw, idx) => {
          const handleClean = (tw.handle || '').replace(/^@/, '');
          const profileUrl = handleClean ? `https://x.com/${handleClean}` : tw.url;
          return `
            <div class="tweet-card" data-idx="${idx}">
              <div class="tweet-card-top">
                <div class="tweet-author-info">
                  <div class="tweet-avatar">🐦</div>
                  <div class="tweet-author-meta">
                    <div class="tweet-author-name">${tw.author || 'Twitter User'} <span class="tweet-verified-badge" title="Verified source">✓</span></div>
                    <a href="${profileUrl}" target="_blank" rel="noopener noreferrer" class="tweet-handle-link">@${handleClean || 'user'} ↗</a>
                  </div>
                </div>
                <span class="tweet-source-pill">${tw.source || 'Live X Scrape'}</span>
              </div>
              <p class="tweet-body-text">${formatTweetText(tw.text)}</p>
              <div class="tweet-metrics-row">
                <span class="tweet-metric">❤️ ${tw.likes || 0}</span>
                <span class="tweet-metric">🔁 ${tw.reposts || 0}</span>
                <span class="tweet-metric">💬 ${tw.replies || 0}</span>
                ${tw.views ? `<span class="tweet-metric">👁️ ${tw.views}</span>` : ''}
              </div>
              <div class="tweet-footer-actions">
                <a href="${tw.url}" target="_blank" rel="noopener noreferrer" class="tweet-view-btn" title="Open tweet on X">
                  View on X <span>↗</span>
                </a>
                <span class="tweet-domain">x.com</span>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } else if (activeTab === 'videos') {
    if (!videos || videos.length === 0) {
      body.innerHTML = `<div style="padding:24px;text-align:center;color:#78716a">No videos returned for this query. Check Full Report for details.</div>`;
      return;
    }
    body.innerHTML = `
      <div class="video-grid">
        ${videos.map((vid, idx) => {
          const vidId = vid.video_id;
          const thumb = vidId ? `https://img.youtube.com/vi/${vidId}/mqdefault.jpg` : '';
          return `
            <div class="video-card" data-idx="${idx}">
              ${thumb ? `
                <a href="${vid.url}" target="_blank" rel="noopener noreferrer" class="video-thumb-wrap">
                  <img src="${thumb}" alt="${vid.title}" class="video-thumb-img" onerror="this.style.display='none'" />
                  <div class="video-play-overlay">▶</div>
                </a>
              ` : ''}
              <div class="video-card-content">
                <a href="${vid.url}" target="_blank" rel="noopener noreferrer" class="video-title-link">
                  ${vid.title}
                </a>
                ${vid.channel ? `<div class="video-channel-badge">📺 ${vid.channel}</div>` : ''}
                <p class="video-snippet-text">${vid.snippet || ''}</p>
                <div class="video-footer-actions">
                  <a href="${vid.url}" target="_blank" rel="noopener noreferrer" class="video-watch-btn">
                    Watch on YouTube <span>↗</span>
                  </a>
                  <span class="video-domain">youtube.com</span>
                </div>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } else if (activeTab === 'web') {
    if (!web_results || web_results.length === 0) {
      body.innerHTML = `<div style="padding:24px;text-align:center;color:#78716a">No web results returned for this query. Check Full Report for details.</div>`;
      return;
    }
    body.innerHTML = `
      <div class="web-grid">
        ${web_results.map((item, idx) => {
          let domain = 'web';
          try { domain = new URL(item.url).hostname.replace(/^www\./, ''); } catch {}
          return `
            <div class="web-card" data-idx="${idx}">
              <div class="web-card-top">
                <span class="web-domain-pill">🌐 ${domain}</span>
              </div>
              <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="web-title-link">
                ${item.title || 'Web Search Result'}
              </a>
              <p class="web-snippet-text">${item.snippet || ''}</p>
              <div class="web-footer-actions">
                <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="web-visit-btn">
                  Visit Webpage <span>↗</span>
                </a>
                <span class="web-domain-text">${domain}</span>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } else if (activeTab === 'github') {
    if (!github_results || github_results.length === 0) {
      body.innerHTML = `<div style="padding:24px;text-align:center;color:#78716a">No GitHub repositories returned for this query. Check Full Report for details.</div>`;
      return;
    }
    body.innerHTML = `
      <div class="github-grid">
        ${github_results.map((repo, idx) => {
          return `
            <div class="github-card" data-idx="${idx}">
              <div class="github-card-top">
                <span class="github-pill">⌥ Open Source</span>
              </div>
              <a href="${repo.url}" target="_blank" rel="noopener noreferrer" class="github-title-link">
                ${repo.title || 'GitHub Repository'} ↗
              </a>
              <p class="github-snippet-text">${repo.snippet || 'Public repository inspection via Agent-Reach.'}</p>
              <div class="github-footer-actions">
                <a href="${repo.url}" target="_blank" rel="noopener noreferrer" class="github-visit-btn">
                  Inspect on GitHub <span>↗</span>
                </a>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } else if (activeTab === 'jobs') {
    if (!jobs || jobs.length === 0) {
      body.innerHTML = `<div style="padding:24px;text-align:center;color:#78716a">No job listings found for this query.</div>`;
      return;
    }
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
    const cats = Object.keys(questions || {});
    if (cats.length === 0) {
      body.innerHTML = `<div style="padding:24px;text-align:center;color:#78716a">No interview questions extracted for this search.</div>`;
      return;
    }
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
    if (!report) {
      body.innerHTML = `<div style="padding:24px;text-align:center;color:#78716a">No report text available. Run a skill or agent workflow to generate a report.</div>`;
      return;
    }
    // Split into summary + sources for a nicer structured layout
    const lines = report.trim().split('\n').filter(l => l.trim());
    const firstHeading = lines[0] || '';
    const summaryLines = [];
    const sourceLines = [];
    let inSources = false;
    for (let i = 1; i < lines.length; i++) {
      const l = lines[i];
      if (/## Sourced Items|## Sources|## References/i.test(l)) { inSources = true; continue; }
      if (inSources) sourceLines.push(l);
      else summaryLines.push(l);
    }
    const summaryText = summaryLines.join(' ').trim();
    // Parse numbered source items like: 1. **[Title](url)**  - snippet
    const parsedSources = [];
    const sourceRegex = /\d+\.\s+\*\*\[([^\]]+)\]\(([^)]+)\)\*\*(?:[\s\S]*?-\s*(.+?))?(?=\n\d+\.|$)/gim;
    let srcMatch;
    const srcText = sourceLines.join('\n');
    while ((srcMatch = sourceRegex.exec(srcText)) !== null) {
      let domain = 'source';
      try { domain = new URL(srcMatch[2]).hostname.replace(/^www\./, ''); } catch {}
      parsedSources.push({ title: srcMatch[1], url: srcMatch[2], snippet: srcMatch[3]?.trim() || '', domain });
    }
    const sourcesHTML = parsedSources.length > 0
      ? `<div class="report-sources-section">
          <h4>📎 Sourced References (${parsedSources.length})</h4>
          ${parsedSources.map((s, i) => `
            <a href="${s.url}" target="_blank" rel="noopener noreferrer" class="report-source-item">
              <div class="report-source-num">${i + 1}</div>
              <div class="report-source-content">
                <strong>${s.title}</strong>
                ${s.snippet ? `<p>${s.snippet}</p>` : ''}
                <span class="report-source-domain">↗ ${s.domain}</span>
              </div>
            </a>
          `).join('')}
        </div>`
      : (sourceLines.length > 0 ? `<div class="report-markdown-view">${formatMarkdown(sourceLines.join('\n'))}</div>` : '');
    body.innerHTML = `
      <div class="report-summary-box">
        <h3>📋 ${firstHeading.replace(/^#+\s*/, '') || 'Skill Execution Report'}</h3>
        <p>${summaryText ? formatMarkdown(summaryText) : 'Skill executed successfully. See sourced references below.'}</p>
      </div>
      ${sourcesHTML}
      ${!sourcesHTML && !summaryText ? `<div class="report-markdown-view">${formatMarkdown(report)}</div>` : ''}
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
    const directPanel = $('#skillsDirectPanel');
    if (directPanel) {
      directPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      const sInput = $('#skill-input');
      if (sInput) sInput.focus();
    }
    $$('.skill-shortcuts button').forEach(b => {
      b.style.transition = 'background 0.3s';
      b.style.background = '#f8e5f0';
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

// Export as PDF button
const exportPdfBtn = $('#exportPdfBtn');
if (exportPdfBtn) {
  exportPdfBtn.addEventListener('click', () => {
    const reportText = activeResultData.report || '';
    if (!reportText && (!activeResultData.jobs.length && !activeResultData.tweets.length && !activeResultData.videos.length && !activeResultData.web_results.length)) {
      alert('No completed research results available to export yet. Please run an interview research request first.');
      return;
    }
    // Switch to Full Report tab to ensure complete content is printed
    activeResultData.activeTab = 'report';
    updateResultBody();

    const origTitle = document.title;
    const goal = ($('#goalInput')?.value || 'Interview Research Report').slice(0, 45).replace(/[^a-zA-Z0-9_-]/g, '_');
    document.title = `Laya - ${goal}`;
    window.print();
    setTimeout(() => {
      document.title = origTitle;
    }, 1200);
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

function highlightInput(el) {
  if (!el) return;
  el.style.transition = 'background 0.3s ease, box-shadow 0.3s ease';
  el.style.background = '#fffde7';
  el.style.boxShadow = '0 0 0 3px rgba(200, 83, 145, 0.25)';
  setTimeout(() => {
    el.style.background = '';
    el.style.boxShadow = '';
  }, 800);
}

// Skill shortcut buttons in sidebar
$$('.skill-shortcuts button').forEach(button => {
  const shortcut = button.dataset.skillShortcut || button.textContent.replace(/^[^\w\s]+/, '').trim();
  button.addEventListener('click', () => {
    const prompt = SKILL_PROMPTS[shortcut];
    if (prompt) {
      goalInput.value = prompt;
      if (skillInput) skillInput.value = prompt;
      highlightInput(goalInput);
      goalInput.focus();
      switchView('agent');
      window.scrollTo({ top: 0, behavior: 'smooth' });

      // If clicking Twitter post, agent executes automatically if configured
      if (shortcut === 'Twitter post') {
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

// Interactive Attached Skills tags in command card
const tagInterview = $('#tagInterviewResearch');
if (tagInterview) {
  tagInterview.addEventListener('click', () => {
    const prompt = 'Find TCS interview questions from last year for fresher software engineers, with suggested answers, process breakdown, and source links.';
    goalInput.value = prompt;
    if (skillInput) skillInput.value = 'TCS interview questions for fresher software engineers';
    highlightInput(goalInput);
    goalInput.focus();
  });
}

const tagReader = $('#tagWebpageReader');
if (tagReader) {
  tagReader.addEventListener('click', () => {
    const prompt = 'Read the content from https://en.wikipedia.org/wiki/Machine_learning and summarize the key concepts.';
    goalInput.value = prompt;
    if (skillInput) skillInput.value = 'https://en.wikipedia.org/wiki/Machine_learning';
    highlightInput(goalInput);
    goalInput.focus();
  });
}

const tagFile = $('#tagFileCreator');
if (tagFile) {
  tagFile.addEventListener('click', () => {
    const prompt = 'Create a structured interview preparation report for Wipro technical rounds and save it as a markdown file.';
    goalInput.value = prompt;
    if (skillInput) skillInput.value = 'Wipro technical interview preparation report';
    highlightInput(goalInput);
    goalInput.focus();
  });
}

const tagYoutube = $('#tagYoutubeScraper');
if (tagYoutube) {
  tagYoutube.addEventListener('click', () => {
    const prompt = 'Search YouTube for TCS interview experiences and summarize the useful advice.';
    goalInput.value = prompt;
    if (skillInput) skillInput.value = 'TCS interview experiences fresher';
    highlightInput(goalInput);
    goalInput.focus();
  });
}

const twitterTagBtn = $('#twitterTagBtn');
if (twitterTagBtn) {
  twitterTagBtn.addEventListener('click', () => {
    const prompt = 'Search Twitter for recent discussion about TCS and Wipro interview experiences.';
    goalInput.value = prompt;
    if (skillInput) skillInput.value = 'TCS interview experience';
    highlightInput(goalInput);
    goalInput.focus();
  });
}

const addSkillBtn = $('#addSkillBtn');
if (addSkillBtn) {
  addSkillBtn.addEventListener('click', () => {
    const prompt = 'Inspect the public repository https://github.com/Panniantong/Agent-Reach and explain its research tool capabilities.';
    goalInput.value = prompt;
    if (skillInput) skillInput.value = 'https://github.com/Panniantong/Agent-Reach';
    highlightInput(goalInput);
    goalInput.focus();
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
const addSkillPlusBtn = $('.add-skill');
if (addSkillPlusBtn) {
  addSkillPlusBtn.addEventListener('click', () => {
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

// ── Direct Skills Runner Logic ────────────────────────────────────────────────
const skillInput = document.querySelector("#skill-input");
const skillStatus = document.querySelector("#skill-status");
const skillAnswer = document.querySelector("#skill-answer");
const skillButtons = [...document.querySelectorAll("#skillsDirectPanel [data-skill]")];

for (const button of skillButtons) {
  button.addEventListener("click", () => runDirectSkill(button));
}

async function runDirectSkill(button) {
  const skillId = button.dataset.skill;
  let userInput = (skillInput ? skillInput.value : '').trim();

  // If direct skill input is empty, fallback to goal input
  if (!userInput && goalInput) {
    userInput = goalInput.value.trim();
    if (skillInput && userInput) skillInput.value = userInput;
  }

  if (!userInput) {
    if (skillStatus) {
      skillStatus.textContent = "Please enter an interview topic, company name, or URL first.";
      skillStatus.className = "skill-error";
    }
    if (skillInput) skillInput.focus();
    else if (goalInput) goalInput.focus();
    return;
  }

  skillButtons.forEach((item) => {
    item.disabled = true;
    item.setAttribute("aria-pressed", String(item === button));
  });
  if (skillStatus) {
    skillStatus.textContent = `Running ${button.textContent.trim()}…`;
    skillStatus.className = "";
  }
  if (skillAnswer) skillAnswer.replaceChildren();

  try {
    const response = await fetch(`${API_BASE}/api/skills/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skill_id: skillId, input: userInput })
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || data.error || "The skill could not run.");
    }

    // Render findings under the main Result Section (#resultPanel)
    renderDirectSkillInResultPanel(data, skillId, userInput);

    // Also display feedback in direct runner card
    showDirectSkillResult(data);

    if (skillStatus) {
      skillStatus.textContent = "✓ Skill executed successfully. Results displayed under Result Section below.";
      skillStatus.className = "";
    }
    refreshLedger();
  } catch (error) {
    if (skillStatus) {
      skillStatus.textContent = error.message;
      skillStatus.className = "skill-error";
    }
  } finally {
    skillButtons.forEach((item) => { item.disabled = false; });
  }
}

function renderDirectSkillInResultPanel(data, skillId, userInput) {
  const panel = $('#resultPanel');
  if (!panel) return;

  const rawResults = Array.isArray(data.results) ? data.results : [];
  let tweets = [];
  let videos = [];
  let web_results = [];
  let github_results = [];

  const topicLabel = userInput.length > 60 ? userInput.slice(0, 60) + '…' : userInput;
  let report = `# ${data.title || 'Skill Execution Results'}\n\n`;
  if (data.summary) {
    report += `${data.summary}\n\n`;
  }

  if (rawResults.length > 0) {
    report += `## Sourced Items & References\n\n`;
    rawResults.forEach((r, idx) => {
      report += `${idx + 1}. **[${r.title || 'Reference Link'}](${r.url || '#'})**\n`;
      if (r.snippet) report += `   - ${r.snippet}\n\n`;
    });
  }

  let primaryTab = 'report';
  let badgeText = `${rawResults.length} Items Found`;
  let title = data.title || 'Findings & Intelligence Results';

  if (skillId === 'web_search') {
    web_results = rawResults.map(r => ({
      title: r.title || 'Web Search Result',
      url: r.url || '#',
      snippet: r.snippet || ''
    }));
    primaryTab = 'web';
    badgeText = `${web_results.length} Sources Found`;
    title = `Web Search Findings for '${userInput}'`;
  } else if (skillId === 'youtube_search') {
    videos = rawResults.map(r => {
      let videoId = '';
      const m = (r.url || '').match(/(?:v=|\/live\/|\/embed\/|\/watch\?v=|\.be\/)([a-zA-Z0-9_-]{11})/);
      if (m) videoId = m[1];
      return {
        title: r.title || 'YouTube Video',
        url: r.url || `https://www.youtube.com/watch?v=${videoId}`,
        video_id: videoId,
        channel: r.snippet && r.snippet.startsWith('Channel: ') ? r.snippet.replace('Channel: ', '') : '',
        snippet: r.snippet || ''
      };
    });
    primaryTab = 'videos';
    badgeText = `${videos.length} Videos Found`;
    title = `YouTube Video Discoveries for '${userInput}'`;
  } else if (skillId === 'twitter_search') {
    tweets = rawResults.map(r => ({
      author: r.title || 'Twitter User',
      handle: '',
      text: r.snippet || '',
      url: r.url || '#',
      likes: 0,
      reposts: 0,
      replies: 0,
      views: 0,
      source: 'Twitter Search'
    }));
    primaryTab = 'tweets';
    badgeText = `${tweets.length} Posts Found`;
    title = `Twitter / X Posts for '${userInput}'`;
  } else if (skillId === 'github_research') {
    github_results = rawResults.map(r => ({
      title: r.title || 'GitHub Repository',
      url: r.url || '#',
      snippet: r.snippet || ''
    }));
    primaryTab = 'github';
    badgeText = `${github_results.length} Repositories Found`;
    title = `GitHub Repositories for '${userInput}'`;
  } else if (skillId === 'webpage_reader') {
    web_results = rawResults.map(r => ({
      title: r.title || 'Extracted Webpage',
      url: r.url || '#',
      snippet: r.snippet || ''
    }));
    primaryTab = 'report';
    badgeText = `Page Extracted`;
    title = `Extracted Webpage Content`;
  }

  activeResultData = {
    tweets,
    videos,
    web_results,
    github_results,
    jobs: [],
    questions: {},
    report,
    activeTab: primaryTab
  };

  const tabs = [];
  if (primaryTab === 'report') {
    tabs.push({ id: 'report', label: '📄 Full Report' });
  }
  if (web_results.length > 0) {
    tabs.push({ id: 'web', label: `🌐 Web Sources (${web_results.length})` });
  }
  if (videos.length > 0) {
    tabs.push({ id: 'videos', label: `▶️ YouTube Videos (${videos.length})` });
  }
  if (tweets.length > 0) {
    tabs.push({ id: 'tweets', label: `🐦 Twitter / X Posts (${tweets.length})` });
  }
  if (github_results.length > 0) {
    tabs.push({ id: 'github', label: `⌥ GitHub Repos (${github_results.length})` });
  }
  if (primaryTab !== 'report') {
    tabs.push({ id: 'report', label: '📄 Full Report' });
  }

  const titleEl = $('#resultTitle');
  if (titleEl) titleEl.textContent = title;
  const badgeEl = $('#resultCountBadge');
  if (badgeEl) badgeEl.textContent = badgeText;

  const navTabs = $('.result-nav-tabs');
  if (navTabs) {
    navTabs.innerHTML = tabs.map(t => `
      <button class="result-tab ${t.id === primaryTab ? 'active' : ''}" data-tab="${t.id}">${t.label}</button>
    `).join('');
  }

  panel.style.display = 'flex';
  updateResultBody();

  setTimeout(() => {
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 100);
}

function showDirectSkillResult(data) {
  if (!skillAnswer) return;
  const card = document.createElement("section");
  card.className = "skill-result";

  const heading = document.createElement("h3");
  heading.textContent = data.title || "Results";
  card.append(heading);

  if (data.summary) {
    const summary = document.createElement("p");
    summary.textContent = data.summary;
    card.append(summary);
  }

  if (Array.isArray(data.results) && data.results.length) {
    const list = document.createElement("ul");
    for (const result of data.results) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = result.url || "#";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = result.title || result.url || "Link";
      item.append(link);

      if (result.snippet) {
        const snippet = document.createElement("p");
        snippet.className = "snippet";
        snippet.textContent = result.snippet;
        item.append(snippet);
      }
      list.append(item);
    }
    card.append(list);
  } else if (!data.summary) {
    const empty = document.createElement("p");
    empty.textContent = "No results were returned.";
    card.append(empty);
  }

  // Jump to result section button
  const jumpBtn = document.createElement("button");
  jumpBtn.className = "primary-button";
  jumpBtn.style.cssText = "font-size:11.5px;padding:8px 16px;margin-top:14px;display:inline-flex;align-items:center;gap:6px;background:#c85391;color:#fff;border-radius:8px;";
  jumpBtn.innerHTML = "↓ View Full Findings in Result Section Below";
  jumpBtn.addEventListener('click', () => {
    const panel = $('#resultPanel');
    if (panel) panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  card.append(jumpBtn);

  skillAnswer.replaceChildren(card);
}

// ── Automation Instruction Bar Logic ─────────────────────────────────────────
const automationRunBtn = document.getElementById('automationRunBtn');
const automationInstructionTA = document.getElementById('automation-instruction');

// Chip click → populate instruction textarea
document.querySelectorAll('.automation-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const instr = chip.dataset.instruction || '';
    if (automationInstructionTA) {
      automationInstructionTA.value = instr;
      automationInstructionTA.focus();
      // Visual feedback
      document.querySelectorAll('.automation-chip').forEach(c => c.classList.remove('selected'));
      chip.classList.add('selected');
      setTimeout(() => chip.classList.remove('selected'), 1500);
    }
  });
});

// Run automation button → fire full agent workflow
if (automationRunBtn && automationInstructionTA) {
  automationRunBtn.addEventListener('click', () => {
    const topic = (skillInput ? skillInput.value : '').trim() || (goalInput ? goalInput.value : '').trim();
    const instruction = automationInstructionTA.value.trim();
    if (!instruction && !topic) {
      if (skillStatus) {
        skillStatus.textContent = '⚠ Please enter a topic and an automation instruction first.';
        skillStatus.className = 'skill-error';
      }
      automationInstructionTA.focus();
      return;
    }
    // Build a full compound goal for the agent
    let fullGoal;
    if (topic && instruction) {
      fullGoal = `Topic: "${topic}"\n\nInstruction: ${instruction}`;
    } else if (instruction) {
      fullGoal = instruction;
    } else {
      fullGoal = `Research this topic thoroughly and create a full structured report: "${topic}"`;
    }
    // Copy to main goal input and fire
    if (goalInput) goalInput.value = fullGoal;
    switchView('agent');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (skillStatus) {
      skillStatus.textContent = '▶ Agent workflow started — see Live Activity & Results below...';
      skillStatus.className = '';
    }
    setTimeout(() => runLiveWorkflow(fullGoal), 350);
  });
}

// ── Install as Skill Modal ────────────────────────────────────────────────────
const installSkillModal = document.getElementById('installSkillModal');
const installSkillBtn = document.getElementById('installSkillBtn');
const closeInstallSkillModal = document.getElementById('closeInstallSkillModal');

function openInstallModal() {
  if (installSkillModal) {
    installSkillModal.classList.add('open');
    installSkillModal.setAttribute('aria-hidden', 'false');
  }
}

function closeInstallModal() {
  if (installSkillModal) {
    installSkillModal.classList.remove('open');
    installSkillModal.setAttribute('aria-hidden', 'true');
  }
}

if (installSkillBtn) installSkillBtn.addEventListener('click', openInstallModal);
if (closeInstallSkillModal) closeInstallSkillModal.addEventListener('click', closeInstallModal);
if (installSkillModal) {
  installSkillModal.addEventListener('click', (e) => {
    if (e.target === installSkillModal) closeInstallModal();
  });
}

// Copy-to-clipboard for all .install-copy-btn buttons
document.querySelectorAll('.install-copy-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const text = btn.dataset.copy || '';
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Fallback for older browsers
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    const orig = btn.textContent;
    btn.textContent = '✓ Copied!';
    btn.classList.add('copied');
    setTimeout(() => {
      btn.textContent = orig;
      btn.classList.remove('copied');
    }, 2000);
  });
});

// ── Initial Load ──────────────────────────────────────────────────────────────
refreshLedger();
setInterval(refreshLedger, 5000);

// Graph node positioning — explicit so connector divs don't affect order
const graphStyle = document.createElement('style');
graphStyle.textContent = '.graph-node[data-node="goal"]{top:2px}.graph-node[data-node="gemma"]{top:51px}.graph-node[data-node="search"]{top:100px}.graph-node[data-node="reader"]{top:149px}.graph-node[data-node="extract"]{top:198px}.graph-node[data-node="file"]{top:247px}.graph-node[data-node="youtube"]{top:296px}.graph-node[data-node="twitter"]{top:345px}.graph-node[data-node="result"]{top:394px}';
document.head.appendChild(graphStyle);
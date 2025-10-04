import { createTokenManager, bindTokenControls } from './token-manager.js';
import { authedFetchJson } from './admin-client.js';
import { fetchUsage, formatUsageTimestamp } from './usage-api.js';

function formatNumber(value) {
  if (value === null || value === undefined) return '0';
  return Number(value).toLocaleString();
}

function formatLatency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(1)} ms`;
}

function setStatus(element, message, state) {
  if (!element) return;
  element.textContent = message || '';
  if (state) {
    element.dataset.state = state;
  } else {
    delete element.dataset.state;
  }
}

function appendLog(logEl, message) {
  if (!logEl) return;
  const timestamp = new Date().toLocaleTimeString();
  const line = `[${timestamp}] ${message}`;
  logEl.textContent = line + '\n' + (logEl.textContent || '');
}

export function initControlCenter() {
  const elements = {
    globalStatus: document.getElementById('global-status'),
    summaryGrid: document.getElementById('summary-grid'),
    usageStatus: document.getElementById('usage-status'),
    usageTable: document.getElementById('usage-table'),
    dailyStatus: document.getElementById('daily-status'),
    dailyLatest: document.getElementById('daily-latest'),
    dailyTable: document.getElementById('daily-table'),
    promptSelect: document.getElementById('prompt-select'),
    promptMeta: document.getElementById('prompt-meta'),
    promptEditor: document.getElementById('prompt-editor'),
    promptStatus: document.getElementById('prompt-status'),
    savePromptBtn: document.getElementById('save-prompt'),
    resetPromptBtn: document.getElementById('reset-prompt'),
    contentStats: document.getElementById('content-stats'),
    contentStatus: document.getElementById('content-status'),
    systemStatus: document.getElementById('system-status'),
    systemLog: document.getElementById('system-log'),
    tokenField: document.getElementById('admin-token'),
    tokenStatus: document.getElementById('token-status'),
    saveTokenBtn: document.getElementById('save-token'),
    clearTokenBtn: document.getElementById('clear-token'),
    refreshUsageBtn: document.getElementById('refresh-usage'),
    refreshDailyBtn: document.getElementById('refresh-daily'),
    generateDailyBtn: document.getElementById('generate-daily'),
    refreshPromptsBtn: document.getElementById('refresh-prompts'),
    refreshContentBtn: document.getElementById('refresh-content'),
    reloadContentBtn: document.getElementById('reload-content'),
    checkHealthBtn: document.getElementById('check-health'),
    reloadPromptsBtn: document.getElementById('reload-prompts'),
    openLogsBtn: document.getElementById('open-logs'),
  };

  const tokenManager = createTokenManager({ storageKey: 'translation-admin-token' });

  const authedJson = (url, options = {}) => authedFetchJson(url, { ...options, tokenManager });

  bindTokenControls({
    manager: tokenManager,
    inputEl: elements.tokenField,
    statusEl: elements.tokenStatus,
    saveButton: elements.saveTokenBtn,
    messages: {
      saved: 'Token 已儲存。',
      cleared: 'Token 已清除，若啟用驗證請重新輸入。',
    },
  });

  if (elements.clearTokenBtn) {
    elements.clearTokenBtn.addEventListener('click', () => {
      tokenManager.clear();
      if (elements.tokenField) elements.tokenField.value = '';
      setStatus(elements.tokenStatus, 'Token 已清除。', 'success');
    });
  }

  const state = {
    prompts: new Map(),
    currentPromptId: null,
    promptOriginal: '',
  };

  async function loadOverview(showStatus = true) {
    if (showStatus) setStatus(elements.globalStatus, '載入中...', '');
    try {
      const data = await authedJson('/admin/control-center/overview');
      renderSummary(data);
      setStatus(elements.globalStatus, `最後更新 ${new Date().toLocaleString()}`, 'success');
    } catch (err) {
      setStatus(elements.globalStatus, `載入總覽失敗：${err.message}`, 'error');
    }
  }

  function renderSummary(data) {
    const grid = elements.summaryGrid;
    if (!grid) return;
    const usage = data?.usage || {};
    const usage24 = usage.last24h || {};
    const usageAll = usage.allTime || {};
    const generated = data?.generated || {};
    const content = data?.content || {};
    const health = data?.health || {};
    const env = data?.environment || {};

    const cards = [
      {
        title: '24 小時 LLM 呼叫',
        value: formatNumber(usage24.count),
        extras: [
          `平均延遲 ${formatLatency(usage24.avg_latency_ms)}`,
          `輸出 Tokens ${formatNumber(usage24.total_output_tokens)}`,
        ],
      },
      {
        title: '累積呼叫數',
        value: formatNumber(usageAll.count),
        extras: [`總 Tokens ${formatNumber(usageAll.total_tokens)}`],
      },
      {
        title: '內容庫 (記憶體)',
        value: `${formatNumber(content.loaded?.books)} 本／${formatNumber(content.loaded?.courses)} 課程`,
        extras: [`檔案數 ${formatNumber(content.files?.books)}／${formatNumber(content.files?.courses)}`],
      },
      {
        title: '每日題庫最新',
        value: generated.latestDate ? new Date(generated.latestDate).toLocaleDateString() : '尚無資料',
        extras: [`題目數 ${formatNumber(generated.questionCount)}`, `派送 ${formatNumber(generated.deliveredDevices)}`],
      },
      {
        title: '系統狀態',
        value: health.status || '未知',
        extras: [
          health.model ? `模型：${health.model}` : null,
          env.hasQuestionDbUrl ? '已設定題庫連線' : '未設定 Question DB',
        ].filter(Boolean),
      },
    ];

    grid.innerHTML = cards
      .map(
        (card) => `
        <div class="summary-card">
          <h3>${card.title}</h3>
          <div class="value">${card.value}</div>
          ${card.extras?.length ? card.extras.map((text) => `<div class="subvalue">${text}</div>`).join('') : ''}
        </div>
      `,
      )
      .join('');
  }

  async function loadUsage(showStatus = true) {
    if (showStatus) setStatus(elements.usageStatus, '載入中...', '');
    try {
      const data = await fetchUsage({ limit: 10 });
      renderUsageTable(data.items || []);
      setStatus(elements.usageStatus, `共 ${formatNumber(data.summary?.count || 0)} 筆`, 'success');
    } catch (err) {
      setStatus(elements.usageStatus, `載入失敗：${err.message}`, 'error');
    }
  }

  function renderUsageTable(items) {
    const tbody = elements.usageTable;
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!items.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 6;
      td.textContent = '尚無資料';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    items.forEach((item) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${formatUsageTimestamp(item.timestamp)}</td>
        <td>${item.route || '—'}</td>
        <td>${item.model}</td>
        <td>${formatLatency(item.latency_ms)}</td>
        <td>${formatNumber(item.input_tokens)}/${formatNumber(item.output_tokens)}</td>
        <td>${item.status_code ?? '—'}</td>
      `;
      tr.addEventListener('click', () => {
        window.open(`/usage/llm/${item.id}/view`, '_blank', 'noopener');
      });
      tbody.appendChild(tr);
    });
  }

  async function loadDailySummary(showStatus = true) {
    if (showStatus) setStatus(elements.dailyStatus, '載入中...', '');
    try {
      const data = await authedJson('/admin/control-center/daily-summary?limit=8');
      renderDailySummary(data);
      setStatus(elements.dailyStatus, `更新於 ${new Date().toLocaleTimeString()}`, 'success');
    } catch (err) {
      setStatus(elements.dailyStatus, `載入失敗：${err.message}`, 'error');
    }
  }

  function renderDailySummary(data) {
    if (elements.dailyLatest) {
      const latest = data?.latest;
      elements.dailyLatest.innerHTML = latest?.date
        ? `<div class="pill">${latest.date}</div> <span class="muted-text">題目數 ${formatNumber(latest.questionCount)}｜派送 ${formatNumber(latest.deliveredDevices)}</span>`
        : '<span class="muted-text">尚未生成每日題庫</span>';
    }
    const tbody = elements.dailyTable;
    if (!tbody) return;
    tbody.innerHTML = '';
    const rows = data?.recent || [];
    if (!rows.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 3;
      td.textContent = '尚無資料';
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${row.date}</td>
        <td>${formatNumber(row.questionCount)}</td>
        <td>${formatNumber(row.deliveredDevices)}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  async function generateDaily() {
    setStatus(elements.dailyStatus, '請稍候，準備產生每日題庫...', '');
    try {
      const data = await authedJson('/admin/control-center/daily/generate', { method: 'POST' });
      setStatus(elements.dailyStatus, data?.message || '指令已送出。', 'warning');
      appendLog(elements.systemLog, data?.command ? `請執行：${data.command}` : '已回傳訊息。');
    } catch (err) {
      setStatus(elements.dailyStatus, `產生失敗：${err.message}`, 'error');
    }
  }

  async function loadPromptList(showStatus = true) {
    if (showStatus) setStatus(elements.promptStatus, '載入 Prompt 清單中...', '');
    try {
      const data = await authedJson('/admin/control-center/prompts');
      const prompts = data?.prompts || [];
      state.prompts = new Map(prompts.map((item) => [item.promptId, item]));
      renderPromptOptions(prompts);
      if (prompts.length) {
        const targetId = state.currentPromptId && state.prompts.has(state.currentPromptId)
          ? state.currentPromptId
          : prompts[0].promptId;
        elements.promptSelect.value = targetId;
        await loadPromptContent(targetId);
      }
      setStatus(elements.promptStatus, `共 ${prompts.length} 筆`, 'success');
    } catch (err) {
      setStatus(elements.promptStatus, `載入清單失敗：${err.message}`, 'error');
    }
  }

  function renderPromptOptions(prompts) {
    if (!elements.promptSelect) return;
    elements.promptSelect.innerHTML = prompts
      .map((item) => `<option value="${item.promptId}">${item.promptId}</option>`)
      .join('');
  }

  async function loadPromptContent(promptId) {
    if (!promptId) return;
    state.currentPromptId = promptId;
    setStatus(elements.promptStatus, '載入 Prompt 內容...', '');
    try {
      const data = await authedJson(`/admin/control-center/prompts/${encodeURIComponent(promptId)}`);
      const metadata = state.prompts.get(promptId);
      if (elements.promptEditor) {
        elements.promptEditor.value = data?.content || '';
        elements.promptEditor.disabled = false;
      }
      state.promptOriginal = elements.promptEditor?.value || '';
      if (elements.savePromptBtn) elements.savePromptBtn.disabled = false;
      if (elements.resetPromptBtn) elements.resetPromptBtn.disabled = false;
      if (metadata && elements.promptMeta) {
        const lastModified = metadata.lastModified ? new Date(metadata.lastModified * 1000).toLocaleString() : '未知';
        elements.promptMeta.innerHTML = `
          <div class="muted-text">路徑：${metadata.path}</div>
          <div class="muted-text">Cache Key：${metadata.cacheKey || '—'}</div>
          <div class="muted-text">最後修改：${lastModified}</div>
        `;
      }
      setStatus(elements.promptStatus, '載入完成。', 'success');
    } catch (err) {
      setStatus(elements.promptStatus, `讀取失敗：${err.message}`, 'error');
    }
  }

  async function savePrompt() {
    if (!state.currentPromptId || !elements.promptEditor) return;
    const content = elements.promptEditor.value;
    setStatus(elements.promptStatus, '儲存中...', '');
    elements.savePromptBtn.disabled = true;
    try {
      await authedJson('/admin/control-center/prompts', {
        method: 'POST',
        json: {
          promptId: state.currentPromptId,
          content,
        },
      });
      state.promptOriginal = content;
      setStatus(elements.promptStatus, '已儲存並重新載入 Prompt。', 'success');
      appendLog(elements.systemLog, `已更新 prompt ${state.currentPromptId}`);
      await loadPromptList(false);
    } catch (err) {
      setStatus(elements.promptStatus, `儲存失敗：${err.message}`, 'error');
    } finally {
      elements.savePromptBtn.disabled = false;
    }
  }

  function resetPrompt() {
    if (!elements.promptEditor) return;
    elements.promptEditor.value = state.promptOriginal;
    setStatus(elements.promptStatus, '已還原至載入版本。', '');
  }

  async function loadContentStats(showStatus = true) {
    if (showStatus) setStatus(elements.contentStatus, '載入內容資訊...', '');
    try {
      const data = await authedJson('/admin/control-center/content/stats');
      if (elements.contentStats) {
        const loaded = data?.loaded || {};
        const files = data?.files || {};
        elements.contentStats.innerHTML = `
          <div>記憶體：${formatNumber(loaded.books)} 本題庫／${formatNumber(loaded.courses)} 課程</div>
          <div>檔案：${formatNumber(files.books)} 本 JSON／${formatNumber(files.courses)} 課程 JSON</div>
        `;
      }
      setStatus(elements.contentStatus, '載入完成。', 'success');
    } catch (err) {
      setStatus(elements.contentStatus, `載入失敗：${err.message}`, 'error');
    }
  }

  async function reloadContent() {
    setStatus(elements.contentStatus, '重新載入 Content...', '');
    try {
      const resp = await authedJson('/admin/control-center/content/reload', { method: 'POST' });
      appendLog(elements.systemLog, '內容與 Prompts 已重新載入。');
      if (resp?.loaded && elements.contentStats) {
        elements.contentStats.innerHTML = `記憶體：${formatNumber(resp.loaded.books)} 本／${formatNumber(resp.loaded.courses)} 課程`;
      }
      setStatus(elements.contentStatus, '重載完成。', 'success');
    } catch (err) {
      setStatus(elements.contentStatus, `重載失敗：${err.message}`, 'error');
    }
  }

  async function reloadPrompts() {
    setStatus(elements.systemStatus, '重新載入 Prompts...', '');
    try {
      await authedJson('/admin/control-center/prompts/reload', { method: 'POST' });
      appendLog(elements.systemLog, '已重新載入 prompts cache。');
      setStatus(elements.systemStatus, 'Prompts 已重新載入。', 'success');
    } catch (err) {
      setStatus(elements.systemStatus, `操作失敗：${err.message}`, 'error');
    }
  }

  async function checkHealth() {
    setStatus(elements.systemStatus, '檢查 Gemini 狀態...', '');
    try {
      const resp = await fetch('/healthz');
      const data = await resp.json();
      appendLog(elements.systemLog, `健康檢查：${JSON.stringify(data)}`);
      setStatus(elements.systemStatus, `狀態：${data.status || 'unknown'} (${new Date().toLocaleTimeString()})`, 'success');
    } catch (err) {
      setStatus(elements.systemStatus, `檢查失敗：${err.message}`, 'error');
    }
  }

  function openLogs() {
    appendLog(elements.systemLog, '請於伺服器檢視 uvicorn.log（專案根目錄）。');
    setStatus(elements.systemStatus, '已記錄查看指示。', '');
  }

  elements.refreshUsageBtn?.addEventListener('click', () => loadUsage());
  elements.refreshDailyBtn?.addEventListener('click', () => loadDailySummary());
  elements.generateDailyBtn?.addEventListener('click', () => generateDaily());
  elements.refreshPromptsBtn?.addEventListener('click', () => loadPromptList());
  elements.savePromptBtn?.addEventListener('click', () => savePrompt());
  elements.resetPromptBtn?.addEventListener('click', () => resetPrompt());
  elements.promptSelect?.addEventListener('change', (event) => loadPromptContent(event.target.value));
  elements.refreshContentBtn?.addEventListener('click', () => loadContentStats());
  elements.reloadContentBtn?.addEventListener('click', () => reloadContent());
  elements.checkHealthBtn?.addEventListener('click', () => checkHealth());
  elements.reloadPromptsBtn?.addEventListener('click', () => reloadPrompts());
  elements.openLogsBtn?.addEventListener('click', () => openLogs());

  loadOverview();
  loadUsage(false);
  loadDailySummary(false);
  loadPromptList(false);
  loadContentStats(false);
}

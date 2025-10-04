import { createUsageState, fetchUsage, formatUsageTimestamp, toUnixTimestamp } from './usage-api.js';

export function initUsageDashboard() {
  const state = createUsageState();
  const form = document.getElementById('filters');
  const statusEl = document.getElementById('status');
  const tableBody = document.getElementById('tableBody');

  if (!form || !statusEl || !tableBody) {
    console.warn('usage dashboard: missing required DOM nodes');
    return;
  }

  function renderSummary(summary) {
    document.getElementById('sumCount').textContent = summary.count.toLocaleString();
    document.getElementById('sumInput').textContent = summary.total_input_tokens.toLocaleString();
    document.getElementById('sumOutput').textContent = summary.total_output_tokens.toLocaleString();
    document.getElementById('sumTotal').textContent = summary.total_tokens.toLocaleString();
    document.getElementById('sumLatency').textContent = summary.avg_latency_ms.toFixed(2);
    document.getElementById('sumCost').textContent = (summary.total_cost_usd ?? 0).toFixed(6);
  }

  function renderTable(items) {
    tableBody.innerHTML = '';
    if (!items.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 12;
      td.textContent = '尚無資料';
      tr.appendChild(td);
      tableBody.appendChild(tr);
      return;
    }
    items.forEach((item, idx) => {
      const tr = document.createElement('tr');
      tr.style.cursor = 'pointer';
      tr.addEventListener('click', () => showDetail(item));
      const cells = [
        state.offset + idx + 1,
        formatUsageTimestamp(item.timestamp),
        item.device_id || '-',
        item.route || '-',
        item.model,
        `${item.input_tokens}/${item.output_tokens}/${item.total_tokens}`,
        item.latency_ms.toFixed(2),
        item.inline_parts,
        item.prompt_chars,
        item.status_code ?? '-',
        (item.cost_total ?? 0).toFixed(6),
        item.api_endpoint,
      ];
      cells.forEach((value) => {
        const td = document.createElement('td');
        td.textContent = value;
        tr.appendChild(td);
      });
      const actionTd = document.createElement('td');
      const link = document.createElement('a');
      link.href = `/usage/llm/${item.id}/view`;
      link.textContent = '查看';
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.style = 'color:#2563eb;text-decoration:none;font-weight:600;';
      actionTd.appendChild(link);
      tr.appendChild(actionTd);
      tableBody.appendChild(tr);
    });
  }

  async function runFetch(query) {
    statusEl.textContent = '載入中...';
    statusEl.className = 'status';
    try {
      const data = await fetchUsage(query);
      state.lastData = data;
      renderSummary(data.summary);
      renderTable(data.items);
      statusEl.textContent = `載入完成，共 ${data.summary.count} 筆`;
      statusEl.className = 'status success';
    } catch (err) {
      statusEl.textContent = `載入失敗：${err.message}`;
      statusEl.className = 'status error';
    }
  }

  function buildQueryFromForm() {
    const formData = new FormData(form);
    const limit = Number(formData.get('limit')) || state.limit;
    state.limit = limit;
    return {
      device_id: formData.get('device_id')?.trim() || undefined,
      route: formData.get('route')?.trim() || undefined,
      model: formData.get('model')?.trim() || undefined,
      provider: formData.get('provider')?.trim() || undefined,
      since: toUnixTimestamp(formData.get('since')),
      until: toUnixTimestamp(formData.get('until')),
      limit,
      offset: state.offset,
    };
  }

  function showDetail(item) {
    window.open(`/usage/llm/${item.id}/view`, '_blank', 'noopener');
  }

  form.addEventListener('submit', (ev) => {
    ev.preventDefault();
    state.offset = 0;
    state.lastQuery = buildQueryFromForm();
    runFetch(state.lastQuery);
  });

  const resetBtn = document.getElementById('resetBtn');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      form.reset();
      state.offset = 0;
      state.lastQuery = buildQueryFromForm();
      runFetch(state.lastQuery);
    });
  }

  const prevBtn = document.getElementById('prevBtn');
  if (prevBtn) {
    prevBtn.addEventListener('click', () => {
      if (state.offset <= 0) return;
      state.offset = Math.max(0, state.offset - state.limit);
      state.lastQuery.offset = state.offset;
      runFetch(state.lastQuery);
    });
  }

  const nextBtn = document.getElementById('nextBtn');
  if (nextBtn) {
    nextBtn.addEventListener('click', () => {
      state.offset += state.limit;
      state.lastQuery.offset = state.offset;
      runFetch(state.lastQuery);
    });
  }

  const exportBtn = document.getElementById('exportJson');
  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      if (!state.lastData) return;
      const blob = new Blob([JSON.stringify(state.lastData, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `llm_usage_${Date.now()}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    });
  }

  state.lastQuery = buildQueryFromForm();
  runFetch(state.lastQuery);
}

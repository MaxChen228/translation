from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from .models import LLMUsageQueryResponse
from .recorder import query_usage, summarize_usage


router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/llm", response_model=LLMUsageQueryResponse)
def get_llm_usage(
    device_id: Optional[str] = Query(default=None),
    route: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    provider: Optional[str] = Query(default=None),
    since: Optional[float] = Query(default=None, description="Filter records newer than this Unix timestamp"),
    until: Optional[float] = Query(default=None, description="Filter records older than this Unix timestamp"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> LLMUsageQueryResponse:
    records = query_usage(
        device_id=device_id,
        route=route,
        model=model,
        provider=provider,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    summary = summarize_usage(records)
    return LLMUsageQueryResponse(summary=summary, items=records)


@router.get("/llm/view", response_class=HTMLResponse)
def llm_usage_view() -> HTMLResponse:
    html = """
<!DOCTYPE html>
<html lang=\"zh-Hant\">
  <head>
    <meta charset=\"utf-8\" />
    <title>LLM Usage Dashboard</title>
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <style>
      :root {
        color-scheme: light dark;
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }
      body {
        margin: 0;
        padding: 1.5rem;
        background: #f7f7f7;
        color: #222;
      }
      h1 {
        margin-bottom: 0.5rem;
      }
      .panel {
        background: #fff;
        border-radius: 8px;
        padding: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 1.5rem;
      }
      form {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 0.75rem;
        align-items: end;
      }
      label {
        display: flex;
        flex-direction: column;
        font-size: 0.85rem;
        gap: 0.25rem;
      }
      input, select, button {
        font: inherit;
        padding: 0.35rem 0.5rem;
        border: 1px solid #ccc;
        border-radius: 6px;
      }
      button {
        cursor: pointer;
        background: #2563eb;
        color: #fff;
        border: none;
        transition: background 0.2s ease;
      }
      button:hover {
        background: #1d4ed8;
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.9rem;
      }
      th, td {
        padding: 0.5rem;
        border-bottom: 1px solid #e5e7eb;
      }
      th {
        text-align: left;
        background: #f3f4f6;
        position: sticky;
        top: 0;
        z-index: 1;
      }
      tbody tr:nth-child(odd) {
        background: #fdfdfd;
      }
      .summary-grid {
        display: grid;
        gap: 0.75rem;
        grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      }
      .summary-card {
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        padding: 0.75rem;
        background: #fff;
      }
      .summary-card h3 {
        margin: 0;
        font-size: 0.85rem;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .summary-card p {
        margin: 0.35rem 0 0;
        font-size: 1.1rem;
        font-weight: 600;
      }
      .status {
        font-size: 0.85rem;
        margin-bottom: 0.75rem;
      }
      .status.success { color: #15803d; }
      .status.error { color: #b91c1c; }
      .actions {
        display: flex;
        gap: 0.5rem;
        margin-top: 0.75rem;
      }
      pre {
        white-space: pre-wrap;
        word-break: break-word;
        background: #111827;
        color: #f9fafb;
        padding: 0.75rem;
        border-radius: 6px;
        font-size: 0.8rem;
      }
      .table-container {
        overflow-x: auto;
        max-height: 60vh;
      }
      @media (prefers-color-scheme: dark) {
        body { background: #111827; color: #f9fafb; }
        .panel, .summary-card { background: #1f2937; border-color: #374151; }
        table { color: #e5e7eb; }
        th { background: #111827; }
        tbody tr:nth-child(odd) { background: #1f2937; }
        input, select { background: #111827; color: #e5e7eb; border-color: #374151; }
        button { background: #2563eb; }
        button:hover { background: #1d4ed8; }
      }
    </style>
  </head>
  <body>
    <h1>LLM Usage Dashboard</h1>
    <div class=\"panel\">
      <form id=\"filters\">
        <label>Device ID<input type=\"text\" name=\"device_id\" placeholder=\"device-123\" /></label>
        <label>Route<input type=\"text\" name=\"route\" placeholder=\"/correct\" /></label>
        <label>Model<input type=\"text\" name=\"model\" placeholder=\"gemini-2.5-flash\" /></label>
        <label>Provider<input type=\"text\" name=\"provider\" placeholder=\"gemini\" /></label>
        <label>Since<input type=\"datetime-local\" name=\"since\" /></label>
        <label>Until<input type=\"datetime-local\" name=\"until\" /></label>
        <label>Limit<input type=\"number\" name=\"limit\" value=\"100\" min=\"1\" max=\"1000\" /></label>
        <div class=\"actions\">
          <button type=\"submit\">查詢</button>
          <button type=\"button\" id=\"resetBtn\">重置</button>
        </div>
      </form>
      <div class=\"status\" id=\"status\">尚未載入資料。</div>
      <div class=\"actions\">
        <button type=\"button\" id=\"prevBtn\">上一頁</button>
        <button type=\"button\" id=\"nextBtn\">下一頁</button>
        <button type=\"button\" id=\"exportJson\">匯出 JSON</button>
      </div>
    </div>

    <div class=\"panel summary-grid\">
      <div class=\"summary-card\">
        <h3>總呼叫數</h3>
        <p id=\"sumCount\">0</p>
      </div>
      <div class=\"summary-card\">
        <h3>Input Tokens</h3>
        <p id=\"sumInput\">0</p>
      </div>
      <div class=\"summary-card\">
        <h3>Output Tokens</h3>
        <p id=\"sumOutput\">0</p>
      </div>
      <div class=\"summary-card\">
        <h3>Total Tokens</h3>
        <p id=\"sumTotal\">0</p>
      </div>
      <div class=\"summary-card\">
        <h3>平均延遲 (ms)</h3>
        <p id=\"sumLatency\">0</p>
      </div>
      <div class=\"summary-card\">
        <h3>估計成本 (USD)</h3>
        <p id=\"sumCost\">0.000000</p>
      </div>
    </div>

    <div class=\"panel table-container\">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>時間</th>
            <th>Device</th>
            <th>Route</th>
            <th>Model</th>
            <th>Tokens (in/out/total)</th>
            <th>Latency (ms)</th>
            <th>Inline Parts</th>
            <th>Prompt Chars</th>
            <th>Status</th>
            <th>成本 (USD)</th>
            <th>Endpoint</th>
          </tr>
        </thead>
        <tbody id=\"tableBody\"></tbody>
      </table>
    </div>

    <div class=\"panel\" id=\"rawPanel\" hidden>
      <h2>Raw JSON</h2>
      <pre id=\"rawJson\"></pre>
    </div>

    <script>
      const pricingTable = {
        'gemini-2.5-flash': { input: 0.3, output: 2.5 },
        'gemini-2.5-flash-lite': { input: 0.10, output: 0.40 },
        'gemini-2.5-pro': { input: 1.25, output: 10.0 },
      };

      const state = {
        offset: 0,
        limit: 100,
        lastQuery: {},
        lastData: null,
      };

      function computeCostUSD(item) {
        const pricing = pricingTable[item.model];
        if (!pricing) return 0;
        const inputCost = (item.input_tokens * pricing.input) / 1_000_000;
        const outputCost = (item.output_tokens * pricing.output) / 1_000_000;
        return inputCost + outputCost;
      }

      function computeTotals(items) {
        let totalCost = 0;
        items.forEach((item) => {
          totalCost += computeCostUSD(item);
        });
        return { totalCost };
      }

      function isoToLocal(iso) {
        if (!iso) return '-';
        const date = new Date(iso * 1000);
        if (Number.isNaN(date.getTime())) return '-';
        return date.toLocaleString();
      }

      function datetimeToUnix(value) {
        if (!value) return null;
        const ts = Date.parse(value);
        return Number.isNaN(ts) ? null : Math.floor(ts / 1000);
      }

      function renderSummary(summary, totals) {
        document.getElementById('sumCount').textContent = summary.count.toLocaleString();
        document.getElementById('sumInput').textContent = summary.total_input_tokens.toLocaleString();
        document.getElementById('sumOutput').textContent = summary.total_output_tokens.toLocaleString();
        document.getElementById('sumTotal').textContent = summary.total_tokens.toLocaleString();
        document.getElementById('sumLatency').textContent = summary.avg_latency_ms.toFixed(2);
        document.getElementById('sumCost').textContent = totals.totalCost.toFixed(6);
      }

      function renderTable(items) {
        const tbody = document.getElementById('tableBody');
        tbody.innerHTML = '';
        if (!items.length) {
          const tr = document.createElement('tr');
          const td = document.createElement('td');
          td.colSpan = 11;
          td.textContent = '尚無資料';
          tr.appendChild(td);
          tbody.appendChild(tr);
          return;
        }
        items.forEach((item, idx) => {
          const tr = document.createElement('tr');
          const cells = [
            state.offset + idx + 1,
            isoToLocal(item.timestamp),
            item.device_id || '-',
            item.route || '-',
            item.model,
            `${item.input_tokens}/${item.output_tokens}/${item.total_tokens}`,
            item.latency_ms.toFixed(2),
            item.inline_parts,
            item.prompt_chars,
            item.status_code ?? '-',
            computeCostUSD(item).toFixed(6),
            item.api_endpoint,
          ];
          cells.forEach((value) => {
            const td = document.createElement('td');
            td.textContent = value;
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
      }

      async function fetchUsage(query) {
        const params = new URLSearchParams();
        for (const [key, value] of Object.entries(query)) {
          if (value !== null && value !== undefined && value !== '') {
            params.append(key, value);
          }
        }
        const url = `/usage/llm?${params.toString()}`;
        const statusEl = document.getElementById('status');
        statusEl.textContent = '載入中...';
        statusEl.className = 'status';
        try {
          const resp = await fetch(url);
          if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
          }
          const data = await resp.json();
          state.lastData = data;
          const totals = computeTotals(data.items);
          renderSummary(data.summary, totals);
          renderTable(data.items);
          document.getElementById('rawJson').textContent = JSON.stringify(data, null, 2);
          document.getElementById('rawPanel').hidden = false;
          statusEl.textContent = `載入完成，共 ${data.summary.count} 筆`;
          statusEl.className = 'status success';
        } catch (err) {
          statusEl.textContent = `載入失敗：${err.message}`;
          statusEl.className = 'status error';
        }
      }

      function buildQueryFromForm(form) {
        const formData = new FormData(form);
        const limit = Number(formData.get('limit')) || state.limit;
        state.limit = limit;
        return {
          device_id: formData.get('device_id')?.trim() || undefined,
          route: formData.get('route')?.trim() || undefined,
          model: formData.get('model')?.trim() || undefined,
          provider: formData.get('provider')?.trim() || undefined,
          since: datetimeToUnix(formData.get('since')),
          until: datetimeToUnix(formData.get('until')),
          limit: limit,
          offset: state.offset,
        };
      }

      function init() {
        const form = document.getElementById('filters');
        form.addEventListener('submit', (ev) => {
          ev.preventDefault();
          state.offset = 0;
          state.lastQuery = buildQueryFromForm(form);
          fetchUsage(state.lastQuery);
        });

        document.getElementById('resetBtn').addEventListener('click', () => {
          form.reset();
          state.offset = 0;
          state.lastQuery = buildQueryFromForm(form);
          fetchUsage(state.lastQuery);
        });

        document.getElementById('prevBtn').addEventListener('click', () => {
          if (state.offset <= 0) return;
          state.offset = Math.max(0, state.offset - state.limit);
          state.lastQuery.offset = state.offset;
          fetchUsage(state.lastQuery);
        });

        document.getElementById('nextBtn').addEventListener('click', () => {
          state.offset += state.limit;
          state.lastQuery.offset = state.offset;
          fetchUsage(state.lastQuery);
        });

        document.getElementById('exportJson').addEventListener('click', () => {
          if (!state.lastData) return;
          const blob = new Blob([JSON.stringify(state.lastData, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `llm_usage_${Date.now()}.json`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
        });

        state.lastQuery = buildQueryFromForm(form);
        fetchUsage(state.lastQuery);
      }

      document.addEventListener('DOMContentLoaded', init);
    </script>
  </body>
</html>
"""
    return HTMLResponse(content=html)

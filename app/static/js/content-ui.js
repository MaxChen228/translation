import { createTokenManager, bindTokenControls } from './token-manager.js';
import { createContentApi } from './content-api.js';

export function initContentAdminPage({ initialBooks = [], initialCourses = [] } = {}) {
  const state = {
    books: initialBooks,
    courses: initialCourses,
    selectedBooks: [],
  };

  const dom = {
    tokenField: document.getElementById('token-field'),
    tokenStatus: document.getElementById('token-status'),
    saveTokenBtn: document.getElementById('save-token-btn'),
    bookCount: document.getElementById('book-count'),
    courseCount: document.getElementById('course-count'),
    bookSearch: document.getElementById('book-search'),
    courseSearch: document.getElementById('course-search'),
    bookSummaryList: document.getElementById('book-summary-list'),
    courseSummaryList: document.getElementById('course-summary-list'),
    bookCatalog: document.getElementById('book-catalog'),
    selectedTable: document.getElementById('selected-books-table'),
    bookFileInput: document.getElementById('book-file'),
    bookFilename: document.getElementById('book-filename'),
    bookJson: document.getElementById('book-json'),
    bookStatus: document.getElementById('book-status'),
    uploadBookBtn: document.getElementById('upload-book-btn'),
    addBookBtn: document.getElementById('add-book-btn'),
    courseForm: document.getElementById('course-form'),
    courseStatus: document.getElementById('course-status'),
  };

  const tokenManager = createTokenManager({ storageKey: 'content-token' });
  const api = createContentApi({ tokenManager });

  bindTokenControls({
    manager: tokenManager,
    inputEl: dom.tokenField,
    statusEl: dom.tokenStatus,
    saveButton: dom.saveTokenBtn,
    messages: {
      saved: 'Token 已儲存。',
      cleared: 'Token 已清除 Token，若後端啟用驗證將無法送出請求。',
    },
  });

  if (dom.tokenStatus) {
    dom.tokenStatus.textContent = tokenManager.getToken()
      ? 'Token 已儲存。'
      : '後端未設定 CONTENT_ADMIN_TOKEN，或尚未輸入 Token。';
  }

  function renderSummaries() {
    if (!dom.bookSummaryList || !dom.courseSummaryList) return;
    const bookKeyword = (dom.bookSearch?.value || '').trim().toLowerCase();
    const courseKeyword = (dom.courseSearch?.value || '').trim().toLowerCase();

    const filteredBooks = state.books.filter((b) => {
      const haystack = `${b.id} ${b.title || ''} ${(b.tags || []).join(' ')}`.toLowerCase();
      return haystack.includes(bookKeyword);
    });
    const filteredCourses = state.courses.filter((c) => {
      const haystack = `${c.id} ${c.title || ''} ${(c.tags || []).join(' ')}`.toLowerCase();
      return haystack.includes(courseKeyword);
    });

    if (dom.bookCount) dom.bookCount.textContent = filteredBooks.length;
    if (dom.courseCount) dom.courseCount.textContent = filteredCourses.length;

    dom.bookSummaryList.innerHTML = filteredBooks.map((b) => `
      <div class="card">
        <h4>${b.id}</h4>
        <div class="subtitle">${b.title || '—'}</div>
        <div class="muted">題數：${b.itemCount ?? '—'}</div>
        ${b.tags && b.tags.length ? `<div>${b.tags.map((t) => `<span class="badge">${t}</span>`).join('')}</div>` : ''}
        <footer>
          <span>難度：${b.difficulty ?? '—'}</span>
          <button class="table-actions" data-copy="${b.id}" data-type="book">複製 ID</button>
        </footer>
      </div>
    `).join('');

    dom.courseSummaryList.innerHTML = filteredCourses.map((c) => {
      const tags = c.tags && c.tags.length ? c.tags.map((t) => `<span class="badge">${t}</span>`).join('') : '—';
      return `<tr>
        <td>${c.id}</td>
        <td>${c.title || '—'}</td>
        <td>${c.bookCount ?? '—'}</td>
        <td>${tags}</td>
        <td class="table-actions">
          <button data-view="${c.id}">查看</button>
          <button data-copy="${c.id}" data-type="course">複製 ID</button>
        </td>
      </tr>`;
    }).join('');

    if (dom.bookCatalog) {
      dom.bookCatalog.innerHTML = state.books
        .map((b) => `<option value="${b.id}">${b.id}｜${b.title || ''}</option>`)
        .join('');
    }
  }

  function renderSelectedBooks() {
    if (!dom.selectedTable) return;
    const tbody = dom.selectedTable.querySelector('tbody');
    if (!tbody) return;

    if (!state.selectedBooks.length) {
      dom.selectedTable.style.display = 'none';
      tbody.innerHTML = '';
      return;
    }

    dom.selectedTable.style.display = '';
    tbody.innerHTML = state.selectedBooks.map((entry, idx) => {
      const source = state.books.find((b) => b.id === entry.bookId);
      const title = entry.title || (source ? source.title : '');
      const difficulty = entry.difficulty ?? (source ? source.difficulty ?? '' : '');
      return `<tr>
        <td><input data-idx="${idx}" data-field="aliasId" type="text" value="${entry.aliasId || entry.bookId}" /></td>
        <td>${entry.bookId}</td>
        <td><input data-idx="${idx}" data-field="title" type="text" value="${title || ''}" /></td>
        <td><input data-idx="${idx}" data-field="difficulty" type="number" min="1" max="5" value="${difficulty || ''}" /></td>
        <td><button type="button" data-remove="${idx}">移除</button></td>
      </tr>`;
    }).join('');
  }

  function addBookToCourse() {
    if (!dom.bookCatalog) return;
    const bookId = dom.bookCatalog.value;
    if (!bookId) return;
    if (state.selectedBooks.some((b) => b.bookId === bookId)) {
      alert('此題庫已加入課程。');
      return;
    }
    state.selectedBooks.push({ bookId, aliasId: bookId });
    renderSelectedBooks();
  }

  function removeSelected(index) {
    state.selectedBooks.splice(index, 1);
    renderSelectedBooks();
  }

  function updateSelectedValue(idx, field, value) {
    const entry = state.selectedBooks[idx];
    if (!entry) return;
    if (field === 'difficulty') {
      entry.difficulty = value ? Number(value) : null;
    } else if (field === 'aliasId') {
      entry.aliasId = value.trim();
    } else {
      entry[field] = value.trim();
    }
  }

  async function refreshData() {
    const data = await api.fetchOverview();
    if (!data) throw new Error('無法更新資料');
    state.books = data.books ?? [];
    state.courses = data.courses ?? [];
    renderSummaries();
  }

  if (dom.bookSearch) dom.bookSearch.addEventListener('input', renderSummaries);
  if (dom.courseSearch) dom.courseSearch.addEventListener('input', renderSummaries);

  if (dom.bookFileInput) {
    dom.bookFileInput.addEventListener('change', (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        if (dom.bookJson) dom.bookJson.value = reader.result;
        if (dom.bookFilename && !dom.bookFilename.value) {
          dom.bookFilename.value = file.name.replace(/\.json$/i, '');
        }
      };
      reader.readAsText(file, 'utf-8');
    });
  }

  if (dom.uploadBookBtn) {
    dom.uploadBookBtn.addEventListener('click', async () => {
      if (!dom.bookFilename || !dom.bookJson || !dom.bookStatus) return;
      const filename = dom.bookFilename.value.trim();
      const raw = dom.bookJson.value.trim();
      const statusEl = dom.bookStatus;
      if (!filename || !raw) {
        statusEl.textContent = '請輸入檔名與 JSON 內容。';
        return;
      }
      try {
        const content = JSON.parse(raw);
        const result = await api.uploadBook({ filename, content });
        if (!result?.success_count) {
          const message = result?.results?.[0]?.message || result?.detail || '上傳失敗';
          statusEl.textContent = `❌ ${message}`;
        } else {
          statusEl.textContent = '✅ 題庫上傳成功';
          await refreshData();
        }
      } catch (err) {
        statusEl.textContent = `❌ ${err.message || err}`;
      }
    });
  }

  if (dom.addBookBtn) {
    dom.addBookBtn.addEventListener('click', addBookToCourse);
  }

  if (dom.selectedTable) {
    dom.selectedTable.addEventListener('click', (event) => {
      const removeIdx = event.target?.dataset?.remove;
      if (removeIdx !== undefined) {
        removeSelected(Number(removeIdx));
      }
    });

    dom.selectedTable.addEventListener('input', (event) => {
      const target = event.target;
      const idx = Number(target.dataset.idx);
      const field = target.dataset.field;
      if (Number.isNaN(idx) || !field) return;
      updateSelectedValue(idx, field, target.value);
    });
  }

  if (dom.courseForm) {
    dom.courseForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!dom.courseStatus) return;
      if (!state.selectedBooks.length) {
        dom.courseStatus.textContent = '請至少加入一個題庫本。';
        return;
      }
      const payload = {
        courseId: document.getElementById('course-id')?.value.trim(),
        title: document.getElementById('course-title')?.value.trim(),
        summary: document.getElementById('course-summary')?.value.trim() || null,
        coverImage: document.getElementById('course-cover')?.value.trim() || null,
        tags: (document.getElementById('course-tags')?.value || '')
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        books: state.selectedBooks.map((entry) => ({
          bookId: entry.bookId,
          aliasId: (entry.aliasId || entry.bookId).trim(),
          title: entry.title || null,
          difficulty: entry.difficulty ? Number(entry.difficulty) : null,
        })),
      };
      try {
        await api.uploadCourse(payload);
        dom.courseStatus.textContent = '✅ 課程已儲存並重新載入';
        state.selectedBooks = [];
        renderSelectedBooks();
        await refreshData();
      } catch (err) {
        dom.courseStatus.textContent = `❌ ${err.message || err}`;
      }
    });
  }

  if (dom.bookSummaryList) {
    dom.bookSummaryList.addEventListener('click', (event) => {
      const target = event.target;
      const copyId = target?.dataset?.copy;
      if (!copyId) return;
      navigator.clipboard?.writeText(copyId).then(() => {
        target.textContent = '已複製';
        setTimeout(() => {
          target.textContent = '複製 ID';
        }, 1200);
      });
    });
  }

  if (dom.courseSummaryList) {
    dom.courseSummaryList.addEventListener('click', (event) => {
      const target = event.target;
      if (!target?.dataset) return;
      if (target.dataset.copy) {
        navigator.clipboard?.writeText(target.dataset.copy).then(() => {
          target.textContent = '已複製';
          setTimeout(() => {
            target.textContent = '複製 ID';
          }, 1200);
        });
      }
      if (target.dataset.view) {
        window.open(`/cloud/courses/${target.dataset.view}`, '_blank');
      }
    });
  }

  renderSummaries();
  renderSelectedBooks();
}

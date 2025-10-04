const DEFAULT_STORAGE_KEY = 'translation-admin-token';
const DEFAULT_HEADER_NAME = 'X-Content-Token';

export function createTokenManager({
  storageKey = DEFAULT_STORAGE_KEY,
  headerName = DEFAULT_HEADER_NAME,
} = {}) {
  let token = (globalThis.localStorage?.getItem(storageKey) || '').trim();

  function persist(value) {
    token = value.trim();
    if (token) {
      globalThis.localStorage?.setItem(storageKey, token);
    } else {
      globalThis.localStorage?.removeItem(storageKey);
    }
    return token;
  }

  return {
    storageKey,
    headerName,
    getToken: () => token,
    setToken(value) {
      return persist(value ?? '');
    },
    clear() {
      return persist('');
    },
    apply(headers = {}) {
      if (token) {
        headers[headerName] = token;
      }
      return headers;
    },
  };
}

export function bindTokenControls({ manager, inputEl, statusEl, saveButton, messages = {} }) {
  if (!manager || !inputEl) {
    return;
  }

  inputEl.value = manager.getToken();

  function updateStatus(text, type = 'neutral') {
    if (!statusEl) return;
    statusEl.textContent = text || '';
    statusEl.dataset.state = type;
  }

  const saveHandler = () => {
    const value = inputEl.value || '';
    manager.setToken(value);
    updateStatus(value ? messages.saved || 'Token 已儲存。' : messages.cleared || 'Token 已清除。');
  };

  if (saveButton) {
    saveButton.addEventListener('click', saveHandler);
  } else {
    inputEl.addEventListener('change', saveHandler);
  }

  return { updateStatus };
}

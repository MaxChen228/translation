import { authedFetch, authedFetchJson } from './admin-client.js';

export function createContentApi({ tokenManager } = {}) {
  function request(url, options = {}) {
    return authedFetch(url, { ...options, tokenManager });
  }

  async function requestJson(url, options = {}) {
    return authedFetchJson(url, { ...options, tokenManager });
  }

  return {
    async fetchOverview() {
      return requestJson('/admin/content/ui/data');
    },
    async uploadBook({ filename, content }) {
      return requestJson('/admin/content/upload', {
        method: 'POST',
        json: {
          filename,
          content,
          content_type: 'book',
        },
      });
    },
    async uploadCourse(payload) {
      return requestJson('/admin/content/ui/course', {
        method: 'POST',
        json: payload,
      });
    },
    async reloadContent() {
      return request('/admin/content/reload', { method: 'POST' });
    },
  };
}

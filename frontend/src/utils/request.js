const BASE_URL = '/api';
function getAuthHeaders() {
    const token = localStorage.getItem('token');
    return token ? { Authorization: `Bearer ${token}` } : {};
}
async function handleResponse(response) {
    if (response.status === 401) {
        localStorage.removeItem('token');
        localStorage.removeItem('user');
        window.location.href = '/login';
        throw new Error('未登录或登录已过期');
    }
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = body.detail;
        throw new Error(typeof detail === 'string' ? detail : `请求失败 (${response.status})`);
    }
    return response.json();
}
const request = {
    async get(url, params) {
        const searchParams = new URLSearchParams();
        if (params) {
            for (const [key, value] of Object.entries(params)) {
                if (value !== undefined) {
                    searchParams.set(key, String(value));
                }
            }
        }
        const query = searchParams.toString();
        const fullUrl = `${BASE_URL}${url}${query ? `?${query}` : ''}`;
        const response = await fetch(fullUrl, {
            headers: { ...getAuthHeaders() },
        });
        return handleResponse(response);
    },
    async post(url, data) {
        const response = await fetch(`${BASE_URL}${url}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders(),
            },
            body: data ? JSON.stringify(data) : undefined,
        });
        return handleResponse(response);
    },
    async put(url, data) {
        const response = await fetch(`${BASE_URL}${url}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders(),
            },
            body: data ? JSON.stringify(data) : undefined,
        });
        return handleResponse(response);
    },
    async patch(url, data) {
        const response = await fetch(`${BASE_URL}${url}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
                ...getAuthHeaders(),
            },
            body: data ? JSON.stringify(data) : undefined,
        });
        return handleResponse(response);
    },
    async delete(url) {
        const response = await fetch(`${BASE_URL}${url}`, {
            method: 'DELETE',
            headers: { ...getAuthHeaders() },
        });
        return handleResponse(response);
    },
    async upload(url, formData) {
        const response = await fetch(`${BASE_URL}${url}`, {
            method: 'POST',
            headers: { ...getAuthHeaders() },
            body: formData,
        });
        return handleResponse(response);
    },
};
export default request;

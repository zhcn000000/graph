import request from '@/utils/request';
export const login = (data) => {
    return fetch('/api/login', {
        method: 'POST',
        body: data,
    }).then((res) => {
        if (!res.ok)
            throw new Error('登录失败，请检查用户名和密码');
        return res.json();
    });
};
export const register = (data) => {
    return request.post('/register', data);
};
export const refreshToken = () => {
    return request.post('/refresh');
};
export const getCurrentUser = () => {
    return request.get('/me');
};

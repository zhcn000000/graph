import request from '@/utils/request';
export const getSessionList = () => {
    return request.get('/chat/list');
};
export const createSession = (data) => {
    return request.post('/chat/', data);
};
export const deleteSession = (sessionId) => {
    return request.delete(`/chat/${sessionId}`);
};
export const renameSession = (sessionId, data) => {
    return request.patch(`/chat/${sessionId}`, data);
};

import request from '@/utils/request';
export const searchRag = (data) => {
    return request.post('/rag/search', data);
};
export const uploadDocument = (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return request.upload('/rag/documents/upload', formData);
};
export const loadCsv = (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return request.upload('/rag/documents/load-csv', formData);
};
export const ingestArtifacts = (museum, limit) => {
    const params = {};
    if (museum)
        params.museum = museum;
    if (limit)
        params.limit = limit;
    return request.post(`/rag/documents/ingest-artifacts?${new URLSearchParams(params).toString()}`);
};

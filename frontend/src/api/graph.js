import request from '@/utils/request';
export const createVertex = (data) => {
    return request.post('/graph/vertex', data);
};
export const getVertex = (uri, label) => {
    return request.get(`/graph/vertex/${encodeURIComponent(uri)}`, { label });
};
export const updateVertex = (uri, data, label) => {
    return request.put(`/graph/vertex/${encodeURIComponent(uri)}`, { ...data, label });
};
export const deleteVertex = (uri, label) => {
    return request.delete(`/graph/vertex/${encodeURIComponent(uri)}?label=${label ?? ''}`);
};
export const createEdge = (data) => {
    return request.post('/graph/edge', data);
};
export const getNeighbors = (uri, direction, maxHops) => {
    return request.get(`/graph/neighbors/${encodeURIComponent(uri)}`, { direction, max_hops: maxHops });
};
export const traverseGraph = (startUri, maxHops, direction) => {
    return request.get(`/graph/traverse/${encodeURIComponent(startUri)}`, {
        max_hops: maxHops,
        direction,
    });
};
export const traverseMulti = (data) => {
    return request.post('/graph/traverse/multi', data);
};
export const findPaths = (startUri, endUri, maxHops) => {
    return request.get(`/graph/paths/${encodeURIComponent(startUri)}/${encodeURIComponent(endUri)}`, { max_hops: maxHops });
};
export const expandContext = (data) => {
    return request.post('/graph/context', data);
};
export const queryEntityPaths = (data) => {
    return request.post('/graph/entity-paths', data);
};

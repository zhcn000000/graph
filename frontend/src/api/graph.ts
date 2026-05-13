import request from '@/utils/request'
import type {
  GraphOperationResponse,
  GraphEntityRequest,
  GraphEdgeRequest,
  GraphContextRequest,
  PathQueryRequest,
  TraverseMultiRequest,
} from './types'

export const createVertex = (data: GraphEntityRequest): Promise<GraphOperationResponse> => {
  return request.post('/graph/vertex', data)
}

export const getVertex = (uri: string, label?: string): Promise<GraphOperationResponse> => {
  return request.get(`/graph/vertex/${encodeURIComponent(uri)}`, { label })
}

export const updateVertex = (uri: string, data: GraphEntityRequest, label?: string): Promise<GraphOperationResponse> => {
  return request.put(`/graph/vertex/${encodeURIComponent(uri)}`, { ...data, label })
}

export const deleteVertex = (uri: string, label?: string): Promise<GraphOperationResponse> => {
  return request.delete(`/graph/vertex/${encodeURIComponent(uri)}?label=${label ?? ''}`)
}

export const createEdge = (data: GraphEdgeRequest): Promise<GraphOperationResponse> => {
  return request.post('/graph/edge', data)
}

export const getNeighbors = (
  uri: string,
  direction?: string,
  maxHops?: number,
): Promise<GraphOperationResponse> => {
  return request.get(`/graph/neighbors/${encodeURIComponent(uri)}`, { direction, max_hops: maxHops })
}

export const traverseGraph = (
  startUri: string,
  maxHops?: number,
  direction?: string,
): Promise<GraphOperationResponse> => {
  return request.get(`/graph/traverse/${encodeURIComponent(startUri)}`, {
    max_hops: maxHops,
    direction,
  })
}

export const traverseMulti = (data: TraverseMultiRequest): Promise<GraphOperationResponse> => {
  return request.post('/graph/traverse/multi', data)
}

export const findPaths = (
  startUri: string,
  endUri: string,
  maxHops?: number,
): Promise<GraphOperationResponse> => {
  return request.get(
    `/graph/paths/${encodeURIComponent(startUri)}/${encodeURIComponent(endUri)}`,
    { max_hops: maxHops },
  )
}

export const expandContext = (data: GraphContextRequest): Promise<GraphOperationResponse> => {
  return request.post('/graph/context', data)
}

export const queryEntityPaths = (data: PathQueryRequest): Promise<GraphOperationResponse> => {
  return request.post('/graph/entity-paths', data)
}

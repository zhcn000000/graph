import request from '@/utils/request'
import type {
  SearchRequest,
  SearchResponse,
  DocumentUploadResponse,
  FileIngestResponse,
} from './types'

export const searchRag = (data: SearchRequest): Promise<SearchResponse> => {
  return request.post('/rag/search', data)
}

export const uploadDocument = (file: File): Promise<DocumentUploadResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  return request.upload('/rag/documents/upload', formData)
}

export const loadCsv = (file: File): Promise<FileIngestResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  return request.upload('/rag/documents/load-csv', formData)
}

export const ingestArtifacts = (museum?: string, limit?: number): Promise<FileIngestResponse> => {
  const params: Record<string, string | number | boolean | undefined> = {}
  if (museum) params.museum = museum
  if (limit) params.limit = limit
  return request.post(`/rag/documents/ingest-artifacts?${new URLSearchParams(params as Record<string, string>).toString()}`)
}

export interface StatusResponse {
  success: boolean
  status?: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserCredentialsRequest {
  username: string
  password: string
}

export interface UserResponse {
  id: string
  username: string
}

export interface UserListResponse {
  users: UserResponse[]
}

export interface UpdateUserRequest {
  username?: string
  password?: string
}

export interface SearchRequest {
  queries: string[]
  regex?: string
  file_ids?: string[]
  use_graph?: boolean
  max_hops?: number
  graph_weight?: number
  vector_weight?: number
  bm25_weight?: number
  offset?: number
  k?: number
}

export interface SearchResponse extends StatusResponse {
  results: Record<string, unknown>[]
  graph_entities: Record<string, unknown>[]
}

export interface GraphEntityRequest {
  label: string
  properties: Record<string, unknown>
}

export interface GraphEdgeRequest {
  start_uri: string
  end_uri: string
  relationship_type: string
  properties?: Record<string, unknown>
}

export interface GraphContextRequest {
  entity_uri: string
  max_hops?: number
  direction?: string
}

export interface PathQueryRequest {
  start_uri: string
  end_uri: string
  max_hops?: number
}

export interface TraverseMultiRequest {
  uris: string[]
  max_hops?: number
  direction?: string
}

export interface GraphOperationResponse extends StatusResponse {
  data?: Record<string, unknown>
}

export interface GraphNode {
  id: string
  label: string
  properties: Record<string, unknown>
}

export interface GraphEdge {
  source: string
  target: string
  relationship: string
  properties?: Record<string, unknown>
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface DocumentUploadResponse extends StatusResponse {
  file_id?: string
  document_count?: number
}

export interface FileIngestResponse extends StatusResponse {
  documents_created?: number
  status?: string
}

export interface ChatRequest {
  text: string
  files?: unknown[]
  model?: string
  thinking?: boolean
  select_toolset?: string[]
}

export interface ChatTitleRequest {
  text: string
}

export interface ChatTitleResponse extends StatusResponse {
  title?: string
}

export interface RenameRequest {
  name: string
}

export interface SessionInfo {
  session_id: string
  name: string
}

export interface SessionCreateResponse extends StatusResponse {
  session_id?: string
  name?: string
}

export interface SessionListResponse extends StatusResponse {
  sessions: SessionInfo[]
}

export interface HistoryResponse extends StatusResponse {
  messages?: unknown[]
}

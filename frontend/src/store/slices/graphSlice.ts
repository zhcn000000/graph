import { createSlice, createAsyncThunk, type PayloadAction } from '@reduxjs/toolkit'
import { traverseGraph, getNeighbors, findPaths, getVertex } from '@/api/graph'
import type { GraphData } from '@/api/types'

interface GraphState {
  data: GraphData | null
  selectedNode: Record<string, unknown> | null
  loading: boolean
  error: string | null
  searchQuery: string
}

const initialState: GraphState = {
  data: null,
  selectedNode: null,
  loading: false,
  error: null,
  searchQuery: '',
}

export const fetchGraphTraverse = createAsyncThunk(
  'graph/traverse',
  async (params: { uri: string; maxHops?: number; direction?: string }, { rejectWithValue }) => {
    try {
      const res = await traverseGraph(params.uri, params.maxHops, params.direction)
      return (res.data as GraphData) ?? { nodes: [], edges: [] }
    } catch (err) {
      return rejectWithValue(err instanceof Error ? err.message : '获取图谱数据失败')
    }
  },
)

export const fetchGraphNeighbors = createAsyncThunk(
  'graph/neighbors',
  async (params: { uri: string; direction?: string; maxHops?: number }, { rejectWithValue }) => {
    try {
      const res = await getNeighbors(params.uri, params.direction, params.maxHops)
      return (res.data as GraphData) ?? { nodes: [], edges: [] }
    } catch (err) {
      return rejectWithValue(err instanceof Error ? err.message : '获取邻居节点失败')
    }
  },
)

export const fetchGraphPaths = createAsyncThunk(
  'graph/paths',
  async (params: { startUri: string; endUri: string; maxHops?: number }, { rejectWithValue }) => {
    try {
      const res = await findPaths(params.startUri, params.endUri, params.maxHops)
      return (res.data as GraphData) ?? { nodes: [], edges: [] }
    } catch (err) {
      return rejectWithValue(err instanceof Error ? err.message : '查询路径失败')
    }
  },
)

export const fetchVertexInfo = createAsyncThunk(
  'graph/vertexInfo',
  async (uri: string, { rejectWithValue }) => {
    try {
      const res = await getVertex(uri)
      return res.data as Record<string, unknown>
    } catch (err) {
      return rejectWithValue(err instanceof Error ? err.message : '获取节点信息失败')
    }
  },
)

const graphSlice = createSlice({
  name: 'graph',
  initialState,
  reducers: {
    setGraphData(state, action: PayloadAction<GraphData>) {
      state.data = action.payload
    },
    setSelectedNode(state, action: PayloadAction<Record<string, unknown> | null>) {
      state.selectedNode = action.payload
    },
    setSearchQuery(state, action: PayloadAction<string>) {
      state.searchQuery = action.payload
    },
    clearGraphData(state) {
      state.data = null
      state.selectedNode = null
      state.error = null
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchGraphTraverse.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchGraphTraverse.fulfilled, (state, action) => {
        state.loading = false
        state.data = action.payload
      })
      .addCase(fetchGraphTraverse.rejected, (state, action) => {
        state.loading = false
        state.error = action.payload as string
      })
      .addCase(fetchGraphNeighbors.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchGraphNeighbors.fulfilled, (state, action) => {
        state.loading = false
        state.data = action.payload
      })
      .addCase(fetchGraphNeighbors.rejected, (state, action) => {
        state.loading = false
        state.error = action.payload as string
      })
      .addCase(fetchGraphPaths.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchGraphPaths.fulfilled, (state, action) => {
        state.loading = false
        state.data = action.payload
      })
      .addCase(fetchGraphPaths.rejected, (state, action) => {
        state.loading = false
        state.error = action.payload as string
      })
      .addCase(fetchVertexInfo.fulfilled, (state, action) => {
        state.selectedNode = action.payload
      })
  },
})

export const { setGraphData, setSelectedNode, setSearchQuery, clearGraphData } = graphSlice.actions
export default graphSlice.reducer

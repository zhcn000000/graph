import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { traverseGraph, getNeighbors, findPaths, getVertex } from '@/api/graph';
const initialState = {
    data: null,
    selectedNode: null,
    loading: false,
    error: null,
    searchQuery: '',
};
export const fetchGraphTraverse = createAsyncThunk('graph/traverse', async (params, { rejectWithValue }) => {
    try {
        const res = await traverseGraph(params.uri, params.maxHops, params.direction);
        return res.data ?? { nodes: [], edges: [] };
    }
    catch (err) {
        return rejectWithValue(err instanceof Error ? err.message : '获取图谱数据失败');
    }
});
export const fetchGraphNeighbors = createAsyncThunk('graph/neighbors', async (params, { rejectWithValue }) => {
    try {
        const res = await getNeighbors(params.uri, params.direction, params.maxHops);
        return res.data ?? { nodes: [], edges: [] };
    }
    catch (err) {
        return rejectWithValue(err instanceof Error ? err.message : '获取邻居节点失败');
    }
});
export const fetchGraphPaths = createAsyncThunk('graph/paths', async (params, { rejectWithValue }) => {
    try {
        const res = await findPaths(params.startUri, params.endUri, params.maxHops);
        return res.data ?? { nodes: [], edges: [] };
    }
    catch (err) {
        return rejectWithValue(err instanceof Error ? err.message : '查询路径失败');
    }
});
export const fetchVertexInfo = createAsyncThunk('graph/vertexInfo', async (uri, { rejectWithValue }) => {
    try {
        const res = await getVertex(uri);
        return res.data;
    }
    catch (err) {
        return rejectWithValue(err instanceof Error ? err.message : '获取节点信息失败');
    }
});
const graphSlice = createSlice({
    name: 'graph',
    initialState,
    reducers: {
        setGraphData(state, action) {
            state.data = action.payload;
        },
        setSelectedNode(state, action) {
            state.selectedNode = action.payload;
        },
        setSearchQuery(state, action) {
            state.searchQuery = action.payload;
        },
        clearGraphData(state) {
            state.data = null;
            state.selectedNode = null;
            state.error = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchGraphTraverse.pending, (state) => {
            state.loading = true;
            state.error = null;
        })
            .addCase(fetchGraphTraverse.fulfilled, (state, action) => {
            state.loading = false;
            state.data = action.payload;
        })
            .addCase(fetchGraphTraverse.rejected, (state, action) => {
            state.loading = false;
            state.error = action.payload;
        })
            .addCase(fetchGraphNeighbors.pending, (state) => {
            state.loading = true;
            state.error = null;
        })
            .addCase(fetchGraphNeighbors.fulfilled, (state, action) => {
            state.loading = false;
            state.data = action.payload;
        })
            .addCase(fetchGraphNeighbors.rejected, (state, action) => {
            state.loading = false;
            state.error = action.payload;
        })
            .addCase(fetchGraphPaths.pending, (state) => {
            state.loading = true;
            state.error = null;
        })
            .addCase(fetchGraphPaths.fulfilled, (state, action) => {
            state.loading = false;
            state.data = action.payload;
        })
            .addCase(fetchGraphPaths.rejected, (state, action) => {
            state.loading = false;
            state.error = action.payload;
        })
            .addCase(fetchVertexInfo.fulfilled, (state, action) => {
            state.selectedNode = action.payload;
        });
    },
});
export const { setGraphData, setSelectedNode, setSearchQuery, clearGraphData } = graphSlice.actions;
export default graphSlice.reducer;

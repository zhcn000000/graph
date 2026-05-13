import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import graphReducer from './slices/graphSlice';
export const store = configureStore({
    reducer: {
        auth: authReducer,
        graph: graphReducer,
    },
});

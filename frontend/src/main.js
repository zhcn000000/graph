import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { store } from './store';
import MainLayout from './layouts/MainLayout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import GraphPage from './pages/GraphPage';
import DocumentUploadPage from './pages/DocumentUploadPage';
import CsvImportPage from './pages/CsvImportPage';
import SpiderPage from './pages/SpiderPage';
import ChatPage from './pages/ChatPage';
import './index.css';
function ProtectedRoute({ children }) {
    const token = localStorage.getItem('token');
    if (!token) {
        return React.createElement(Navigate, { to: "/login", replace: true });
    }
    return React.createElement(React.Fragment, null, children);
}
createRoot(document.getElementById('root')).render(React.createElement(StrictMode, null,
    React.createElement(Provider, { store: store },
        React.createElement(ConfigProvider, { locale: zhCN },
            React.createElement(AntApp, null,
                React.createElement(BrowserRouter, null,
                    React.createElement(Routes, null,
                        React.createElement(Route, { path: "/login", element: React.createElement(LoginPage, null) }),
                        React.createElement(Route, { element: React.createElement(ProtectedRoute, null,
                                React.createElement(MainLayout, null)) },
                            React.createElement(Route, { path: "/", element: React.createElement(DashboardPage, null) }),
                            React.createElement(Route, { path: "/graph", element: React.createElement(GraphPage, null) }),
                            React.createElement(Route, { path: "/chat", element: React.createElement(ChatPage, null) }),
                            React.createElement(Route, { path: "/documents/upload", element: React.createElement(DocumentUploadPage, null) }),
                            React.createElement(Route, { path: "/documents/csv", element: React.createElement(CsvImportPage, null) }),
                            React.createElement(Route, { path: "/spider", element: React.createElement(SpiderPage, null) })),
                        React.createElement(Route, { path: "*", element: React.createElement(Navigate, { to: "/", replace: true }) }))))))));

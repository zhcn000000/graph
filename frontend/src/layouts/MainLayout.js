import { useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, Avatar, Space, Typography, Dropdown, theme, } from 'antd';
import { DatabaseOutlined, CloudUploadOutlined, FileAddOutlined, BugOutlined, RobotOutlined, MenuFoldOutlined, MenuUnfoldOutlined, LogoutOutlined, UserOutlined, DashboardOutlined, } from '@ant-design/icons';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { logout } from '@/store/slices/authSlice';
const { Header, Sider, Content } = Layout;
const { Title } = Typography;
const menuItems = [
    {
        key: '/',
        icon: React.createElement(DashboardOutlined, null),
        label: '首页',
    },
    {
        key: '/graph',
        icon: React.createElement(DatabaseOutlined, null),
        label: '知识图谱',
    },
    {
        key: '/chat',
        icon: React.createElement(RobotOutlined, null),
        label: 'AI 问答',
    },
    {
        type: 'divider',
    },
    {
        key: '/documents/upload',
        icon: React.createElement(CloudUploadOutlined, null),
        label: '文档上传',
    },
    {
        key: '/documents/csv',
        icon: React.createElement(FileAddOutlined, null),
        label: 'CSV 导入',
    },
    {
        key: '/spider',
        icon: React.createElement(BugOutlined, null),
        label: '爬虫控制',
    },
];
export default function MainLayout() {
    const [collapsed, setCollapsed] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();
    const dispatch = useAppDispatch();
    const user = useAppSelector((state) => state.auth.user);
    const { token: themeToken } = theme.useToken();
    const selectedKeys = [location.pathname];
    const handleMenuClick = ({ key }) => {
        navigate(key);
    };
    const handleLogout = () => {
        dispatch(logout());
        navigate('/login');
    };
    const userMenuItems = [
        {
            key: 'logout',
            label: '退出登录',
            icon: React.createElement(LogoutOutlined, null),
            danger: true,
            onClick: handleLogout,
        },
    ];
    return (React.createElement(Layout, { style: { minHeight: '100vh' } },
        React.createElement(Sider, { trigger: null, collapsible: true, collapsed: collapsed, style: {
                overflow: 'auto',
                height: '100vh',
                position: 'fixed',
                left: 0,
                top: 0,
                bottom: 0,
                zIndex: 100,
            } },
            React.createElement("div", { style: {
                    height: 64,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: 16,
                } },
                React.createElement(Space, null,
                    React.createElement(Avatar, { size: 32, style: { backgroundColor: tokenTheme.colorPrimary } }, "KG"),
                    !collapsed && (React.createElement(Title, { level: 5, style: { color: '#fff', margin: 0, whiteSpace: 'nowrap' } }, "\u6587\u7269\u56FE\u8C31")))),
            React.createElement(Menu, { theme: "dark", mode: "inline", selectedKeys: selectedKeys, items: menuItems, onClick: handleMenuClick })),
        React.createElement(Layout, { style: { marginLeft: collapsed ? 80 : 220, transition: 'margin-left 0.2s' } },
            React.createElement(Header, { style: {
                    padding: '0 24px',
                    background: tokenTheme.colorBgContainer,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
                    position: 'sticky',
                    top: 0,
                    zIndex: 99,
                } },
                React.createElement(Button, { type: "text", icon: collapsed ? React.createElement(MenuUnfoldOutlined, null) : React.createElement(MenuFoldOutlined, null), onClick: () => setCollapsed(!collapsed), style: { fontSize: 16 } }),
                React.createElement(Space, null, user ? (React.createElement(Dropdown, { menu: { items: userMenuItems }, placement: "bottomRight" },
                    React.createElement(Space, { style: { cursor: 'pointer' } },
                        React.createElement(Avatar, { style: { backgroundColor: tokenTheme.colorPrimary } }, user.username[0].toUpperCase()),
                        React.createElement("span", null, user.username)))) : (React.createElement(Avatar, { icon: React.createElement(UserOutlined, null) })))),
            React.createElement(Content, { style: {
                    padding: 24,
                    minHeight: 'calc(100vh - 64px)',
                    background: tokenTheme.colorBgLayout,
                } },
                React.createElement(Outlet, null)))));
}

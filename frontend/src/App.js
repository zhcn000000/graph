import { useState } from 'react';
import { Layout, Menu, Input, Card, Row, Col, Statistic, Table, Tag, Image, Typography, Space, Button, Avatar, Breadcrumb, Progress } from 'antd';
import { SearchOutlined, DatabaseOutlined, BankOutlined, HistoryOutlined, FileImageOutlined, TeamOutlined, GlobalOutlined, MenuFoldOutlined, MenuUnfoldOutlined, ArrowRightOutlined, WarningOutlined } from '@ant-design/icons';
import './App.css';
const { Header, Sider, Content, Footer } = Layout;
const { Title, Text } = Typography;
const artifactData = [
    {
        key: '1',
        name: '清乾隆粉彩花卉瓶',
        dynasty: '清朝',
        type: '瓷器',
        museum: '大英博物馆',
        material: '瓷',
        image: 'https://placehold.co/100x100?text=花瓶'
    },
    {
        key: '2',
        name: '商代青铜鼎',
        dynasty: '商朝',
        type: '青铜器',
        museum: '大都会艺术博物馆',
        material: '青铜',
        image: 'https://placehold.co/100x100?text=青铜鼎'
    },
    {
        key: '3',
        name: '唐代三彩骆驼',
        dynasty: '唐朝',
        type: '陶俑',
        museum: '卢浮宫',
        material: '陶器',
        image: 'https://placehold.co/100x100?text=骆驼'
    },
    {
        key: '4',
        name: '宋代汝窑茶盏',
        dynasty: '宋朝',
        type: '瓷器',
        museum: '大英博物馆',
        material: '瓷',
        image: 'https://placehold.co/100x100?text=茶盏'
    },
    {
        key: '5',
        name: '东汉陶俑',
        dynasty: '汉朝',
        type: '陶俑',
        museum: '大都会艺术博物馆',
        material: '陶器',
        image: 'https://placehold.co/100x100?text=陶俑'
    }
];
const columns = [
    {
        title: '文物图片',
        dataIndex: 'image',
        key: 'image',
        render: (text) => React.createElement(Image, { src: text, width: 60, height: 60, fallback: "https://placehold.co/60x60?text=N/A" })
    },
    {
        title: '文物名称',
        dataIndex: 'name',
        key: 'name',
        render: (text) => React.createElement(Text, { strong: true }, text)
    },
    {
        title: '年代',
        dataIndex: 'dynasty',
        key: 'dynasty',
        render: (text) => React.createElement(Tag, { color: "blue" }, text)
    },
    {
        title: '类型',
        dataIndex: 'type',
        key: 'type',
        render: (text) => React.createElement(Tag, { color: "green" }, text)
    },
    {
        title: '材质',
        dataIndex: 'material',
        key: 'material',
        render: (text) => React.createElement(Tag, { color: "orange" }, text)
    },
    {
        title: '所属博物馆',
        dataIndex: 'museum',
        key: 'museum',
        render: (text) => React.createElement(Text, null, text)
    }
];
function App() {
    const [collapsed, setCollapsed] = useState(false);
    const menuItems = [
        {
            key: 'home',
            icon: React.createElement(GlobalOutlined, null),
            label: '首页',
        },
        {
            key: 'artifacts',
            icon: React.createElement(FileImageOutlined, null),
            label: '文物浏览',
        },
        {
            key: 'graph',
            icon: React.createElement(DatabaseOutlined, null),
            label: '知识图谱',
        },
        {
            key: 'museums',
            icon: React.createElement(BankOutlined, null),
            label: '博物馆',
        },
        {
            key: 'timeline',
            icon: React.createElement(HistoryOutlined, null),
            label: '历史时空',
        },
        {
            key: 'artists',
            icon: React.createElement(TeamOutlined, null),
            label: '艺术家',
        }
    ];
    return (React.createElement(Layout, { className: "app-layout" },
        React.createElement(Sider, { trigger: null, collapsible: true, collapsed: collapsed, className: "app-sider", width: 220 },
            React.createElement("div", { className: "logo" }, collapsed ? (React.createElement(Avatar, { size: 32, style: { backgroundColor: '#1890ff' } }, "KG")) : (React.createElement(Space, null,
                React.createElement(Avatar, { size: 32, style: { backgroundColor: '#1890ff' } }, "KG"),
                React.createElement(Title, { level: 5, style: { color: '#fff', margin: 0 } }, "\u6587\u7269\u56FE\u8C31")))),
            React.createElement(Menu, { theme: "dark", mode: "inline", defaultSelectedKeys: ['home'], items: menuItems })),
        React.createElement(Layout, null,
            React.createElement(Header, { className: "app-header" },
                React.createElement(Space, null, React.createElement(Button, { type: "text", icon: collapsed ? React.createElement(MenuUnfoldOutlined, null) : React.createElement(MenuFoldOutlined, null), onClick: () => setCollapsed(!collapsed), className: "collapse-btn" })),
                React.createElement(Space, { size: "large" },
                    React.createElement(Input, { placeholder: "\u641C\u7D22\u6587\u7269\u3001\u535A\u7269\u9986\u3001\u827A\u672F\u5BB6...", prefix: React.createElement(SearchOutlined, null), className: "search-input", size: "large" }),
                    React.createElement(Avatar, { style: { backgroundColor: '#87d068' } }, "\u7528\u6237"))),
            React.createElement(Content, { className: "app-content" },
                React.createElement(Breadcrumb, { className: "breadcrumb", items: [{ title: '首页' }] }),
                React.createElement("div", { className: "hero-section" },
                    React.createElement(Title, { level: 2 }, "\u6D77\u5916\u4E2D\u56FD\u6587\u7269\u77E5\u8BC6\u56FE\u8C31"),
                    React.createElement(Text, { type: "secondary", className: "hero-subtitle" }, "\u63A2\u7D22\u6D77\u5916\u535A\u7269\u9986\u6536\u85CF\u7684\u4E2D\u56FD\u6587\u7269\uFF0C\u6784\u5EFA\u7ED3\u6784\u5316\u77E5\u8BC6\u56FE\u8C31")),
                React.createElement(Row, { gutter: [24, 24], className: "stats-row" },
                    React.createElement(Col, { xs: 24, sm: 12, md: 6 },
                        React.createElement(Card, null,
                            React.createElement(Statistic, { title: "\u6587\u7269\u603B\u6570", value: 12580, prefix: React.createElement(FileImageOutlined, null), valueStyle: { color: '#1890ff' } }))),
                    React.createElement(Col, { xs: 24, sm: 12, md: 6 },
                        React.createElement(Card, null,
                            React.createElement(Statistic, { title: "\u535A\u7269\u9986\u6570\u91CF", value: 12, prefix: React.createElement(BankOutlined, null), valueStyle: { color: '#52c41a' } }))),
                    React.createElement(Col, { xs: 24, sm: 12, md: 6 },
                        React.createElement(Card, null,
                            React.createElement(Statistic, { title: "\u6D89\u53CA\u671D\u4EE3", value: 28, prefix: React.createElement(HistoryOutlined, null), valueStyle: { color: '#faad14' } }))),
                    React.createElement(Col, { xs: 24, sm: 12, md: 6 },
                        React.createElement(Card, null,
                            React.createElement(Statistic, { title: "\u4E09\u5143\u7EC4\u6570\u91CF", value: 85600, prefix: React.createElement(DatabaseOutlined, null), valueStyle: { color: '#f5222d' } })))),
                React.createElement(Row, { gutter: [24, 24], className: "main-content" },
                    React.createElement(Col, { xs: 24, lg: 14 },
                        React.createElement(Card, { title: "\u6587\u7269\u5217\u8868", extra: React.createElement(Button, { type: "link", icon: React.createElement(ArrowRightOutlined, null) }, "\u67E5\u770B\u5168\u90E8"), className: "artifact-card" },
                            React.createElement(Table, { columns: columns, dataSource: artifactData, pagination: false, size: "small" })),
                        React.createElement(Card, { title: "\u6570\u636E\u8D28\u91CF\u76D1\u63A7", className: "quality-card" },
                            React.createElement(Space, { direction: "vertical", style: { width: '100%' } },
                                React.createElement("div", null,
                                    React.createElement(Text, null, "\u56FE\u7247\u6709\u6548\u7387"),
                                    React.createElement(Progress, { percent: 96, status: "active" })),
                                React.createElement("div", null,
                                    React.createElement(Text, null, "\u5B57\u6BB5\u5B8C\u6574\u7387"),
                                    React.createElement(Progress, { percent: 89, status: "active" })),
                                React.createElement("div", null,
                                    React.createElement(Text, null, "\u5B9E\u4F53\u5BF9\u9F50\u7387"),
                                    React.createElement(Progress, { percent: 78, status: "active" }))))),
                    React.createElement(Col, { xs: 24, lg: 10 },
                        React.createElement(Card, { title: "\u77E5\u8BC6\u56FE\u8C31\u9884\u89C8", className: "graph-preview" },
                            React.createElement("div", { className: "graph-placeholder" },
                                React.createElement(GlobalOutlined, { style: { fontSize: 64, color: '#1890ff' } }),
                                React.createElement(Text, { type: "secondary" }, "\u56FE\u8C31\u53EF\u89C6\u5316\u533A\u57DF"),
                                React.createElement(Text, { type: "secondary", style: { fontSize: 12 } }, "\u5C55\u793A\u6587\u7269\u3001\u535A\u7269\u9986\u3001\u671D\u4EE3\u3001\u827A\u672F\u5BB6\u4E4B\u95F4\u7684\u5173\u7CFB\u7F51\u7EDC")),
                            React.createElement("div", { className: "graph-legend" },
                                React.createElement(Space, { wrap: true },
                                    React.createElement(Tag, { color: "blue" }, "\u6587\u7269"),
                                    React.createElement(Tag, { color: "green" }, "\u535A\u7269\u9986"),
                                    React.createElement(Tag, { color: "orange" }, "\u671D\u4EE3"),
                                    React.createElement(Tag, { color: "purple" }, "\u827A\u672F\u5BB6"),
                                    React.createElement(Tag, { color: "cyan" }, "\u5730\u70B9")))),
                        React.createElement(Card, { title: "\u6570\u636E\u66F4\u65B0\u65E5\u5FD7", className: "log-card" },
                            React.createElement(Space, { direction: "vertical", style: { width: '100%' } },
                                React.createElement("div", { className: "log-item" },
                                    React.createElement(WarningOutlined, { style: { color: '#faad14' } }),
                                    React.createElement(Text, { style: { marginLeft: 8 } }, "\u5927\u82F1\u535A\u7269\u9986\u65B0\u589E 23 \u4EF6\u6587\u7269"),
                                    React.createElement(Text, { type: "secondary", style: { marginLeft: 'auto' } }, "2\u5C0F\u65F6\u524D")),
                                React.createElement("div", { className: "log-item" },
                                    React.createElement(WarningOutlined, { style: { color: '#52c41a' } }),
                                    React.createElement(Text, { style: { marginLeft: 8 } }, "\u5B8C\u6210\u589E\u91CF\u722C\u53D6 - 12 \u6761\u66F4\u65B0"),
                                    React.createElement(Text, { type: "secondary", style: { marginLeft: 'auto' } }, "\u6628\u5929")),
                                React.createElement("div", { className: "log-item" },
                                    React.createElement(WarningOutlined, { style: { color: '#1890ff' } }),
                                    React.createElement(Text, { style: { marginLeft: 8 } }, "\u5B9E\u4F53\u5BF9\u9F50\u5B8C\u6210 - \u5408\u5E76 45 \u4E2A\u91CD\u590D\u5B9E\u4F53"),
                                    React.createElement(Text, { type: "secondary", style: { marginLeft: 'auto' } }, "3\u5929\u524D"))))))),
            React.createElement(Footer, { className: "app-footer" },
                React.createElement(Text, { type: "secondary" }, "\u6D77\u5916\u4E2D\u56FD\u6587\u7269\u77E5\u8BC6\u56FE\u8C31\u6784\u5EFA\u7CFB\u7EDF \u00A9 2024")))));
}
export default App;

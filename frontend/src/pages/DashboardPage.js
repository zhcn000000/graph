import { useState, useEffect } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Typography, Progress, Space, Button } from 'antd';
import { DatabaseOutlined, BankOutlined, HistoryOutlined, FileImageOutlined, WarningOutlined, ArrowRightOutlined, GlobalOutlined, } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { searchRag } from '@/api/documents';
import { getSessionList } from '@/api/sessions';
const { Title, Text } = Typography;
const columns = [
    {
        title: '文物名称',
        dataIndex: 'name',
        key: 'name',
        render: (text) => React.createElement(Text, { strong: true }, text),
    },
    {
        title: '年代',
        dataIndex: 'dynasty',
        key: 'dynasty',
        render: (text) => React.createElement(Tag, { color: "blue" }, text),
    },
    {
        title: '类型',
        dataIndex: 'type',
        key: 'type',
        render: (text) => React.createElement(Tag, { color: "green" }, text),
    },
    {
        title: '材质',
        dataIndex: 'material',
        key: 'material',
        render: (text) => React.createElement(Tag, { color: "orange" }, text),
    },
    {
        title: '所属博物馆',
        dataIndex: 'museum',
        key: 'museum',
        render: (text) => React.createElement(Text, null, text),
    },
];
const recentLogs = [
    { text: '大英博物馆新增 23 件文物', time: '2小时前', color: '#faad14' },
    { text: '完成增量爬取 - 12 条更新', time: '昨天', color: '#52c41a' },
    { text: '实体对齐完成 - 合并 45 个重复实体', time: '3天前', color: '#1890ff' },
];
export default function DashboardPage() {
    const navigate = useNavigate();
    const [stats, setStats] = useState({ artifacts: 0, museums: 0, dynasties: 0, triples: 0 });
    const [sessionCount, setSessionCount] = useState(0);
    const [recentArtifacts, setRecentArtifacts] = useState([]);
    const [loading, setLoading] = useState(false);
    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            try {
                const res = await searchRag({
                    queries: ['中国文物'],
                    use_graph: true,
                    k: 5,
                    max_hops: 2,
                    graph_weight: 0.3,
                    vector_weight: 0.4,
                    bm25_weight: 0.3,
                });
                if (res.results) {
                    const rows = res.results.map((r, i) => ({
                        key: String(i),
                        name: r.title || r.name || `文物 ${i + 1}`,
                        dynasty: r.period || r.dynasty || '未知',
                        type: r.type || '未知',
                        museum: r.museum || '未知',
                        material: r.material || '未知',
                    }));
                    setRecentArtifacts(rows);
                }
                if (res.graph_entities) {
                    setStats((prev) => ({ ...prev, triples: res.graph_entities.length }));
                }
            }
            catch {
                // Use fallback data
            }
            try {
                const sessions = await getSessionList();
                setSessionCount(sessions.sessions?.length ?? 0);
            }
            catch {
                // ignore
            }
            setLoading(false);
        };
        fetchData();
    }, []);
    return (React.createElement("div", null,
        React.createElement("div", { style: {
                textAlign: 'center',
                padding: '32px 0',
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                borderRadius: 12,
                marginBottom: 24,
            } },
            React.createElement(Title, { level: 2, style: { color: '#fff', marginBottom: 8 } }, "\u6D77\u5916\u4E2D\u56FD\u6587\u7269\u77E5\u8BC6\u56FE\u8C31"),
            React.createElement(Text, { style: { color: 'rgba(255,255,255,0.85)', fontSize: 16 } }, "\u63A2\u7D22\u6D77\u5916\u535A\u7269\u9986\u6536\u85CF\u7684\u4E2D\u56FD\u6587\u7269\uFF0C\u6784\u5EFA\u7ED3\u6784\u5316\u77E5\u8BC6\u56FE\u8C31")),
        React.createElement(Row, { gutter: [24, 24], style: { marginBottom: 24 } },
            React.createElement(Col, { xs: 24, sm: 12, md: 6 },
                React.createElement(Card, null,
                    React.createElement(Statistic, { title: "\u6587\u7269\u603B\u6570", value: stats.artifacts || 12580, prefix: React.createElement(FileImageOutlined, null), valueStyle: { color: '#1890ff' } }))),
            React.createElement(Col, { xs: 24, sm: 12, md: 6 },
                React.createElement(Card, null,
                    React.createElement(Statistic, { title: "\u535A\u7269\u9986\u6570\u91CF", value: stats.museums || 12, prefix: React.createElement(BankOutlined, null), valueStyle: { color: '#52c41a' } }))),
            React.createElement(Col, { xs: 24, sm: 12, md: 6 },
                React.createElement(Card, null,
                    React.createElement(Statistic, { title: "\u6D3B\u8DC3\u4F1A\u8BDD", value: sessionCount, prefix: React.createElement(HistoryOutlined, null), valueStyle: { color: '#faad14' } }))),
            React.createElement(Col, { xs: 24, sm: 12, md: 6 },
                React.createElement(Card, null,
                    React.createElement(Statistic, { title: "\u4E09\u5143\u7EC4\u6570\u91CF", value: stats.triples || 85600, prefix: React.createElement(DatabaseOutlined, null), valueStyle: { color: '#f5222d' } })))),
        React.createElement(Row, { gutter: [24, 24] },
            React.createElement(Col, { xs: 24, lg: 14 },
                React.createElement(Card, { title: "\u6587\u7269\u5217\u8868", extra: React.createElement(Button, { type: "link", icon: React.createElement(ArrowRightOutlined, null), onClick: () => navigate('/graph') }, "\u67E5\u770B\u5168\u90E8") },
                    React.createElement(Table, { columns: columns, dataSource: recentArtifacts, pagination: false, size: "small", loading: loading, locale: { emptyText: '暂无数据，请先导入文档或启动爬虫' } })),
                React.createElement(Card, { title: "\u6570\u636E\u8D28\u91CF\u76D1\u63A7", style: { marginTop: 24 } },
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
                React.createElement(Card, { title: "\u77E5\u8BC6\u56FE\u8C31\u9884\u89C8" },
                    React.createElement("div", { style: {
                            height: 280,
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            background: 'linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%)',
                            borderRadius: 8,
                            gap: 12,
                            cursor: 'pointer',
                        }, onClick: () => navigate('/graph') },
                        React.createElement(GlobalOutlined, { style: { fontSize: 64, color: '#1890ff' } }),
                        React.createElement(Text, { type: "secondary" }, "\u70B9\u51FB\u8FDB\u5165\u56FE\u8C31\u53EF\u89C6\u5316"),
                        React.createElement(Text, { type: "secondary", style: { fontSize: 12 } }, "\u5C55\u793A\u6587\u7269\u3001\u535A\u7269\u9986\u3001\u671D\u4EE3\u3001\u827A\u672F\u5BB6\u4E4B\u95F4\u7684\u5173\u7CFB\u7F51\u7EDC")),
                    React.createElement("div", { style: { marginTop: 16, textAlign: 'center' } },
                        React.createElement(Space, { wrap: true },
                            React.createElement(Tag, { color: "blue" }, "\u6587\u7269"),
                            React.createElement(Tag, { color: "green" }, "\u535A\u7269\u9986"),
                            React.createElement(Tag, { color: "orange" }, "\u671D\u4EE3"),
                            React.createElement(Tag, { color: "purple" }, "\u827A\u672F\u5BB6"),
                            React.createElement(Tag, { color: "cyan" }, "\u5730\u70B9")))),
                React.createElement(Card, { title: "\u6570\u636E\u66F4\u65B0\u65E5\u5FD7", style: { marginTop: 24 } },
                    React.createElement(Space, { direction: "vertical", style: { width: '100%' } }, recentLogs.map((log) => (React.createElement("div", { key: log.text, style: {
                            display: 'flex',
                            alignItems: 'center',
                            padding: '8px 0',
                            borderBottom: i < recentLogs.length - 1 ? '1px solid #f0f0f0' : 'none',
                        } },
                        React.createElement(WarningOutlined, { style: { color: log.color } }),
                        React.createElement(Text, { style: { marginLeft: 8, flex: 1 } }, log.text),
                        React.createElement(Text, { type: "secondary" }, log.time))))))))));
}

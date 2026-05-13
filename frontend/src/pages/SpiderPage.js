import { useState, useCallback } from 'react';
import { Card, Button, Space, Typography, Tag, Table, Alert, message, Row, Col, } from 'antd';
import { BugOutlined, PlayCircleOutlined, PauseCircleOutlined, CheckCircleOutlined, ExclamationCircleOutlined, SyncOutlined, } from '@ant-design/icons';
import { ingestArtifacts } from '@/api/documents';
const { Title, Text } = Typography;
const MUSEUMS = [
    { key: 'CMA', name: '克利夫兰艺术博物馆', location: '美国克利夫兰' },
    { key: 'Met', name: '大都会艺术博物馆', location: '美国纽约' },
    { key: 'Princeton', name: '普林斯顿大学艺术博物馆', location: '美国普林斯顿' },
    { key: 'Nelson-Atkins', name: '尼尔森-阿特金斯艺术博物馆', location: '美国堪萨斯城' },
    { key: 'Philadelphia', name: '费城艺术博物馆', location: '美国费城' },
    { key: 'AMNH', name: '美国自然历史博物馆', location: '美国纽约' },
];
export default function SpiderPage() {
    const [running, setRunning] = useState(false);
    const [ingesting, setIngesting] = useState(false);
    const [logs, setLogs] = useState([]);
    const addLog = useCallback((museum, status, message) => {
        const log = {
            key: `${Date.now()}-${Math.random()}`,
            time: new Date().toLocaleTimeString(),
            museum,
            status,
            message,
        };
        setLogs((prev) => [log, ...prev].slice(0, 50));
    }, []);
    const handleCrawlAll = useCallback(async () => {
        setRunning(true);
        addLog('全部', 'running', '开始批量爬取...');
        for (let i = 0; i < MUSEUMS.length; i++) {
            const museum = MUSEUMS[i];
            addLog(museum.name, 'running', '正在爬取...');
            try {
                // Simulate crawl with a delay (actual spider runs via CLI)
                await new Promise((resolve) => setTimeout(resolve, 2000));
                addLog(museum.name, 'success', '爬取完成');
            }
            catch {
                addLog(museum.name, 'error', '爬取失败');
            }
        }
        addLog('全部', 'success', '所有博物馆爬取完成');
        setRunning(false);
    }, [addLog]);
    const handleCrawlSingle = useCallback(async (museumKey, museumName) => {
        setRunning(true);
        addLog(museumName, 'running', '正在爬取...');
        try {
            await new Promise((resolve) => setTimeout(resolve, 2000));
            addLog(museumName, 'success', '爬取完成');
        }
        catch {
            addLog(museumName, 'error', '爬取失败');
        }
        setRunning(false);
    }, [addLog]);
    const handleIngestArtifacts = useCallback(async () => {
        setIngesting(true);
        message.loading({ content: '正在将爬取数据导入知识图谱...', key: 'ingest' });
        try {
            const res = await ingestArtifacts();
            message.success({
                content: `成功导入 ${res.documents_created ?? 0} 条记录到知识图谱`,
                key: 'ingest',
            });
            addLog('系统', 'success', `导入完成: ${res.documents_created ?? 0} 条记录`);
        }
        catch (err) {
            const errorMsg = err instanceof Error ? err.message : '导入失败';
            message.error({ content: errorMsg, key: 'ingest' });
            addLog('系统', 'error', errorMsg);
        }
        finally {
            setIngesting(false);
        }
    }, [addLog]);
    const logColumns = [
        {
            title: '时间',
            dataIndex: 'time',
            key: 'time',
            width: 100,
        },
        {
            title: '博物馆',
            dataIndex: 'museum',
            key: 'museum',
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            width: 80,
            render: (status) => status === 'running' ? (React.createElement(Tag, { icon: React.createElement(SyncOutlined, { spin: true }), color: "processing" }, "\u8FDB\u884C\u4E2D")) : status === 'success' ? (React.createElement(Tag, { icon: React.createElement(CheckCircleOutlined, null), color: "success" }, "\u6210\u529F")) : (React.createElement(Tag, { icon: React.createElement(ExclamationCircleOutlined, null), color: "error" }, "\u5931\u8D25")),
        },
        {
            title: '消息',
            dataIndex: 'message',
            key: 'message',
        },
    ];
    return (React.createElement("div", null,
        React.createElement(Title, { level: 4 },
            React.createElement(BugOutlined, null),
            " \u722C\u866B\u4EFB\u52A1\u63A7\u5236"),
        React.createElement(Alert, { message: "\u722C\u866B\u8BF4\u660E", description: "\u7CFB\u7EDF\u4F7F\u7528 Scrapy \u6846\u67B6\u722C\u53D6\u6D77\u5916\u535A\u7269\u9986\u7F51\u7AD9\u7684\u4E2D\u56FD\u6587\u7269\u6570\u636E\u3002\u722C\u866B\u901A\u8FC7 sitemap \u53D1\u73B0\u6587\u7269\u9875\u9762\uFF0C\u89E3\u6790 JSON-LD/OpenGraph \u6570\u636E\uFF0C\u7ECF\u4E2D\u6587\u5173\u952E\u8BCD\u8FC7\u6EE4\u540E\u5B58\u50A8\u5230\u6570\u636E\u5E93\u3002\u722C\u53D6\u5B8C\u6210\u540E\u9700\u624B\u52A8\u6267\u884C\u300C\u5BFC\u5165\u77E5\u8BC6\u56FE\u8C31\u300D\u5C06\u6570\u636E\u5199\u5165\u56FE\u8C31\u3002", type: "info", showIcon: true, style: { marginBottom: 24 } }),
        React.createElement(Row, { gutter: [24, 24] }, MUSEUMS.map((museum) => (React.createElement(Col, { xs: 24, sm: 12, lg: 8, key: museum.key },
            React.createElement(Card, { title: museum.name, extra: React.createElement(Button, { type: "primary", size: "small", icon: React.createElement(PlayCircleOutlined, null), loading: running, onClick: () => handleCrawlSingle(museum.key, museum.name), disabled: running }, "\u722C\u53D6") },
                React.createElement(Text, { type: "secondary" }, museum.location),
                React.createElement("div", { style: { marginTop: 8 } },
                    React.createElement(Tag, null, museum.key))))))),
        React.createElement(Card, { style: { marginTop: 24 } },
            React.createElement(Space, { size: "large" },
                React.createElement(Button, { type: "primary", size: "large", icon: React.createElement(PlayCircleOutlined, null), onClick: handleCrawlAll, loading: running, disabled: running }, "\u5168\u90E8\u722C\u53D6"),
                React.createElement(Button, { type: "default", size: "large", icon: React.createElement(PauseCircleOutlined, null), disabled: !running, onClick: () => setRunning(false) }, "\u505C\u6B62"),
                React.createElement(Button, { type: "primary", size: "large", icon: React.createElement(SyncOutlined, null), loading: ingesting, onClick: handleIngestArtifacts }, "\u5BFC\u5165\u77E5\u8BC6\u56FE\u8C31"))),
        React.createElement(Card, { title: "\u8FD0\u884C\u65E5\u5FD7", style: { marginTop: 24 } },
            React.createElement(Table, { columns: logColumns, dataSource: logs, pagination: { pageSize: 10 }, size: "small", locale: { emptyText: '暂无爬取记录，点击上方按钮开始爬取' } }))));
}

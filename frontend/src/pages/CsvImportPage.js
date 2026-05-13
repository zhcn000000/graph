import { useState } from 'react';
import { Card, Upload, Space, Typography, message, Table, Tag, Alert, Progress, } from 'antd';
import { InboxOutlined, FileAddOutlined, FileExcelOutlined } from '@ant-design/icons';
import { loadCsv } from '@/api/documents';
const { Title, Text } = Typography;
const { Dragger } = Upload;
export default function CsvImportPage() {
    const [records, setRecords] = useState([]);
    const [uploading, setUploading] = useState(false);
    const handleUpload = async (options) => {
        const { file, onSuccess, onError } = options;
        if (!(file instanceof File)) {
            onError?.(new Error('文件格式错误'));
            return;
        }
        const record = {
            key: `${Date.now()}`,
            name: file.name,
            size: file.size > 1024 * 1024 ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${(file.size / 1024).toFixed(1)} KB`,
            status: 'uploading',
        };
        setRecords((prev) => [record, ...prev]);
        setUploading(true);
        try {
            const res = await loadCsv(file);
            setRecords((prev) => prev.map((r) => r.key === record.key
                ? { ...r, status: 'success', documentsCreated: res.documents_created }
                : r));
            message.success(`CSV 文件 ${file.name} 导入成功，已创建 ${res.documents_created ?? 0} 条记录`);
            onSuccess?.(res, file);
        }
        catch (err) {
            const errorMsg = err instanceof Error ? err.message : '导入失败';
            setRecords((prev) => prev.map((r) => (r.key === record.key ? { ...r, status: 'error', error: errorMsg } : r)));
            message.error(errorMsg);
            onError?.(err instanceof Error ? err : new Error(errorMsg));
        }
        finally {
            setUploading(false);
        }
    };
    const columns = [
        {
            title: '文件名',
            dataIndex: 'name',
            key: 'name',
            render: (text) => (React.createElement(Space, null,
                React.createElement(FileExcelOutlined, { style: { color: '#52c41a' } }),
                React.createElement(Text, null, text))),
        },
        {
            title: '大小',
            dataIndex: 'size',
            key: 'size',
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            render: (status, record) => status === 'uploading' ? (React.createElement(Tag, { color: "processing" }, "\u5BFC\u5165\u4E2D")) : status === 'success' ? (React.createElement(Tag, { color: "success" }, "\u6210\u529F")) : (React.createElement(Tag, { color: "error" }, record.error ?? '失败')),
        },
        {
            title: '创建记录数',
            dataIndex: 'documentsCreated',
            key: 'documentsCreated',
            render: (count) => (count !== undefined ? React.createElement(Tag, { color: "blue" }, count) : '-'),
        },
    ];
    const totalCreated = records
        .filter((r) => r.status === 'success')
        .reduce((sum, r) => sum + (r.documentsCreated ?? 0), 0);
    return (React.createElement("div", null,
        React.createElement(Title, { level: 4 },
            React.createElement(FileAddOutlined, null),
            " CSV \u6570\u636E\u5BFC\u5165"),
        React.createElement(Alert, { message: "CSV \u5BFC\u5165\u8BF4\u660E", description: React.createElement("div", null,
                React.createElement("p", null, "CSV \u6587\u4EF6\u5E94\u5305\u542B\u4EE5\u4E0B\u5217\uFF08\u5BF9\u5E94\u535A\u7269\u9986\u6587\u7269\u6570\u636E\uFF09\uFF1A"),
                React.createElement(Space, { wrap: true },
                    React.createElement(Tag, null, "object_id"),
                    React.createElement(Tag, null, "title"),
                    React.createElement(Tag, null, "period"),
                    React.createElement(Tag, null, "type"),
                    React.createElement(Tag, null, "material"),
                    React.createElement(Tag, null, "description"),
                    React.createElement(Tag, null, "dimensions"),
                    React.createElement(Tag, null, "museum"),
                    React.createElement(Tag, null, "location"),
                    React.createElement(Tag, null, "detail_url"),
                    React.createElement(Tag, null, "image_url")),
                React.createElement("p", { style: { marginTop: 8 } }, "\u7CFB\u7EDF\u4F1A\u81EA\u52A8\u4ECE CSV \u884C\u4E2D\u63D0\u53D6\u4E09\u5143\u7EC4\uFF08\u6587\u7269-\u6536\u85CF\u4E8E-\u535A\u7269\u9986\u3001\u6587\u7269-\u5C5E\u4E8E-\u671D\u4EE3\u3001\u6587\u7269-\u6750\u8D28-\u6750\u6599\u7B49\uFF09\uFF0C \u5E76\u5199\u5165\u77E5\u8BC6\u56FE\u8C31\u3002")), type: "info", showIcon: true, style: { marginBottom: 24 } }),
        React.createElement(Card, { style: { marginBottom: 24 } },
            React.createElement(Dragger, { multiple: true, customRequest: handleUpload, showUploadList: false, accept: ".csv", disabled: uploading },
                React.createElement("p", { className: "ant-upload-drag-icon" },
                    React.createElement(InboxOutlined, null)),
                React.createElement("p", { className: "ant-upload-text" }, "\u70B9\u51FB\u6216\u62D6\u62FD CSV \u6587\u4EF6\u5230\u6B64\u533A\u57DF\u4E0A\u4F20"),
                React.createElement("p", { className: "ant-upload-hint" }, "\u652F\u6301\u535A\u7269\u9986\u6587\u7269\u6570\u636E CSV\uFF0C\u7CFB\u7EDF\u5C06\u81EA\u52A8\u63D0\u53D6\u4E09\u5143\u7EC4"))),
        totalCreated > 0 && (React.createElement(Card, { style: { marginBottom: 24 } },
            React.createElement(Space, { direction: "vertical", style: { width: '100%' } },
                React.createElement(Text, null,
                    "\u603B\u5171\u521B\u5EFA\u8BB0\u5F55\u6570: ",
                    totalCreated),
                React.createElement(Progress, { percent: 100, status: "success" })))),
        records.length > 0 && (React.createElement(Card, { title: "\u5BFC\u5165\u8BB0\u5F55" },
            React.createElement(Table, { columns: columns, dataSource: records, pagination: { pageSize: 10 }, size: "small" })))));
}

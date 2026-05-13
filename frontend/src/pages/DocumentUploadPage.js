import { useState } from 'react';
import { Card, Upload, Space, Typography, message, Progress, Table, Tag, Alert, } from 'antd';
import { InboxOutlined, CloudUploadOutlined, FileTextOutlined } from '@ant-design/icons';
import { uploadDocument } from '@/api/documents';
const { Title, Text } = Typography;
const { Dragger } = Upload;
export default function DocumentUploadPage() {
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
            const res = await uploadDocument(file);
            setRecords((prev) => prev.map((r) => r.key === record.key
                ? { ...r, status: 'success', documentCount: res.document_count, fileId: res.file_id }
                : r));
            message.success(`文件 ${file.name} 上传成功，已创建 ${res.document_count ?? 0} 个文档块`);
            onSuccess?.(res, file);
        }
        catch (err) {
            const errorMsg = err instanceof Error ? err.message : '上传失败';
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
                React.createElement(FileTextOutlined, null),
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
            render: (status, record) => status === 'uploading' ? (React.createElement(Tag, { color: "processing" }, "\u4E0A\u4F20\u4E2D")) : status === 'success' ? (React.createElement(Tag, { color: "success" }, "\u6210\u529F")) : (React.createElement(Tag, { color: "error" }, record.error ?? '失败')),
        },
        {
            title: '文档块数',
            dataIndex: 'documentCount',
            key: 'documentCount',
            render: (count) => (count !== undefined ? React.createElement(Tag, null, count) : '-'),
        },
    ];
    const totalDocs = records
        .filter((r) => r.status === 'success')
        .reduce((sum, r) => sum + (r.documentCount ?? 0), 0);
    return (React.createElement("div", null,
        React.createElement(Title, { level: 4 },
            React.createElement(CloudUploadOutlined, null),
            " \u6587\u6863\u4E0A\u4F20"),
        React.createElement(Alert, { message: "\u652F\u6301\u7684\u683C\u5F0F", description: "\u652F\u6301 PDF\u3001Word\u3001Excel\u3001PPT\u3001\u56FE\u7247\u3001HTML\u3001Markdown \u7B49\u5E38\u89C1\u683C\u5F0F\u3002\u7CFB\u7EDF\u4F1A\u81EA\u52A8\u5C06\u6587\u6863\u8F6C\u6362\u4E3A Markdown\uFF0C\u8FDB\u884C\u4E2D\u6587\u5206\u8BCD\u3001\u5411\u91CF\u5D4C\u5165\uFF0C\u5E76\u63D0\u53D6\u5B9E\u4F53\u548C\u5173\u7CFB\u5B58\u5165\u77E5\u8BC6\u56FE\u8C31\u3002", type: "info", showIcon: true, style: { marginBottom: 24 } }),
        React.createElement(Card, { style: { marginBottom: 24 } },
            React.createElement(Dragger, { multiple: true, customRequest: handleUpload, showUploadList: false, accept: ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.html,.htm,.jpg,.jpeg,.png,.gif,.webp", disabled: uploading },
                React.createElement("p", { className: "ant-upload-drag-icon" },
                    React.createElement(InboxOutlined, null)),
                React.createElement("p", { className: "ant-upload-text" }, "\u70B9\u51FB\u6216\u62D6\u62FD\u6587\u4EF6\u5230\u6B64\u533A\u57DF\u4E0A\u4F20"),
                React.createElement("p", { className: "ant-upload-hint" }, "\u652F\u6301\u5355\u4E2A\u6216\u6279\u91CF\u4E0A\u4F20\uFF0C\u7CFB\u7EDF\u5C06\u81EA\u52A8\u5904\u7406\u6587\u6863\u5185\u5BB9"))),
        totalDocs > 0 && (React.createElement(Card, { style: { marginBottom: 24 } },
            React.createElement(Space, { direction: "vertical", style: { width: '100%' } },
                React.createElement(Text, null,
                    "\u603B\u6587\u6863\u5757\u6570: ",
                    totalDocs),
                React.createElement(Progress, { percent: 100, status: "success" })))),
        records.length > 0 && (React.createElement(Card, { title: "\u4E0A\u4F20\u8BB0\u5F55" },
            React.createElement(Table, { columns: columns, dataSource: records, pagination: { pageSize: 10 }, size: "small" })))));
}

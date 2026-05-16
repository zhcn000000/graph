import { FileAddOutlined, FileExcelOutlined, InboxOutlined } from "@ant-design/icons";
import type { UploadProps } from "antd";
import { Alert, Card, message, Progress, Space, Table, Tag, Typography, Upload } from "antd";
import { useState } from "react";
import { loadCsv } from "@/api/documents";

const { Title, Text } = Typography;
const { Dragger } = Upload;

interface CsvRecord {
  key: string;
  name: string;
  size: string;
  status: "uploading" | "success" | "error";
  documentsCreated?: number;
  error?: string;
}

export default function CsvImportPage() {
  const [records, setRecords] = useState<CsvRecord[]>([]);
  const [uploading, setUploading] = useState(false);

  const handleUpload: UploadProps["customRequest"] = async (options) => {
    const { file, onSuccess, onError } = options;
    if (!(file instanceof File)) {
      onError?.(new Error("文件格式错误"));
      return;
    }

    const record: CsvRecord = {
      key: `${Date.now()}`,
      name: file.name,
      size:
        file.size > 1024 * 1024 ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${(file.size / 1024).toFixed(1)} KB`,
      status: "uploading",
    };

    setRecords((prev) => [record, ...prev]);
    setUploading(true);

    try {
      const res = await loadCsv(file);
      setRecords((prev) =>
        prev.map((r) =>
          r.key === record.key ? { ...r, status: "success", documentsCreated: res.documents_created } : r,
        ),
      );
      message.success(`CSV 文件 ${file.name} 导入成功，已创建 ${res.documents_created ?? 0} 条记录`);
      onSuccess?.(res, file);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "导入失败";
      setRecords((prev) => prev.map((r) => (r.key === record.key ? { ...r, status: "error", error: errorMsg } : r)));
      message.error(errorMsg);
      onError?.(err instanceof Error ? err : new Error(errorMsg));
    } finally {
      setUploading(false);
    }
  };

  const columns = [
    {
      title: "文件名",
      dataIndex: "name",
      key: "name",
      render: (text: string) => (
        <Space>
          <FileExcelOutlined style={{ color: "#52c41a" }} />
          <Text>{text}</Text>
        </Space>
      ),
    },
    {
      title: "大小",
      dataIndex: "size",
      key: "size",
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (status: string, record: CsvRecord) =>
        status === "uploading" ? (
          <Tag color="processing">导入中</Tag>
        ) : status === "success" ? (
          <Tag color="success">成功</Tag>
        ) : (
          <Tag color="error">{record.error ?? "失败"}</Tag>
        ),
    },
    {
      title: "创建记录数",
      dataIndex: "documentsCreated",
      key: "documentsCreated",
      render: (count: number | undefined) => (count !== undefined ? <Tag color="blue">{count}</Tag> : "-"),
    },
  ];

  const totalCreated = records
    .filter((r) => r.status === "success")
    .reduce((sum, r) => sum + (r.documentsCreated ?? 0), 0);

  return (
    <div>
      <Title level={4}>
        <FileAddOutlined /> CSV 数据导入
      </Title>

      <Alert
        message="CSV 导入说明"
        description={
          <div>
            <p>CSV 文件应包含以下列（对应博物馆文物数据）：</p>
            <Space wrap>
              <Tag>object_id</Tag>
              <Tag>title</Tag>
              <Tag>period</Tag>
              <Tag>type</Tag>
              <Tag>material</Tag>
              <Tag>description</Tag>
              <Tag>dimensions</Tag>
              <Tag>museum</Tag>
              <Tag>location</Tag>
              <Tag>detail_url</Tag>
              <Tag>image_url</Tag>
            </Space>
            <p style={{ marginTop: 8 }}>
              系统会自动从 CSV 行中提取三元组（文物-收藏于-博物馆、文物-属于-朝代、文物-材质-材料等）， 并写入知识图谱。
            </p>
          </div>
        }
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Card style={{ marginBottom: 24 }}>
        <Dragger multiple customRequest={handleUpload} showUploadList={false} accept=".csv" disabled={uploading}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽 CSV 文件到此区域上传</p>
          <p className="ant-upload-hint">支持博物馆文物数据 CSV，系统将自动提取三元组</p>
        </Dragger>
      </Card>

      {totalCreated > 0 && (
        <Card style={{ marginBottom: 24 }}>
          <Space direction="vertical" style={{ width: "100%" }}>
            <Text>总共创建记录数: {totalCreated}</Text>
            <Progress percent={100} status="success" />
          </Space>
        </Card>
      )}

      {records.length > 0 && (
        <Card title="导入记录">
          <Table columns={columns} dataSource={records} pagination={{ pageSize: 10 }} size="small" />
        </Card>
      )}
    </div>
  );
}

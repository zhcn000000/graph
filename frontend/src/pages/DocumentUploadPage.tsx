import { useState } from 'react'
import {
  Card,
  Upload,
  Button,
  Space,
  Typography,
  message,
  Progress,
  Table,
  Tag,
  Alert,
} from 'antd'
import { InboxOutlined, CloudUploadOutlined, FileTextOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import { uploadDocument } from '@/api/documents'

const { Title, Text } = Typography
const { Dragger } = Upload

interface UploadRecord {
  key: string
  name: string
  size: string
  status: 'uploading' | 'success' | 'error'
  documentCount?: number
  fileId?: string
  error?: string
}

export default function DocumentUploadPage() {
  const [records, setRecords] = useState<UploadRecord[]>([])
  const [uploading, setUploading] = useState(false)

  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const { file, onSuccess, onError } = options
    if (!(file instanceof File)) {
      onError?.(new Error('文件格式错误'))
      return
    }

    const record: UploadRecord = {
      key: `${Date.now()}`,
      name: file.name,
      size: file.size > 1024 * 1024 ? `${(file.size / 1024 / 1024).toFixed(1)} MB` : `${(file.size / 1024).toFixed(1)} KB`,
      status: 'uploading',
    }

    setRecords((prev) => [record, ...prev])
    setUploading(true)

    try {
      const res = await uploadDocument(file)
      setRecords((prev) =>
        prev.map((r) =>
          r.key === record.key
            ? { ...r, status: 'success', documentCount: res.document_count, fileId: res.file_id }
            : r,
        ),
      )
      message.success(`文件 ${file.name} 上传成功，已创建 ${res.document_count ?? 0} 个文档块`)
      onSuccess?.(res, file)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '上传失败'
      setRecords((prev) =>
        prev.map((r) => (r.key === record.key ? { ...r, status: 'error', error: errorMsg } : r)),
      )
      message.error(errorMsg)
      onError?.(err instanceof Error ? err : new Error(errorMsg))
    } finally {
      setUploading(false)
    }
  }

  const columns = [
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      render: (text: string) => (
        <Space>
          <FileTextOutlined />
          <Text>{text}</Text>
        </Space>
      ),
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
      render: (status: string, record: UploadRecord) =>
        status === 'uploading' ? (
          <Tag color="processing">上传中</Tag>
        ) : status === 'success' ? (
          <Tag color="success">成功</Tag>
        ) : (
          <Tag color="error">{record.error ?? '失败'}</Tag>
        ),
    },
    {
      title: '文档块数',
      dataIndex: 'documentCount',
      key: 'documentCount',
      render: (count: number | undefined) => (count !== undefined ? <Tag>{count}</Tag> : '-'),
    },
  ]

  const totalDocs = records
    .filter((r) => r.status === 'success')
    .reduce((sum, r) => sum + (r.documentCount ?? 0), 0)

  return (
    <div>
      <Title level={4}>
        <CloudUploadOutlined /> 文档上传
      </Title>

      <Alert
        message="支持的格式"
        description="支持 PDF、Word、Excel、PPT、图片、HTML、Markdown 等常见格式。系统会自动将文档转换为 Markdown，进行中文分词、向量嵌入，并提取实体和关系存入知识图谱。"
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Card style={{ marginBottom: 24 }}>
        <Dragger
          multiple
          customRequest={handleUpload}
          showUploadList={false}
          accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.md,.html,.htm,.jpg,.jpeg,.png,.gif,.webp"
          disabled={uploading}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
          <p className="ant-upload-hint">
            支持单个或批量上传，系统将自动处理文档内容
          </p>
        </Dragger>
      </Card>

      {totalDocs > 0 && (
        <Card style={{ marginBottom: 24 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text>总文档块数: {totalDocs}</Text>
            <Progress percent={100} status="success" />
          </Space>
        </Card>
      )}

      {records.length > 0 && (
        <Card title="上传记录">
          <Table
            columns={columns}
            dataSource={records}
            pagination={{ pageSize: 10 }}
            size="small"
          />
        </Card>
      )}
    </div>
  )
}

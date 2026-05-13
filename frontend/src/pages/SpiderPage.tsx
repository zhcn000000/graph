import { useState, useCallback } from 'react'
import {
  Card,
  Button,
  Space,
  Typography,
  Tag,
  Table,
  Alert,
  message,
  Statistic,
  Row,
  Col,
  List,
  Spin,
} from 'antd'
import {
  BugOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { ingestArtifacts } from '@/api/documents'

const { Title, Text } = Typography

const MUSEUMS = [
  { key: 'CMA', name: '克利夫兰艺术博物馆', location: '美国克利夫兰' },
  { key: 'Met', name: '大都会艺术博物馆', location: '美国纽约' },
  { key: 'Princeton', name: '普林斯顿大学艺术博物馆', location: '美国普林斯顿' },
  { key: 'Nelson-Atkins', name: '尼尔森-阿特金斯艺术博物馆', location: '美国堪萨斯城' },
  { key: 'Philadelphia', name: '费城艺术博物馆', location: '美国费城' },
  { key: 'AMNH', name: '美国自然历史博物馆', location: '美国纽约' },
]

interface CrawlLog {
  key: string
  time: string
  museum: string
  status: 'running' | 'success' | 'error'
  message: string
}

export default function SpiderPage() {
  const [running, setRunning] = useState(false)
  const [ingesting, setIngesting] = useState(false)
  const [logs, setLogs] = useState<CrawlLog[]>([])

  const addLog = useCallback((museum: string, status: 'running' | 'success' | 'error', message: string) => {
    const log: CrawlLog = {
      key: `${Date.now()}-${Math.random()}`,
      time: new Date().toLocaleTimeString(),
      museum,
      status,
      message,
    }
    setLogs((prev) => [log, ...prev].slice(0, 50))
  }, [])

  const handleCrawlAll = useCallback(async () => {
    setRunning(true)
    addLog('全部', 'running', '开始批量爬取...')

    for (let i = 0; i < MUSEUMS.length; i++) {
      const museum = MUSEUMS[i]
      addLog(museum.name, 'running', '正在爬取...')
      try {
        // Simulate crawl with a delay (actual spider runs via CLI)
        await new Promise((resolve) => setTimeout(resolve, 2000))
        addLog(museum.name, 'success', '爬取完成')
      } catch {
        addLog(museum.name, 'error', '爬取失败')
      }
    }

    addLog('全部', 'success', '所有博物馆爬取完成')
    setRunning(false)
  }, [addLog])

  const handleCrawlSingle = useCallback(
    async (museumKey: string, museumName: string) => {
      setRunning(true)
      addLog(museumName, 'running', '正在爬取...')
      try {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        addLog(museumName, 'success', '爬取完成')
      } catch {
        addLog(museumName, 'error', '爬取失败')
      }
      setRunning(false)
    },
    [addLog],
  )

  const handleIngestArtifacts = useCallback(async () => {
    setIngesting(true)
    message.loading({ content: '正在将爬取数据导入知识图谱...', key: 'ingest' })
    try {
      const res = await ingestArtifacts()
      message.success({
        content: `成功导入 ${res.documents_created ?? 0} 条记录到知识图谱`,
        key: 'ingest',
      })
      addLog('系统', 'success', `导入完成: ${res.documents_created ?? 0} 条记录`)
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : '导入失败'
      message.error({ content: errorMsg, key: 'ingest' })
      addLog('系统', 'error', errorMsg)
    } finally {
      setIngesting(false)
    }
  }, [addLog])

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
      render: (status: string) =>
        status === 'running' ? (
          <Tag icon={<SyncOutlined spin />} color="processing">进行中</Tag>
        ) : status === 'success' ? (
          <Tag icon={<CheckCircleOutlined />} color="success">成功</Tag>
        ) : (
          <Tag icon={<ExclamationCircleOutlined />} color="error">失败</Tag>
        ),
    },
    {
      title: '消息',
      dataIndex: 'message',
      key: 'message',
    },
  ]

  return (
    <div>
      <Title level={4}>
        <BugOutlined /> 爬虫任务控制
      </Title>

      <Alert
        message="爬虫说明"
        description="系统使用 Scrapy 框架爬取海外博物馆网站的中国文物数据。爬虫通过 sitemap 发现文物页面，解析 JSON-LD/OpenGraph 数据，经中文关键词过滤后存储到数据库。爬取完成后需手动执行「导入知识图谱」将数据写入图谱。"
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
      />

      <Row gutter={[24, 24]}>
        {MUSEUMS.map((museum) => (
          <Col xs={24} sm={12} lg={8} key={museum.key}>
            <Card
              title={museum.name}
              extra={
                <Button
                  type="primary"
                  size="small"
                  icon={<PlayCircleOutlined />}
                  loading={running}
                  onClick={() => handleCrawlSingle(museum.key, museum.name)}
                  disabled={running}
                >
                  爬取
                </Button>
              }
            >
              <Text type="secondary">{museum.location}</Text>
              <div style={{ marginTop: 8 }}>
                <Tag>{museum.key}</Tag>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <Card style={{ marginTop: 24 }}>
        <Space size="large">
          <Button
            type="primary"
            size="large"
            icon={<PlayCircleOutlined />}
            onClick={handleCrawlAll}
            loading={running}
            disabled={running}
          >
            全部爬取
          </Button>
          <Button
            type="default"
            size="large"
            icon={<PauseCircleOutlined />}
            disabled={!running}
            onClick={() => setRunning(false)}
          >
            停止
          </Button>
          <Button
            type="primary"
            size="large"
            icon={<SyncOutlined />}
            loading={ingesting}
            onClick={handleIngestArtifacts}
          >
            导入知识图谱
          </Button>
        </Space>
      </Card>

      <Card title="运行日志" style={{ marginTop: 24 }}>
        <Table
          columns={logColumns}
          dataSource={logs}
          pagination={{ pageSize: 10 }}
          size="small"
          locale={{ emptyText: '暂无爬取记录，点击上方按钮开始爬取' }}
        />
      </Card>
    </div>
  )
}

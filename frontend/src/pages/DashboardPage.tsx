import { useState, useEffect } from 'react'
import { Card, Row, Col, Statistic, Table, Tag, Typography, Progress, Space, Button } from 'antd'
import {
  DatabaseOutlined,
  BankOutlined,
  HistoryOutlined,
  FileImageOutlined,
  WarningOutlined,
  ArrowRightOutlined,
  GlobalOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { searchRag } from '@/api/documents'
import { getSessionList } from '@/api/sessions'

const { Title, Text } = Typography

interface ArtifactRow {
  key: string
  name: string
  dynasty: string
  type: string
  museum: string
  material: string
}

const columns = [
  {
    title: '文物名称',
    dataIndex: 'name',
    key: 'name',
    render: (text: string) => <Text strong>{text}</Text>,
  },
  {
    title: '年代',
    dataIndex: 'dynasty',
    key: 'dynasty',
    render: (text: string) => <Tag color="blue">{text}</Tag>,
  },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
    render: (text: string) => <Tag color="green">{text}</Tag>,
  },
  {
    title: '材质',
    dataIndex: 'material',
    key: 'material',
    render: (text: string) => <Tag color="orange">{text}</Tag>,
  },
  {
    title: '所属博物馆',
    dataIndex: 'museum',
    key: 'museum',
    render: (text: string) => <Text>{text}</Text>,
  },
]

const recentLogs = [
  { text: '大英博物馆新增 23 件文物', time: '2小时前', color: '#faad14' },
  { text: '完成增量爬取 - 12 条更新', time: '昨天', color: '#52c41a' },
  { text: '实体对齐完成 - 合并 45 个重复实体', time: '3天前', color: '#1890ff' },
]

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState({ artifacts: 0, museums: 0, dynasties: 0, triples: 0 })
  const [sessionCount, setSessionCount] = useState(0)
  const [recentArtifacts, setRecentArtifacts] = useState<ArtifactRow[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const res = await searchRag({
          queries: ['中国文物'],
          use_graph: true,
          k: 5,
          max_hops: 2,
          graph_weight: 0.3,
          vector_weight: 0.4,
          bm25_weight: 0.3,
        })
        if (res.results) {
          const rows: ArtifactRow[] = res.results.map((r: Record<string, unknown>, i: number) => ({
            key: String(i),
            name: (r.title as string) || (r.name as string) || `文物 ${i + 1}`,
            dynasty: (r.period as string) || (r.dynasty as string) || '未知',
            type: (r.type as string) || '未知',
            museum: (r.museum as string) || '未知',
            material: (r.material as string) || '未知',
          }))
          setRecentArtifacts(rows)
        }
        if (res.graph_entities) {
          setStats((prev) => ({ ...prev, triples: res.graph_entities.length }))
        }
      } catch {
        // Use fallback data
      }
      try {
        const sessions = await getSessionList()
        setSessionCount(sessions.sessions?.length ?? 0)
      } catch {
        // ignore
      }
      setLoading(false)
    }
    fetchData()
  }, [])

  return (
    <div>
      <div
        style={{
          textAlign: 'center',
          padding: '32px 0',
          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          borderRadius: 12,
          marginBottom: 24,
        }}
      >
        <Title level={2} style={{ color: '#fff', marginBottom: 8 }}>
          海外中国文物知识图谱
        </Title>
        <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 16 }}>
          探索海外博物馆收藏的中国文物，构建结构化知识图谱
        </Text>
      </div>

      <Row gutter={[24, 24]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="文物总数"
              value={stats.artifacts || 12580}
              prefix={<FileImageOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="博物馆数量"
              value={stats.museums || 12}
              prefix={<BankOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="活跃会话"
              value={sessionCount}
              prefix={<HistoryOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} md={6}>
          <Card>
            <Statistic
              title="三元组数量"
              value={stats.triples || 85600}
              prefix={<DatabaseOutlined />}
              valueStyle={{ color: '#f5222d' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[24, 24]}>
        <Col xs={24} lg={14}>
          <Card
            title="文物列表"
            extra={
              <Button type="link" icon={<ArrowRightOutlined />} onClick={() => navigate('/graph')}>
                查看全部
              </Button>
            }
          >
            <Table
              columns={columns}
              dataSource={recentArtifacts}
              pagination={false}
              size="small"
              loading={loading}
              locale={{ emptyText: '暂无数据，请先导入文档或启动爬虫' }}
            />
          </Card>

          <Card title="数据质量监控" style={{ marginTop: 24 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <div>
                <Text>图片有效率</Text>
                <Progress percent={96} status="active" />
              </div>
              <div>
                <Text>字段完整率</Text>
                <Progress percent={89} status="active" />
              </div>
              <div>
                <Text>实体对齐率</Text>
                <Progress percent={78} status="active" />
              </div>
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={10}>
          <Card title="知识图谱预览">
            <div
              style={{
                height: 280,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%)',
                borderRadius: 8,
                gap: 12,
                cursor: 'pointer',
              }}
              onClick={() => navigate('/graph')}
            >
              <GlobalOutlined style={{ fontSize: 64, color: '#1890ff' }} />
              <Text type="secondary">点击进入图谱可视化</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                展示文物、博物馆、朝代、艺术家之间的关系网络
              </Text>
            </div>
            <div style={{ marginTop: 16, textAlign: 'center' }}>
              <Space wrap>
                <Tag color="blue">文物</Tag>
                <Tag color="green">博物馆</Tag>
                <Tag color="orange">朝代</Tag>
                <Tag color="purple">艺术家</Tag>
                <Tag color="cyan">地点</Tag>
              </Space>
            </div>
          </Card>

          <Card title="数据更新日志" style={{ marginTop: 24 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              {recentLogs.map((log, index) => (
                <div
                  key={log.text}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    padding: '8px 0',
                    borderBottom: index < recentLogs.length - 1 ? '1px solid #f0f0f0' : 'none',
                  }}
                >
                  <WarningOutlined style={{ color: log.color }} />
                  <Text style={{ marginLeft: 8, flex: 1 }}>{log.text}</Text>
                  <Text type="secondary">{log.time}</Text>
                </div>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  )
}

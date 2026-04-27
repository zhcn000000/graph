import { useState } from 'react'
import {
  Layout,
  Menu,
  Input,
  Card,
  Row,
  Col,
  Statistic,
  Table,
  Tag,
  Image,
  Typography,
  Space,
  Button,
  Avatar,
  Breadcrumb,
  Progress
} from 'antd'
import {
  SearchOutlined,
  DatabaseOutlined,
  BankOutlined,
  HistoryOutlined,
  FileImageOutlined,
  TeamOutlined,
  GlobalOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  ArrowRightOutlined,
  WarningOutlined
} from '@ant-design/icons'
import type { MenuProps } from 'antd'
import './App.css'

const { Header, Sider, Content, Footer } = Layout
const { Title, Text } = Typography

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
]

const columns = [
  {
    title: '文物图片',
    dataIndex: 'image',
    key: 'image',
    render: (text: string) => <Image src={text} width={60} height={60} fallback="https://placehold.co/60x60?text=N/A" />
  },
  {
    title: '文物名称',
    dataIndex: 'name',
    key: 'name',
    render: (text: string) => <Text strong>{text}</Text>
  },
  {
    title: '年代',
    dataIndex: 'dynasty',
    key: 'dynasty',
    render: (text: string) => <Tag color="blue">{text}</Tag>
  },
  {
    title: '类型',
    dataIndex: 'type',
    key: 'type',
    render: (text: string) => <Tag color="green">{text}</Tag>
  },
  {
    title: '材质',
    dataIndex: 'material',
    key: 'material',
    render: (text: string) => <Tag color="orange">{text}</Tag>
  },
  {
    title: '所属博物馆',
    dataIndex: 'museum',
    key: 'museum',
    render: (text: string) => <Text>{text}</Text>
  }
]

function App() {
  const [collapsed, setCollapsed] = useState(false)

  const menuItems: MenuProps['items'] = [
    {
      key: 'home',
      icon: <GlobalOutlined />,
      label: '首页',
    },
    {
      key: 'artifacts',
      icon: <FileImageOutlined />,
      label: '文物浏览',
    },
    {
      key: 'graph',
      icon: <DatabaseOutlined />,
      label: '知识图谱',
    },
    {
      key: 'museums',
      icon: <BankOutlined />,
      label: '博物馆',
    },
    {
      key: 'timeline',
      icon: <HistoryOutlined />,
      label: '历史时空',
    },
    {
      key: 'artists',
      icon: <TeamOutlined />,
      label: '艺术家',
    }
  ]

  return (
    <Layout className="app-layout">
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        className="app-sider"
        width={220}
      >
        <div className="logo">
          {collapsed ? (
            <Avatar size={32} style={{ backgroundColor: '#1890ff' }}>KG</Avatar>
          ) : (
            <Space>
              <Avatar size={32} style={{ backgroundColor: '#1890ff' }}>KG</Avatar>
              <Title level={5} style={{ color: '#fff', margin: 0 }}>文物图谱</Title>
            </Space>
          )}
        </div>
        <Menu
          theme="dark"
          mode="inline"
          defaultSelectedKeys={['home']}
          items={menuItems}
        />
      </Sider>

      <Layout>
        <Header className="app-header">
          <Space>
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
              className="collapse-btn"
            />
          </Space>
          <Space size="large">
            <Input
              placeholder="搜索文物、博物馆、艺术家..."
              prefix={<SearchOutlined />}
              className="search-input"
              size="large"
            />
            <Avatar style={{ backgroundColor: '#87d068' }}>用户</Avatar>
          </Space>
        </Header>

        <Content className="app-content">
          <Breadcrumb
            className="breadcrumb"
            items={[{ title: '首页' }]}
          />

          <div className="hero-section">
            <Title level={2}>海外中国文物知识图谱</Title>
            <Text type="secondary" className="hero-subtitle">
              探索海外博物馆收藏的中国文物，构建结构化知识图谱
            </Text>
          </div>

          <Row gutter={[24, 24]} className="stats-row">
            <Col xs={24} sm={12} md={6}>
              <Card>
                <Statistic
                  title="文物总数"
                  value={12580}
                  prefix={<FileImageOutlined />}
                  valueStyle={{ color: '#1890ff' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card>
                <Statistic
                  title="博物馆数量"
                  value={12}
                  prefix={<BankOutlined />}
                  valueStyle={{ color: '#52c41a' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card>
                <Statistic
                  title="涉及朝代"
                  value={28}
                  prefix={<HistoryOutlined />}
                  valueStyle={{ color: '#faad14' }}
                />
              </Card>
            </Col>
            <Col xs={24} sm={12} md={6}>
              <Card>
                <Statistic
                  title="三元组数量"
                  value={85600}
                  prefix={<DatabaseOutlined />}
                  valueStyle={{ color: '#f5222d' }}
                />
              </Card>
            </Col>
          </Row>

          <Row gutter={[24, 24]} className="main-content">
            <Col xs={24} lg={14}>
              <Card
                title="文物列表"
                extra={<Button type="link" icon={<ArrowRightOutlined />}>查看全部</Button>}
                className="artifact-card"
              >
                <Table
                  columns={columns}
                  dataSource={artifactData}
                  pagination={false}
                  size="small"
                />
              </Card>

              <Card title="数据质量监控" className="quality-card">
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
              <Card title="知识图谱预览" className="graph-preview">
                <div className="graph-placeholder">
                  <GlobalOutlined style={{ fontSize: 64, color: '#1890ff' }} />
                  <Text type="secondary">图谱可视化区域</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    展示文物、博物馆、朝代、艺术家之间的关系网络
                  </Text>
                </div>
                <div className="graph-legend">
                  <Space wrap>
                    <Tag color="blue">文物</Tag>
                    <Tag color="green">博物馆</Tag>
                    <Tag color="orange">朝代</Tag>
                    <Tag color="purple">艺术家</Tag>
                    <Tag color="cyan">地点</Tag>
                  </Space>
                </div>
              </Card>

              <Card title="数据更新日志" className="log-card">
                <Space direction="vertical" style={{ width: '100%' }}>
                  <div className="log-item">
                    <WarningOutlined style={{ color: '#faad14' }} />
                    <Text style={{ marginLeft: 8 }}>大英博物馆新增 23 件文物</Text>
                    <Text type="secondary" style={{ marginLeft: 'auto' }}>2小时前</Text>
                  </div>
                  <div className="log-item">
                    <WarningOutlined style={{ color: '#52c41a' }} />
                    <Text style={{ marginLeft: 8 }}>完成增量爬取 - 12 条更新</Text>
                    <Text type="secondary" style={{ marginLeft: 'auto' }}>昨天</Text>
                  </div>
                  <div className="log-item">
                    <WarningOutlined style={{ color: '#1890ff' }} />
                    <Text style={{ marginLeft: 8 }}>实体对齐完成 - 合并 45 个重复实体</Text>
                    <Text type="secondary" style={{ marginLeft: 'auto' }}>3天前</Text>
                  </div>
                </Space>
              </Card>
            </Col>
          </Row>
        </Content>

        <Footer className="app-footer">
          <Text type="secondary">海外中国文物知识图谱构建系统 © 2024</Text>
        </Footer>
      </Layout>
    </Layout>
  )
}

export default App

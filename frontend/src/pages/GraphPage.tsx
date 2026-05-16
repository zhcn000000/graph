import { ApartmentOutlined, NodeIndexOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Empty,
  Input,
  message,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import { useCallback, useEffect, useState } from "react";
import type { GraphEdge, GraphNode } from "@/api/types";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { fetchGraphNeighbors, fetchGraphTraverse, fetchVertexInfo, setSelectedNode } from "@/store/slices/graphSlice";

const { Title, Text } = Typography;

const ENTITY_TYPES = [
  { value: "Artifact", label: "文物", color: "blue" },
  { value: "Museum", label: "博物馆", color: "green" },
  { value: "Dynasty", label: "朝代", color: "orange" },
  { value: "Artist", label: "艺术家", color: "purple" },
  { value: "Location", label: "地点", color: "cyan" },
  { value: "Material", label: "材质", color: "magenta" },
  { value: "ArtifactType", label: "文物类型", color: "red" },
];

const getTypeColor = (label: string) => {
  const found = ENTITY_TYPES.find((t) => label.includes(t.value));
  return found?.color ?? "default";
};

const getTypeLabel = (label: string) => {
  const found = ENTITY_TYPES.find((t) => label.includes(t.value));
  return found?.label ?? label;
};

export default function GraphPage() {
  const dispatch = useAppDispatch();
  const { data, selectedNode, loading, error } = useAppSelector((state) => state.graph);
  const [searchUri, setSearchUri] = useState("");
  const [startNode, setStartNode] = useState("");
  const [maxHops, setMaxHops] = useState(3);
  const [direction, setDirection] = useState("both");
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);

  useEffect(() => {
    if (error) {
      message.error(error);
    }
  }, [error]);

  const handleSearch = useCallback(() => {
    if (!searchUri.trim()) {
      message.warning("请输入实体 URI");
      return;
    }
    dispatch(fetchGraphTraverse({ uri: searchUri.trim(), maxHops, direction }));
    setStartNode(searchUri.trim());
  }, [dispatch, searchUri, maxHops, direction]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      dispatch(setSelectedNode(node.properties ?? null));
      dispatch(fetchVertexInfo(node.id));
    },
    [dispatch],
  );

  const handleNodeDoubleClick = useCallback(
    (node: GraphNode) => {
      dispatch(fetchGraphNeighbors({ uri: node.id, maxHops: 1, direction: "both" }));
    },
    [dispatch],
  );

  const handleNodeHover = useCallback((node: GraphNode | null) => {
    setHoveredNode(node);
  }, []);

  const getEdgeLabel = (edge: GraphEdge) => {
    return edge.relationship?.replace(/_/g, " ") ?? "关联";
  };

  return (
    <div>
      <Title level={4}>
        <ApartmentOutlined /> 知识图谱可视化
      </Title>

      <Card style={{ marginBottom: 24 }}>
        <Space wrap>
          <Input
            placeholder="输入实体 URI，如 cidoc:Artifact/唐代铜镜"
            value={searchUri}
            onChange={(e) => setSearchUri(e.target.value)}
            onPressEnter={handleSearch}
            style={{ width: 360 }}
            prefix={<SearchOutlined />}
            allowClear
          />
          <Select
            value={direction}
            onChange={setDirection}
            style={{ width: 100 }}
            options={[
              { value: "both", label: "双向" },
              { value: "outgoing", label: "出向" },
              { value: "incoming", label: "入向" },
            ]}
          />
          <Select
            value={maxHops}
            onChange={setMaxHops}
            style={{ width: 100 }}
            options={[
              { value: 1, label: "1 跳" },
              { value: 2, label: "2 跳" },
              { value: 3, label: "3 跳" },
              { value: 5, label: "5 跳" },
            ]}
          />
          <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch} loading={loading}>
            查询
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => handleSearch()} disabled={!startNode}>
            刷新
          </Button>
        </Space>
      </Card>

      <Row gutter={[24, 24]}>
        <Col xs={24} lg={16}>
          <Card
            title={
              <Space>
                <NodeIndexOutlined />
                <span>图谱关系图</span>
                <Tag>{data?.nodes?.length ?? 0} 节点</Tag>
                <Tag>{data?.edges?.length ?? 0} 边</Tag>
              </Space>
            }
            styles={{ body: { padding: 0, minHeight: 500 } }}
          >
            {loading ? (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: 500 }}>
                <Spin size="large" tip="加载图谱数据..." />
              </div>
            ) : !data?.nodes?.length ? (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: 500 }}>
                <Empty description="输入实体 URI 并点击查询以加载图谱" />
              </div>
            ) : (
              <div
                style={{
                  width: "100%",
                  height: 500,
                  background: "#fafafa",
                  overflow: "auto",
                  padding: 24,
                  position: "relative",
                }}
              >
                <svg width="100%" height="100%" style={{ minWidth: 800, minHeight: 500 }}>
                  <title>知识图谱可视化</title>
                  {data.edges?.map((edge, i) => {
                    const sourceNode = data.nodes?.find((n) => n.id === edge.source);
                    const targetNode = data.nodes?.find((n) => n.id === edge.target);
                    if (!sourceNode || !targetNode || !data.nodes) return null;
                    const sIdx = data.nodes.indexOf(sourceNode);
                    const tIdx = data.nodes.indexOf(targetNode);
                    const cols = Math.max(1, Math.ceil(Math.sqrt(data.nodes.length)));
                    const sx = `${((sIdx % cols) / cols) * 100}%`;
                    const sy = `${(Math.floor(sIdx / cols) / Math.ceil(data.nodes.length / cols)) * 100}%`;
                    const tx = `${((tIdx % cols) / cols) * 100}%`;
                    const ty = `${(Math.floor(tIdx / cols) / Math.ceil(data.nodes.length / cols)) * 100}%`;
                    return (
                      <line
                        key={`${edge.source}-${edge.target}-${edge.relationship}`}
                        x1={sx}
                        y1={sy}
                        x2={tx}
                        y2={ty}
                        stroke="#ccc"
                        strokeWidth={1}
                      />
                    );
                  })}
                  {data.nodes?.map((node, i) => {
                    if (!data.nodes) return null;
                    const cols = Math.max(1, Math.ceil(Math.sqrt(data.nodes.length)));
                    const x = `${((i % cols) / cols) * 100}%`;
                    const y = `${(Math.floor(i / cols) / Math.ceil(data.nodes.length / cols)) * 100}%`;
                    const nodeColor = getTypeColor(node.label);
                    const nodeLabel = getTypeLabel(node.label);
                    const isSelected = selectedNode && selectedNode === node.properties;
                    const isHovered = hoveredNode?.id === node.id;
                    return (
                      // biome-ignore lint/a11y/useSemanticElements: SVG <g> cannot be replaced with <button>
                      <g
                        key={node.id}
                        transform={`translate(${x}, ${y})`}
                        onClick={() => handleNodeClick(node)}
                        onDoubleClick={() => handleNodeDoubleClick(node)}
                        onMouseEnter={() => handleNodeHover(node)}
                        onMouseLeave={() => handleNodeHover(null)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleNodeClick(node);
                        }}
                        style={{ cursor: "pointer" }}
                      >
                        <circle
                          r={isSelected ? 22 : isHovered ? 18 : 14}
                          fill={nodeColor}
                          stroke={isSelected ? "#000" : isHovered ? "#333" : "#fff"}
                          strokeWidth={isSelected ? 3 : 1}
                        />
                        <text
                          textAnchor="middle"
                          dy={isSelected ? 40 : 28}
                          fontSize={12}
                          fill="#333"
                          style={{ pointerEvents: "none" }}
                        >
                          {(node.properties?.name as string) ?? node.id.split("/").pop() ?? node.id}
                        </text>
                        <Tag
                          color={nodeColor}
                          style={{
                            position: "absolute",
                            transform: "translate(-50%, -50%)",
                            marginTop: -40,
                          }}
                        >
                          {nodeLabel}
                        </Tag>
                      </g>
                    );
                  })}
                </svg>
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title="节点详情">
            {selectedNode ? (
              <Descriptions column={1} size="small" bordered>
                {Object.entries(selectedNode as Record<string, unknown>).map(([key, value]) => (
                  <Descriptions.Item key={key} label={key}>
                    {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : (
              <Empty description="点击节点查看详情" />
            )}
          </Card>

          <Card title="图例" style={{ marginTop: 24 }}>
            <Space direction="vertical">
              {ENTITY_TYPES.map((type) => (
                <Space key={type.value}>
                  <div
                    style={{
                      width: 14,
                      height: 14,
                      borderRadius: "50%",
                      backgroundColor: type.color,
                    }}
                  />
                  <Text>{type.label}</Text>
                </Space>
              ))}
            </Space>
          </Card>

          {data?.edges?.length ? (
            <Card title="最近关系" style={{ marginTop: 24 }}>
              <div style={{ maxHeight: 200, overflow: "auto" }}>
                {data.edges.slice(0, 20).map((edge) => {
                  const srcName = data.nodes?.find((n) => n.id === edge.source)?.properties?.name ?? edge.source;
                  const tgtName = data.nodes?.find((n) => n.id === edge.target)?.properties?.name ?? edge.target;
                  return (
                    <div
                      key={`${edge.source}-${edge.target}-${edge.relationship}`}
                      style={{ padding: "4px 0", borderBottom: "1px solid #f0f0f0", fontSize: 12 }}
                    >
                      <Tag color="blue">{srcName as string}</Tag>
                      <Tag>{getEdgeLabel(edge)}</Tag>
                      <Tag color="green">{tgtName as string}</Tag>
                    </div>
                  );
                })}
              </div>
            </Card>
          ) : null}
        </Col>
      </Row>
    </div>
  );
}

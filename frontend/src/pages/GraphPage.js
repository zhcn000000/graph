import { useState, useEffect, useCallback } from 'react';
import { Card, Row, Col, Input, Button, Space, Tag, Typography, Spin, Descriptions, Select, message, Empty, } from 'antd';
import { SearchOutlined, NodeIndexOutlined, ApartmentOutlined, ReloadOutlined, } from '@ant-design/icons';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { fetchGraphTraverse, fetchGraphNeighbors, fetchVertexInfo, setSelectedNode } from '@/store/slices/graphSlice';
const { Title, Text } = Typography;
const ENTITY_TYPES = [
    { value: 'Artifact', label: '文物', color: 'blue' },
    { value: 'Museum', label: '博物馆', color: 'green' },
    { value: 'Dynasty', label: '朝代', color: 'orange' },
    { value: 'Artist', label: '艺术家', color: 'purple' },
    { value: 'Location', label: '地点', color: 'cyan' },
    { value: 'Material', label: '材质', color: 'magenta' },
    { value: 'ArtifactType', label: '文物类型', color: 'red' },
];
const getTypeColor = (label) => {
    const found = ENTITY_TYPES.find((t) => label.includes(t.value));
    return found?.color ?? 'default';
};
const getTypeLabel = (label) => {
    const found = ENTITY_TYPES.find((t) => label.includes(t.value));
    return found?.label ?? label;
};
export default function GraphPage() {
    const dispatch = useAppDispatch();
    const { data, selectedNode, loading, error } = useAppSelector((state) => state.graph);
    const [searchUri, setSearchUri] = useState('');
    const [startNode, setStartNode] = useState('');
    const [maxHops, setMaxHops] = useState(3);
    const [direction, setDirection] = useState('both');
    const [hoveredNode, setHoveredNode] = useState(null);
    useEffect(() => {
        if (error) {
            message.error(error);
        }
    }, [error]);
    const handleSearch = useCallback(() => {
        if (!searchUri.trim()) {
            message.warning('请输入实体 URI');
            return;
        }
        dispatch(fetchGraphTraverse({ uri: searchUri.trim(), maxHops, direction }));
        setStartNode(searchUri.trim());
    }, [dispatch, searchUri, maxHops, direction]);
    const handleNodeClick = useCallback((node) => {
        dispatch(setSelectedNode(node.properties ?? null));
        dispatch(fetchVertexInfo(node.id));
    }, [dispatch]);
    const handleNodeDoubleClick = useCallback((node) => {
        dispatch(fetchGraphNeighbors({ uri: node.id, maxHops: 1, direction: 'both' }));
    }, [dispatch]);
    const handleNodeHover = useCallback((node) => {
        setHoveredNode(node);
    }, []);
    const getEdgeLabel = (edge) => {
        return edge.relationship?.replace(/_/g, ' ') ?? '关联';
    };
    return (React.createElement("div", null,
        React.createElement(Title, { level: 4 },
            React.createElement(ApartmentOutlined, null),
            " \u77E5\u8BC6\u56FE\u8C31\u53EF\u89C6\u5316"),
        React.createElement(Card, { style: { marginBottom: 24 } },
            React.createElement(Space, { wrap: true },
                React.createElement(Input, { placeholder: "\u8F93\u5165\u5B9E\u4F53 URI\uFF0C\u5982 cidoc:Artifact/\u5510\u4EE3\u94DC\u955C", value: searchUri, onChange: (e) => setSearchUri(e.target.value), onPressEnter: handleSearch, style: { width: 360 }, prefix: React.createElement(SearchOutlined, null), allowClear: true }),
                React.createElement(Select, { value: direction, onChange: setDirection, style: { width: 100 }, options: [
                        { value: 'both', label: '双向' },
                        { value: 'outgoing', label: '出向' },
                        { value: 'incoming', label: '入向' },
                    ] }),
                React.createElement(Select, { value: maxHops, onChange: setMaxHops, style: { width: 100 }, options: [
                        { value: 1, label: '1 跳' },
                        { value: 2, label: '2 跳' },
                        { value: 3, label: '3 跳' },
                        { value: 5, label: '5 跳' },
                    ] }),
                React.createElement(Button, { type: "primary", icon: React.createElement(SearchOutlined, null), onClick: handleSearch, loading: loading }, "\u67E5\u8BE2"),
                React.createElement(Button, { icon: React.createElement(ReloadOutlined, null), onClick: () => handleSearch(), disabled: !startNode }, "\u5237\u65B0"))),
        React.createElement(Row, { gutter: [24, 24] },
            React.createElement(Col, { xs: 24, lg: 16 },
                React.createElement(Card, { title: React.createElement(Space, null,
                        React.createElement(NodeIndexOutlined, null),
                        React.createElement("span", null, "\u56FE\u8C31\u5173\u7CFB\u56FE"),
                        React.createElement(Tag, null,
                            data?.nodes?.length ?? 0,
                            " \u8282\u70B9"),
                        React.createElement(Tag, null,
                            data?.edges?.length ?? 0,
                            " \u8FB9")), styles: { body: { padding: 0, minHeight: 500 } } }, loading ? (React.createElement("div", { style: { display: 'flex', justifyContent: 'center', alignItems: 'center', height: 500 } },
                    React.createElement(Spin, { size: "large", tip: "\u52A0\u8F7D\u56FE\u8C31\u6570\u636E..." }))) : !data || !data.nodes?.length ? (React.createElement("div", { style: { display: 'flex', justifyContent: 'center', alignItems: 'center', height: 500 } },
                    React.createElement(Empty, { description: "\u8F93\u5165\u5B9E\u4F53 URI \u5E76\u70B9\u51FB\u67E5\u8BE2\u4EE5\u52A0\u8F7D\u56FE\u8C31" }))) : (React.createElement("div", { style: {
                        width: '100%',
                        height: 500,
                        background: '#fafafa',
                        overflow: 'auto',
                        padding: 24,
                        position: 'relative',
                    } },
                    React.createElement("svg", { width: "100%", height: "100%", style: { minWidth: 800, minHeight: 500 } },
                        data.edges?.map((edge, i) => {
                            const sourceNode = data.nodes?.find((n) => n.id === edge.source);
                            const targetNode = data.nodes?.find((n) => n.id === edge.target);
                            if (!sourceNode || !targetNode)
                                return null;
                            const sIdx = data.nodes.indexOf(sourceNode);
                            const tIdx = data.nodes.indexOf(targetNode);
                            const cols = Math.max(1, Math.ceil(Math.sqrt(data.nodes.length)));
                            const sx = ((sIdx % cols) / cols) * 100 + '%';
                            const sy = (Math.floor(sIdx / cols) / Math.ceil(data.nodes.length / cols)) * 100 + '%';
                            const tx = ((tIdx % cols) / cols) * 100 + '%';
                            const ty = (Math.floor(tIdx / cols) / Math.ceil(data.nodes.length / cols)) * 100 + '%';
                            return (React.createElement("line", { key: `${edge.source}-${edge.target}-${edge.relationship}`, x1: sx, y1: sy, x2: tx, y2: ty, stroke: "#ccc", strokeWidth: 1 }));
                        }),
                        data.nodes?.map((node, i) => {
                            const cols = Math.max(1, Math.ceil(Math.sqrt(data.nodes.length)));
                            const x = ((i % cols) / cols) * 100 + '%';
                            const y = (Math.floor(i / cols) / Math.ceil(data.nodes.length / cols)) * 100 + '%';
                            const nodeColor = getTypeColor(node.label);
                            const nodeLabel = getTypeLabel(node.label);
                            const isSelected = selectedNode && selectedNode === node.properties;
                            const isHovered = hoveredNode?.id === node.id;
                            return (React.createElement("g", { key: node.id, transform: `translate(${x}, ${y})`, onClick: () => handleNodeClick(node), onDoubleClick: () => handleNodeDoubleClick(node), onMouseEnter: () => handleNodeHover(node), onMouseLeave: () => handleNodeHover(null), style: { cursor: 'pointer' } },
                                React.createElement("circle", { r: isSelected ? 22 : isHovered ? 18 : 14, fill: nodeColor, stroke: isSelected ? '#000' : isHovered ? '#333' : '#fff', strokeWidth: isSelected ? 3 : 1 }),
                                React.createElement("text", { textAnchor: "middle", dy: isSelected ? 40 : 28, fontSize: 12, fill: "#333", style: { pointerEvents: 'none' } }, node.properties?.name ?? node.id.split('/').pop() ?? node.id),
                                React.createElement(Tag, { color: nodeColor, style: {
                                        position: 'absolute',
                                        transform: 'translate(-50%, -50%)',
                                        marginTop: -40,
                                    } }, nodeLabel)));
                        })))))),
            React.createElement(Col, { xs: 24, lg: 8 },
                React.createElement(Card, { title: "\u8282\u70B9\u8BE6\u60C5" }, selectedNode ? (React.createElement(Descriptions, { column: 1, size: "small", bordered: true }, Object.entries(selectedNode).map(([key, value]) => (React.createElement(Descriptions.Item, { key: key, label: key }, typeof value === 'object' ? JSON.stringify(value) : String(value)))))) : (React.createElement(Empty, { description: "\u70B9\u51FB\u8282\u70B9\u67E5\u770B\u8BE6\u60C5" }))),
                React.createElement(Card, { title: "\u56FE\u4F8B", style: { marginTop: 24 } },
                    React.createElement(Space, { direction: "vertical" }, ENTITY_TYPES.map((type) => (React.createElement(Space, { key: type.value },
                        React.createElement("div", { style: {
                                width: 14,
                                height: 14,
                                borderRadius: '50%',
                                backgroundColor: type.color,
                            } }),
                        React.createElement(Text, null, type.label)))))),
                data?.edges?.length ? (React.createElement(Card, { title: "\u6700\u8FD1\u5173\u7CFB", style: { marginTop: 24 } },
                    React.createElement("div", { style: { maxHeight: 200, overflow: 'auto' } }, data.edges.slice(0, 20).map((edge) => {
                        const srcName = data.nodes?.find((n) => n.id === edge.source)?.properties?.name ?? edge.source;
                        const tgtName = data.nodes?.find((n) => n.id === edge.target)?.properties?.name ?? edge.target;
                        return (React.createElement("div", { key: `${edge.source}-${edge.target}-${edge.relationship}`, style: { padding: '4px 0', borderBottom: '1px solid #f0f0f0', fontSize: 12 } },
                            React.createElement(Tag, { color: "blue" }, srcName),
                            React.createElement(Tag, null, getEdgeLabel(edge)),
                            React.createElement(Tag, { color: "green" }, tgtName)));
                    })))) : null))));
}

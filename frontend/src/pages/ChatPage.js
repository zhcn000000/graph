import { AppstoreAddOutlined, BulbOutlined, CloudUploadOutlined, InboxOutlined, PaperClipOutlined, ToolOutlined, } from '@ant-design/icons';
import { Actions, Attachments, Bubble, Conversations, FileCard, Sender, Think, ThoughtChain, } from '@ant-design/x';
import { useXChat, useXConversations } from '@ant-design/x-sdk';
import styled from '@emotion/styled';
import { Alert, Checkbox, Flex, Input, Modal, message, Tooltip } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createChatProvider, generateSessionTitle, getHistoryMessages, transcribeAudio, } from '@/api/chat';
import { createSession, deleteSession, getSessionList, renameSession } from '@/api/session';
import { SuperMarkdown } from '@/components/SuperMarkdown';
const MAX_UPLOAD_SIZE = 10 * 1024 * 1024;
const defaultTypingConfig = {
    effect: 'typing',
    step: 2,
    interval: 80,
    keepPrefix: true,
};
const availableTools = [
    { value: 'rag_toolkit', label: '调用知识库', description: '用于检索增强生成的工具' },
    { value: 'code_toolkit', label: '在容器中执行代码', description: '用于安全的执行代码以计算的工具' },
    { value: 'web_toolkit', label: '搜索网页', description: '用于实时获取互联网信息的工具' },
];
const createAttachmentId = (prefix = 'att') => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
const fileToDataUri = (file) => {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('文件读取失败'));
        reader.readAsDataURL(file);
    });
};
const resolveFileType = (url) => {
    if (url?.startsWith('data:image'))
        return 'image';
    if (url?.startsWith('data:audio'))
        return 'audio';
    if (url?.startsWith('data:video'))
        return 'video';
    const ext = url?.split('?')[0].split('#')[0].split('/').slice(-1)[0].split('.').slice(-1)[0].toLowerCase();
    if (ext && ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext))
        return 'image';
    if (ext && ['mp3', 'wav', 'aac', 'flac', 'ogg'].includes(ext))
        return 'audio';
    if (ext && ['mp4', 'webm', 'mov', 'mkv'].includes(ext))
        return 'video';
    return 'file';
};
export default function ChatPage() {
    const [attachments, setAttachments] = useState([]);
    const [senderValue, setSenderValue] = useState('');
    const [selectedTools, setSelectedTools] = useState([]);
    const [toolVisible, setToolVisible] = useState(false);
    const [attachmentVisible, setAttachmentVisible] = useState(false);
    const [isDeepThinking, setIsDeepThinking] = useState(true);
    const [error, setError] = useState(null);
    const [speechRecording, setSpeechRecording] = useState(false);
    const [isTranscribingSpeech, setIsTranscribingSpeech] = useState(false);
    const mediaRecorderRef = useRef(null);
    const mediaStreamRef = useRef(null);
    const speechChunksRef = useRef([]);
    const [chatProvider] = useState(() => createChatProvider());
    const messagesRef = useRef([]);
    const conversationManager = useXConversations({
        defaultConversations: [],
        defaultActiveConversationKey: '',
    });
    const conversations = useMemo(() => conversationManager.conversations, [conversationManager.conversations]);
    const activeConversationKey = conversationManager.activeConversationKey;
    const { addConversation, removeConversation, setActiveConversationKey, setConversation, setConversations } = conversationManager;
    const { messages: messageInfos, onRequest, abort, isRequesting, isDefaultMessagesRequesting, } = useXChat({
        provider: chatProvider,
        conversationKey: activeConversationKey || undefined,
        defaultMessages: async (info) => {
            const conversationKey = info.conversationKey;
            if (!conversationKey)
                return [];
            try {
                setError(null);
                return await getHistoryMessages({ sessionId: String(conversationKey) });
            }
            catch (err) {
                const nextError = err instanceof Error ? err : new Error('获取历史记录失败');
                setError(nextError);
                message.error('获取历史记录失败');
                return [];
            }
        },
        requestPlaceholder: { role: 'assistant', content: [] },
    });
    const hasMessages = messageInfos.length > 0;
    const hasUploadingAttachments = attachments.some((item) => item.status === 'uploading');
    const listRef = useRef(null);
    useEffect(() => {
        messagesRef.current = messageInfos;
    }, [messageInfos]);
    const refreshSessionList = useCallback(async () => {
        try {
            const response = await getSessionList();
            const sessions = response?.sessions ?? [];
            const list = sessions.map((session) => ({
                key: session.session_id,
                label: session.name,
                isAutoTitle: false,
            }));
            setConversations(list);
            if (list.length === 0) {
                await createNewConversation();
                return;
            }
            if (!activeConversationKey) {
                setActiveConversationKey(list[0].key);
            }
        }
        catch {
            await createNewConversation();
        }
    }, []);
    const createNewConversation = useCallback(async () => {
        const defaultName = `新会话-${Date.now().toString().slice(-4)}`;
        try {
            const res = await createSession({ name: defaultName });
            if (!res?.session_id)
                throw new Error('创建会话失败');
            const sessionId = res.session_id;
            addConversation({ key: sessionId, label: res.name || defaultName, isAutoTitle: true }, 'prepend');
            setActiveConversationKey(sessionId);
            message.success('已开启新会话');
        }
        catch {
            message.error('创建会话失败，请稍后重试');
        }
    }, [addConversation, setActiveConversationKey]);
    useEffect(() => {
        void refreshSessionList();
    }, []);
    const updateConversationTitleFromMessage = useCallback(async (messageText) => {
        if (!activeConversationKey)
            return;
        const target = conversations.find((item) => item.key === activeConversationKey);
        if (!target?.isAutoTitle)
            return;
        const normalized = messageText.replace(/\s+/g, ' ').trim();
        if (!normalized)
            return;
        try {
            const response = await generateSessionTitle({ text: normalized });
            if (!response?.success || !response.title?.trim())
                return;
            const generatedTitle = response.title.trim();
            await renameSession(activeConversationKey, { name: generatedTitle });
            setConversation(activeConversationKey, { ...target, label: generatedTitle, isAutoTitle: false });
        }
        catch {
            // ignore
        }
    }, [activeConversationKey, conversations, setConversation]);
    const handleConversationSelect = useCallback((value) => {
        if (!value || value === activeConversationKey)
            return;
        if (isRequesting) {
            message.warning('请先终止当前回答，再切换会话。');
            return;
        }
        setActiveConversationKey(value);
        setError(null);
        setAttachments([]);
    }, [activeConversationKey, isRequesting, setActiveConversationKey]);
    const handleConversationMenuCommand = useCallback(async (command, item) => {
        if (!item?.key)
            return;
        if (command === 'rename') {
            const newName = await new Promise((resolve) => {
                let value = item.label;
                Modal.confirm({
                    title: '重命名会话',
                    content: React.createElement(Input, { defaultValue: item.label, autoFocus: true, onChange: (e) => { value = e.target.value; } }),
                    okText: '确定',
                    cancelText: '取消',
                    onOk: async () => {
                        if (!value.trim()) {
                            message.warning('会话名称不能为空');
                            throw new Error('invalid');
                        }
                        resolve(value.trim());
                    },
                    onCancel: () => resolve(null),
                });
            });
            if (!newName)
                return;
            try {
                await renameSession(item.key, { name: newName });
                setConversation(item.key, { ...item, label: newName, isAutoTitle: false });
                message.success('会话重命名成功');
            }
            catch {
                message.error('重命名会话失败');
            }
            return;
        }
        if (command === 'delete') {
            Modal.confirm({
                title: '删除确认',
                content: '确定删除当前会话吗？',
                okText: '删除',
                cancelText: '取消',
                onOk: async () => {
                    try {
                        await deleteSession(item.key);
                        removeConversation(item.key);
                        if (activeConversationKey === item.key) {
                            const fallback = conversations.find((c) => c.key !== item.key);
                            if (fallback)
                                setActiveConversationKey(fallback.key);
                            else
                                await createNewConversation();
                        }
                        message.success('会话已删除');
                    }
                    catch {
                        message.error('删除会话失败');
                    }
                },
            });
        }
    }, [activeConversationKey, conversations, createNewConversation, removeConversation, setActiveConversationKey, setConversation]);
    const conversationMenu = useCallback((item) => ({
        items: [{ key: 'rename', label: '重命名' }, { key: 'delete', label: '删除' }],
        onClick: (info) => {
            const target = conversations.find((c) => c.key === item.key);
            if (target)
                void handleConversationMenuCommand(String(info.key), target);
        },
    }), [conversations, handleConversationMenuCommand]);
    const handleSubmit = useCallback(async () => {
        if (!senderValue.trim() || isRequesting)
            return;
        if (hasUploadingAttachments) {
            message.warning('文件上传中，请稍后发送');
            return;
        }
        if (!activeConversationKey) {
            message.warning('缺少会话信息，无法发送消息');
            return;
        }
        const fileItems = attachments
            .filter((item) => item.url && item.name)
            .map((item) => ({
            part: 'file',
            name: item.name ?? '文件',
            url: item.url,
        }));
        setError(null);
        listRef.current?.scrollTo({ top: 'bottom' });
        const messageText = senderValue;
        setSenderValue('');
        setAttachments([]);
        await updateConversationTitleFromMessage(messageText);
        onRequest({
            model: 'deepseek-v4-flash',
            thinking: isDeepThinking,
            sessionId: activeConversationKey,
            text: messageText,
            files: fileItems,
            tools: selectedTools,
        });
    }, [
        activeConversationKey, attachments, hasUploadingAttachments, isDeepThinking,
        isRequesting, selectedTools, senderValue, onRequest, updateConversationTitleFromMessage,
    ]);
    const handleCancel = useCallback(() => {
        if (!isRequesting)
            return;
        abort();
        message.info('已终止生成');
    }, [abort, isRequesting]);
    const handleAttachmentUpload = async (options) => {
        const { file, onSuccess, onError } = options;
        if (!(file instanceof File)) {
            onError?.(new Error('文件格式错误'));
            return;
        }
        const uid = createAttachmentId('upload');
        const uploadItem = { uid, name: file.name, status: 'uploading', originFileObj: file };
        setAttachments((prev) => [...prev, uploadItem]);
        try {
            const dataUri = await fileToDataUri(file);
            setAttachments((prev) => prev.map((item) => (item.uid === uid ? { ...item, status: 'done', url: dataUri } : item)));
            onSuccess?.({ success: true }, file);
            message.success(`文件 ${file.name} 上传成功`);
        }
        catch (error) {
            setAttachments((prev) => prev.filter((item) => item.uid !== uid));
            const err = error instanceof Error ? error : new Error(String(error || ''));
            onError?.(err);
            message.error(err.message || '文件上传失败');
        }
    };
    const handleSpeechRecordingChange = useCallback(async (nextRecording) => {
        if (nextRecording) {
            if (!('mediaDevices' in navigator) || !navigator.mediaDevices.getUserMedia) {
                message.error('当前浏览器不支持录音');
                setSpeechRecording(false);
                return;
            }
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const recorder = new MediaRecorder(stream);
                mediaStreamRef.current = stream;
                mediaRecorderRef.current = recorder;
                speechChunksRef.current = [];
                recorder.ondataavailable = (event) => {
                    if (event.data.size > 0)
                        speechChunksRef.current.push(event.data);
                };
                recorder.onstop = () => {
                    const chunks = speechChunksRef.current;
                    speechChunksRef.current = [];
                    setSpeechRecording(false);
                    mediaRecorderRef.current = null;
                    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
                    mediaStreamRef.current = null;
                    if (!chunks.length)
                        return;
                    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
                    if (blob.size === 0)
                        return;
                    void (async () => {
                        setIsTranscribingSpeech(true);
                        try {
                            const response = await transcribeAudio(blob, `recording-${Date.now()}.webm`);
                            if (!response.success)
                                throw new Error(response.status || '语音转写失败');
                            const text = response.text?.trim();
                            if (!text)
                                return;
                            setSenderValue((prev) => (prev ? `${prev.trimEnd()}\n${text}` : text));
                            message.success('语音识别成功');
                        }
                        catch (err) {
                            message.error(err instanceof Error ? err.message : '语音转写失败');
                        }
                        finally {
                            setIsTranscribingSpeech(false);
                        }
                    })();
                };
                recorder.start();
                setSpeechRecording(true);
            }
            catch {
                setSpeechRecording(false);
                message.error('无法开始录音，请检查麦克风权限');
            }
            return;
        }
        const recorder = mediaRecorderRef.current;
        if (recorder && recorder.state !== 'inactive') {
            recorder.stop();
        }
        else {
            setSpeechRecording(false);
        }
    }, []);
    const bubbleItems = useMemo(() => {
        const renderContentItems = (contentItems) => {
            if (!contentItems?.length)
                return { nodes: null, copyText: '' };
            const nodes = [];
            let copyText = '';
            let index = 0;
            while (index < contentItems.length) {
                const current = contentItems[index];
                if (current.part === 'text') {
                    let mergedText = current.content ?? '';
                    let nextIndex = index + 1;
                    while (nextIndex < contentItems.length && contentItems[nextIndex].part === 'text') {
                        mergedText += contentItems[nextIndex].content ?? '';
                        nextIndex += 1;
                    }
                    nodes.push(React.createElement(SuperMarkdown, { key: `text-${index}`, streaming: { hasNextChunk: current.status !== 'success' } }, mergedText));
                    copyText += mergedText;
                    index = nextIndex;
                    continue;
                }
                if (current.part === 'reasoning') {
                    let mergedReasoning = current.reasoning ?? '';
                    let nextIndex = index + 1;
                    while (nextIndex < contentItems.length && contentItems[nextIndex].part === 'reasoning') {
                        mergedReasoning += contentItems[nextIndex].reasoning ?? '';
                        nextIndex += 1;
                    }
                    nodes.push(React.createElement(Think, { key: `reasoning-${index}`, title: "\u6DF1\u5EA6\u601D\u8003", defaultExpanded: current.status !== 'success' }, mergedReasoning));
                    index = nextIndex;
                    continue;
                }
                if (current.part === 'file') {
                    const fileItems = [];
                    let nextIndex = index;
                    while (nextIndex < contentItems.length && contentItems[nextIndex].part === 'file') {
                        const file = contentItems[nextIndex];
                        if (file.part === 'file') {
                            fileItems.push({
                                name: file.name ?? '文件',
                                src: file.url,
                                type: resolveFileType(file.url),
                            });
                        }
                        nextIndex += 1;
                    }
                    if (fileItems.length)
                        nodes.push(React.createElement(FileCard.List, { key: `file-${index}`, items: fileItems }));
                    index = nextIndex;
                    continue;
                }
                if (current.part === 'tool') {
                    const toolItems = [];
                    let nextIndex = index;
                    while (nextIndex < contentItems.length && contentItems[nextIndex].part === 'tool') {
                        toolItems.push(contentItems[nextIndex]);
                        nextIndex += 1;
                    }
                    if (toolItems.length) {
                        const thoughtItems = toolItems.map((tool) => ({
                            title: tool.name,
                            content: (React.createElement(Flex, null,
                                tool.args ? (React.createElement(ThoughtChain.Item, { variant: "solid", title: "\u8C03\u7528\u5DE5\u5177", description: typeof tool.args === 'string' ? tool.args : JSON.stringify(tool.args) })) : null,
                                tool.result ? (React.createElement(ThoughtChain.Item, { variant: "solid", title: "\u5DE5\u5177\u7ED3\u679C", description: typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result) })) : null)),
                            collapsible: true,
                            status: tool.status,
                        }));
                        nodes.push(React.createElement(ThoughtChain, { key: `tool-${index}`, items: thoughtItems }));
                    }
                    index = nextIndex;
                    continue;
                }
                index += 1;
            }
            return { nodes, copyText };
        };
        return messageInfos.map((info) => {
            const item = info.message;
            const { nodes, copyText } = renderContentItems(item.content);
            const actionsItems = [
                { key: 'copy', actionRender: React.createElement(Actions.Copy, { text: copyText }) },
            ];
            return {
                key: String(info.id),
                role: item.role,
                status: info.status,
                loading: info.status === 'loading',
                content: (React.createElement(MessageContent, null,
                    nodes,
                    React.createElement(Actions, { items: actionsItems }))),
                streaming: info.status === 'updating',
                typing: item.role === 'assistant' && info.status === 'updating' ? defaultTypingConfig : false,
            };
        });
    }, [messageInfos]);
    const conversationItems = useMemo(() => conversations.map((item) => ({ key: item.key, label: item.label })), [conversations]);
    return (React.createElement(ChatWrap, null,
        React.createElement(ChatLayout, null,
            React.createElement(Sidebar, null, React.createElement(Conversations, { items: conversationItems, activeKey: activeConversationKey ?? undefined, onActiveChange: handleConversationSelect, menu: conversationMenu, creation: {
                    label: '创建新会话',
                    icon: React.createElement(AppstoreAddOutlined, null),
                    onClick: createNewConversation,
                } })),
            React.createElement(Main, null,
                error ? React.createElement(Alert, { type: "error", title: error.message, closable: true, style: { marginBottom: 8 } }) : null,
                isDefaultMessagesRequesting ? (React.createElement(Alert, { type: "info", title: "\u5386\u53F2\u8BB0\u5F55\u52A0\u8F7D\u4E2D...", showIcon: true, style: { marginBottom: 8 } })) : null,
                React.createElement(ChatContent, null,
                    React.createElement(Bubble.List, { ref: listRef, items: bubbleItems, autoScroll: true, role: {
                            user: { placement: 'end', variant: 'filled' },
                            assistant: { placement: 'start', variant: 'outlined' },
                        } })),
                React.createElement(Sender, { value: senderValue, onChange: (value) => setSenderValue(value), onSubmit: handleSubmit, onCancel: handleCancel, loading: isRequesting, allowSpeech: {
                        recording: speechRecording,
                        onRecordingChange: handleSpeechRecordingChange,
                    }, autoSize: { minRows: 1, maxRows: 10 }, placeholder: "\u8BF7\u8F93\u5165\u95EE\u9898... (\u53EF\u76F4\u63A5\u7C98\u8D34\u6587\u4EF6)", submitType: "enter", header: React.createElement(SenderTop, null,
                        React.createElement(Sender.Header, { title: "\u9644\u4EF6\u4E0A\u4F20", open: attachmentVisible, onOpenChange: setAttachmentVisible },
                            React.createElement(AttachmentPanel, null, React.createElement(Attachments, { items: attachments, multiple: true, maxCount: 8, customRequest: handleAttachmentUpload, onRemove: (file) => setAttachments((prev) => prev.filter((item) => item.uid !== file.uid)), overflow: "wrap", placeholder: (type) => type === 'drop'
                                    ? { icon: React.createElement(InboxOutlined, null), title: '拖拽文件到此处上传', description: '单个文件不超过10MB' }
                                    : { icon: React.createElement(CloudUploadOutlined, null), title: '在此处上传文件', description: '单个文件不超过10MB' } }))),
                        React.createElement(Sender.Header, { title: "\u5DE5\u5177\u9009\u62E9", open: toolVisible, onOpenChange: setToolVisible },
                            React.createElement(ToolSelector, null,
                                React.createElement(Checkbox, { indeterminate: selectedTools.length > 0 && selectedTools.length < availableTools.length, checked: selectedTools.length === availableTools.length, onChange: (e) => {
                                        if (e.target.checked)
                                            setSelectedTools(availableTools.map((t) => t.value));
                                        else
                                            setSelectedTools([]);
                                    }, style: { marginBottom: 8 } }, "\u5168\u9009/\u5168\u4E0D\u9009"),
                                React.createElement(Checkbox.Group, { value: selectedTools, onChange: (values) => setSelectedTools(values) },
                                    React.createElement(Flex, { wrap: "wrap", gap: "8px", style: { width: '100%' } }, availableTools.map((tool) => (React.createElement(ToolOptionRow, { key: tool.value },
                                        React.createElement(Checkbox, { value: tool.value, disabled: isRequesting },
                                            React.createElement(ToolLabel, null, tool.label),
                                            React.createElement(ToolDesc, null, tool.description)))))))))), prefix: React.createElement(SenderPrefix, null,
                        React.createElement(Tooltip, { title: "\u9644\u4EF6\u4E0A\u4F20" },
                            React.createElement(Sender.Switch, { icon: React.createElement(PaperClipOutlined, null), value: attachmentVisible, onChange: setAttachmentVisible, disabled: isRequesting })),
                        React.createElement(Tooltip, { title: "\u5DE5\u5177\u9009\u62E9" },
                            React.createElement(Sender.Switch, { icon: React.createElement(ToolOutlined, null), value: toolVisible, onChange: setToolVisible, disabled: isRequesting })),
                        React.createElement(Tooltip, { title: "\u6DF1\u5EA6\u601D\u8003" },
                            React.createElement(Sender.Switch, { icon: React.createElement(BulbOutlined, null), value: isDeepThinking, onChange: setIsDeepThinking }))) })))));
}
const ChatWrap = styled('div')({
    height: 'calc(100vh - 160px)',
    padding: '0 16px 16px',
});
const ChatLayout = styled('div')({
    height: '100%',
    display: 'flex',
    gap: '16px',
    overflow: 'hidden',
});
const Sidebar = styled('aside')({
    flex: '0 0 280px',
    minWidth: '240px',
    display: 'flex',
    flexDirection: 'column',
});
const Main = styled('section')({
    flex: '1',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    overflow: 'hidden',
});
const ChatContent = styled('div')({
    flex: '1',
    minHeight: '0',
    display: 'flex',
    flexDirection: 'column',
});
const MessageContent = styled('div')({
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
});
const SenderPrefix = styled('div')({
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
});
const SenderTop = styled('div')({
    display: 'flex',
});
const ToolSelector = styled('div')({
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    width: '420px',
});
const ToolOptionRow = styled('div')({
    padding: '6px 8px',
    borderRadius: '6px',
    '&:hover': { background: 'var(--bg-hover)' },
    width: 'calc(50% - 4px)',
});
const ToolLabel = styled('div')({
    fontSize: '13px',
    fontWeight: '600',
});
const ToolDesc = styled('div')({
    fontSize: '12px',
    color: 'var(--font-secondary)',
});
const AttachmentPanel = styled('div')({
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    width: '360px',
});

import {
  AppstoreAddOutlined,
  BulbOutlined,
  CloudUploadOutlined,
  CodeOutlined,
  CommentOutlined,
  InboxOutlined,
  PaperClipOutlined,
  PlusOutlined,
  RobotOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import {
  Actions,
  ActionsFeedbackProps,
  Attachments,
  Bubble,
  Conversations,
  FileCard,
  FileCardProps,
  Prompts,
  Sender,
  Think,
  ThoughtChain,
  ThoughtChainItemType,
} from "@ant-design/x";
import { ItemType } from "@ant-design/x/es/actions/interface";
import { BubbleListRef } from "@ant-design/x/es/bubble";
import { SenderRef } from "@ant-design/x/es/sender";
import { useXChat, useXConversations } from "@ant-design/x-sdk";
import styled from "@emotion/styled";
import type { MenuProps, UploadFile, UploadProps } from "antd";
import { Alert, Button, Card, Checkbox, Flex, Input, Modal, message, Tooltip, Upload } from "antd";
import React, { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  type ChatMessage,
  type ChatMessageInfo,
  type ContentItem,
  createChatProvider,
  type FileItem,
  generateSessionTitle,
  getHistoryMessages,
  type StreamChatParams,
  type ToolItem,
  type ToolType,
  transcribeAudio,
} from "@/api/chat";
import { createChecklist } from "@/api/checklist";
import { resolveProjectName } from "@/api/idnameutil";
import { listChatPrompts } from "@/api/prompt";
import { createSession, deleteSession, getSessionList, renameSession } from "@/api/session";
import { SuperMarkdown } from "@/components/SuperMarkdown";

type PromptItemMeta = {
  text?: string;
  html?: string;
};

interface PromptItem {
  key: string;
  label: string;
  description?: string;
  disabled?: boolean;
  highlight?: boolean;
  meta?: PromptItemMeta;
}

type ConversationItem = {
  key: string;
  label: string;
  isAutoTitle?: boolean;
};

type ToolOption = {
  value: ToolType;
  label: string;
  description: string;
};

const MAX_UPLOAD_SIZE = 10 * 1024 * 1024;

const defaultTypingConfig = {
  effect: "typing" as const,
  step: 2,
  interval: 80,
  keepPrefix: true,
};

const availableTools: ToolOption[] = [
  {
    value: "rag_toolkit",
    label: "调用知识库",
    description: "用于检索增强生成的工具",
  },
  {
    value: "sql_toolkit",
    label: "调用数据表格",
    description: "用于数据库查询和分析的工具",
  },
  {
    value: "code_toolkit",
    label: "在容器中执行代码",
    description: "用于安全的执行代码以计算的工具",
  },
  {
    value: "web_toolkit",
    label: "搜索网页",
    description: "用于实时获取互联网信息的工具",
  },
];

const createAttachmentId = (prefix = "att"): string =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

const fileToDataUri = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(reader.result as string);
    };
    reader.onerror = () => {
      reject(new Error("文件读取失败"));
    };
    reader.readAsDataURL(file);
  });
};

const resolveFileType = (url?: string): "image" | "audio" | "video" | "file" => {
  if (url?.startsWith("data:image")) return "image";
  if (url?.startsWith("data:audio")) return "audio";
  if (url?.startsWith("data:video")) return "video";
  const ext = url?.split("?")[0].split("#")[0].split("/").slice(-1)[0].split(".").slice(-1)[0].toLowerCase();
  if (ext && ["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"].includes(ext)) return "image";
  if (ext && ["mp3", "wav", "aac", "flac", "ogg"].includes(ext)) return "audio";
  if (ext && ["mp4", "webm", "mov", "mkv"].includes(ext)) return "video";
  return "file";
};

const LLMChat = () => {
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("projectId") ?? "";
  const [projectName, setProjectName] = useState(searchParams.get("projectName") ?? (projectId || "未知项目"));

  const [attachments, setAttachments] = useState<UploadFile[]>([]);
  const [senderValue, setSenderValue] = useState("");
  const [selectedTools, setSelectedTools] = useState<ToolType[]>([]);
  const [toolVisible, setToolVisible] = useState(false);
  const [attachmentVisible, setAttachmentVisible] = useState(false);
  const [activePromptKey, setActivePromptKey] = useState("");
  const [lastSelectedPromptLabel, setLastSelectedPromptLabel] = useState("");
  const [isSessionListLoading, setIsSessionListLoading] = useState(false);
  const [isDeepThinking, setIsDeepThinking] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [chatPrompts, setChatPrompts] = useState<PromptItem[]>([]);
  const [speechRecording, setSpeechRecording] = useState(false);
  const [isTranscribingSpeech, setIsTranscribingSpeech] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState<ActionsFeedbackProps["value"]>("default");
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const speechChunksRef = useRef<BlobPart[]>([]);
  const senderRef = useRef<SenderRef>(null);
  const [chatProvider] = useState(() => createChatProvider());
  const messagesRef = useRef<ChatMessageInfo[]>([]);
  const conversationsRef = useRef<ConversationItem[]>([]);
  const conversationManager = useXConversations({
    defaultConversations: [],
    defaultActiveConversationKey: "",
  });
  const conversations = useMemo(
    () => conversationManager.conversations as ConversationItem[],
    [conversationManager.conversations],
  );
  const activeConversationKey = conversationManager.activeConversationKey;
  const { addConversation, removeConversation, setActiveConversationKey, setConversation, setConversations } =
    conversationManager;
  const {
    messages: messageInfos,
    onRequest,
    abort,
    isRequesting,
    isDefaultMessagesRequesting,
  } = useXChat<ChatMessage, ChatMessage, StreamChatParams>({
    provider: chatProvider,
    conversationKey: activeConversationKey || undefined,
    defaultMessages: async (info: { conversationKey?: string }) => {
      const conversationKey = info.conversationKey;
      if (!projectId || !conversationKey) {
        return [];
      }

      try {
        setError(null);
        return await getHistoryMessages({
          projectId,
          sessionId: String(conversationKey),
        });
      } catch (err) {
        console.error("获取历史记录失败", err);
        const nextError = err instanceof Error ? err : new Error("获取历史记录失败");
        setError(nextError);
        message.error("获取历史记录失败");
        return [];
      }
    },
    requestPlaceholder: {
      role: "assistant",
      content: [],
    },
  });

  const activeConversationKeyRef = useRef("");

  const hasMessages = messageInfos.length > 0;
  const hasUploadingAttachments = attachments.some((item) => item.status === "uploading");
  const listRef = useRef<BubbleListRef>(null);

  useEffect(() => {
    messagesRef.current = messageInfos;
  }, [messageInfos]);

  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  useEffect(() => {
    activeConversationKeyRef.current = activeConversationKey;
  }, [activeConversationKey]);

  const updateConversationTitleFromMessage = useCallback(
    async (messageText: string) => {
      if (!activeConversationKey) return;
      const target = conversations.find((item) => item.key === activeConversationKey);
      if (!target?.isAutoTitle) return;
      const normalized = messageText.replace(/\s+/g, " ").trim();
      if (!normalized) return;
      let generatedTitle = "";

      try {
        const response = await generateSessionTitle({ text: normalized });
        if (!response?.success || !response.title?.trim()) {
          throw new Error("生成标题失败");
        }
        generatedTitle = response.title.trim();
        await renameSession(projectId, activeConversationKey, {
          name: generatedTitle,
        });
      } catch (renameError) {
        console.error("重命名会话失败", renameError);
        return;
      }

      setConversation(activeConversationKey, {
        ...target,
        label: generatedTitle,
        isAutoTitle: false,
      });
    },
    [activeConversationKey, conversations, projectId, setConversation],
  );

  useEffect(() => {
    if (!projectId || searchParams.get("projectName")) return;
    let isMounted = true;
    resolveProjectName(projectId)
      .then((names) => {
        if (isMounted && names[0]) {
          setProjectName(names[0]);
        }
      })
      .catch((err) => {
        console.warn("获取项目名称失败", err);
      });
    return () => {
      isMounted = false;
    };
  }, [projectId, searchParams]);

  const createNewConversation = useCallback(async () => {
    if (!projectId) {
      message.warning("缺少项目 ID，无法创建会话");
      return;
    }
    if (messagesRef.current.length === 0 && conversationsRef.current.length > 0) {
      message.info("当前会话无消息记录，无需创建新会话");
      return;
    }
    const defaultName = `新会话-${Date.now().toString().slice(-4)}`;
    try {
      const res = await createSession(projectId, { name: defaultName });
      if (!res?.session_id) {
        throw new Error("创建会话失败");
      }
      const sessionId = res.session_id;
      addConversation(
        {
          key: sessionId,
          label: res.name || defaultName,
          isAutoTitle: true,
        },
        "prepend",
      );
      setActiveConversationKey(sessionId);
      message.success("已开启新会话");
    } catch (err) {
      console.error("创建会话失败", err);
      message.error("创建会话失败，请稍后重试");
    }
  }, [addConversation, projectId, setActiveConversationKey]);

  const refreshSessionList = useCallback(async () => {
    if (!projectId) return;
    setIsSessionListLoading(true);
    try {
      const response = await getSessionList(projectId);
      const sessions = response?.sessions ?? [];
      const list: ConversationItem[] = sessions.map((session) => ({
        key: session.session_id,
        label: session.name,
        isAutoTitle: false,
      }));
      setConversations(list);
      if (list.length === 0) {
        await createNewConversation();
        return;
      }
      if (!activeConversationKeyRef.current) {
        setActiveConversationKey(list[0].key);
      }
    } catch (err) {
      console.error("获取会话列表失败", err);
      message.error("获取会话列表失败，将开启新会话");
      await createNewConversation();
    } finally {
      setIsSessionListLoading(false);
    }
  }, [createNewConversation, projectId, setActiveConversationKey, setConversations]);

  useEffect(() => {
    void refreshSessionList();
  }, [refreshSessionList]);

  useEffect(() => {
    const fetchChatPrompts = async () => {
      try {
        const response = await listChatPrompts();
        if (response.success && response.data) {
          const prompts: PromptItem[] = response.data.map((item) => ({
            key: item.id,
            label: item.prompt_name,
            description: item.prompt_description,
            meta: {
              text: item.prompt_content,
            },
          }));
          setChatPrompts(prompts);
        }
      } catch (err) {
        console.error("获取提示词列表失败", err);
      }
    };
    void fetchChatPrompts();
  }, []);

  const promptRenameConversation = useCallback((currentLabel: string) => {
    return new Promise<string | null>((resolve) => {
      let value = currentLabel;
      const modal = Modal.confirm({
        title: "重命名会话",
        content: (
          <Input
            defaultValue={currentLabel}
            autoFocus
            onChange={(event) => {
              value = event.target.value;
            }}
          />
        ),
        okText: "确定",
        cancelText: "取消",
        onOk: async () => {
          if (!value.trim()) {
            message.warning("会话名称不能为空");
            throw new Error("invalid");
          }
          resolve(value.trim());
        },
        onCancel: () => resolve(null),
      });
      modal.update({});
    });
  }, []);

  const handleConversationMenuCommand = useCallback(
    async (command: string, item: ConversationItem) => {
      if (!item?.key) {
        message.warning("未找到会话");
        return;
      }
      if (command === "rename") {
        const newName = await promptRenameConversation(item.label);
        if (!newName) return;
        try {
          await renameSession(projectId, item.key, { name: newName });
          setConversation(item.key, {
            ...item,
            label: newName,
            isAutoTitle: false,
          });
          message.success("会话重命名成功");
        } catch (err) {
          console.error("重命名会话失败", err);
          message.error("重命名会话失败，请稍后重试");
        }
        return;
      }
      if (command === "delete") {
        Modal.confirm({
          title: "删除确认",
          content: "确定删除当前会话吗？",
          okText: "删除",
          cancelText: "取消",
          onOk: async () => {
            try {
              await deleteSession(projectId, item.key);
              removeConversation(item.key);
              if (activeConversationKey === item.key) {
                const fallback = conversations.find((conversation) => conversation.key !== item.key);
                if (fallback) {
                  setActiveConversationKey(fallback.key);
                } else {
                  await createNewConversation();
                }
              }
              message.success("会话已删除");
            } catch (err) {
              console.error("删除会话失败", err);
              message.error("删除会话失败，请稍后重试");
            }
          },
        });
      }
    },
    [
      activeConversationKey,
      conversations,
      createNewConversation,
      projectId,
      promptRenameConversation,
      removeConversation,
      setActiveConversationKey,
      setConversation,
    ],
  );

  const handleConversationSelect = useCallback(
    (value: string) => {
      if (!value || value === activeConversationKey) return;
      if (isRequesting) {
        message.warning("请先终止当前回答，再切换会话。");
        return;
      }
      setActiveConversationKey(value);
      setError(null);
      setAttachments([]);
    },
    [activeConversationKey, isRequesting, setActiveConversationKey],
  );

  useEffect(() => {
    return () => {
      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.stop();
      }
      mediaStreamRef.current?.getTracks().forEach((track) => {
        track.stop();
      });
      mediaStreamRef.current = null;
    };
  }, []);

  const handlePromptClick = useCallback((item: PromptItem) => {
    setActivePromptKey(item.key);
    const promptText = item.meta?.text ?? item.label;
    setSenderValue((prev) => (prev ? `${prev.trimEnd()}\n${promptText}` : promptText));
    setLastSelectedPromptLabel(item.label);
    message.success(`已插入提示词「${item.label}」`);
  }, []);

  const clearPromptInput = useCallback(() => {
    setSenderValue("");
    setActivePromptKey("");
    setLastSelectedPromptLabel("");
    message.success("输入内容已清空");
  }, []);

  const beforeAttachmentUpload: UploadProps["beforeUpload"] = (file) => {
    if (file.size > MAX_UPLOAD_SIZE) {
      message.error("文件不能超过10MB");
      return Upload.LIST_IGNORE;
    }
    return true;
  };

  const handleAttachmentUpload: UploadProps["customRequest"] = async (options) => {
    const { file, onSuccess, onError } = options;
    if (!(file instanceof File)) {
      onError?.(new Error("文件格式错误"));
      return;
    }
    if (isRequesting) {
      const err = new Error("正在生成中，请稍后再上传文件");
      onError?.(err);
      message.warning(err.message);
      return;
    }
    const uid = createAttachmentId("upload");
    const uploadItem: UploadFile = {
      uid,
      name: file.name,
      status: "uploading",
      originFileObj: file as UploadFile["originFileObj"],
    };
    setAttachments((prev) => [...prev, uploadItem]);
    try {
      const dataUri = await fileToDataUri(file);
      setAttachments((prev) =>
        prev.map((item) => (item.uid === uid ? { ...item, status: "done", url: dataUri } : item)),
      );
      onSuccess?.({ success: true }, file);
      message.success(`文件 ${file.name} 上传成功`);
    } catch (error) {
      setAttachments((prev) => prev.filter((item) => item.uid !== uid));
      const err = error instanceof Error ? error : new Error(String(error || ""));
      onError?.(err);
      message.error(err.message || `文件 ${file.name} 上传失败`);
    }
  };

  const handleAttachmentRemove: UploadProps["onRemove"] = (file) => {
    setAttachments((prev) => prev.filter((item) => item.uid !== file.uid));
  };

  const handlePasteFile = useCallback(
    async (files: FileList) => {
      if (isRequesting) {
        message.warning("正在生成中，请稍后再粘贴文件");
        return;
      }

      for (const file of Array.from(files)) {
        if (file.size > MAX_UPLOAD_SIZE) {
          message.error(`文件 ${file.name} 不能超过10MB`);
          continue;
        }

        const uid = createAttachmentId("paste");
        const uploadItem: UploadFile = {
          uid,
          name: file.name,
          status: "uploading",
          originFileObj: file as UploadFile["originFileObj"],
        };
        setAttachments((prev) => [...prev, uploadItem]);

        try {
          const dataUri = await fileToDataUri(file);
          setAttachments((prev) =>
            prev.map((item) => (item.uid === uid ? { ...item, status: "done", url: dataUri } : item)),
          );
          message.success(`文件 ${file.name} 已添加到附件`);
        } catch (error) {
          setAttachments((prev) => prev.filter((item) => item.uid !== uid));
          message.error(`文件 ${file.name} 处理失败`);
        }
      }
    },
    [isRequesting],
  );

  const handleSubmit = useCallback(async () => {
    if (!senderValue.trim() || isRequesting) return;
    if (isTranscribingSpeech) {
      message.warning("语音识别中，请稍候再发送");
      return;
    }
    if (hasUploadingAttachments) {
      message.warning("文件上传中，请稍后发送消息");
      return;
    }
    if (!projectId || !activeConversationKey) {
      message.warning("缺少项目或会话信息，无法发送消息");
      return;
    }

    const fileItems: FileItem[] = attachments
      .filter((item) => item.url && item.name)
      .map((item) => ({
        part: "file",
        name: item.name ?? "文件",
        url: item.url as string,
      }));

    setError(null);
    listRef.current?.scrollTo({ top: "bottom" });
    const messageText = senderValue;
    setSenderValue("");
    setAttachments([]);

    await updateConversationTitleFromMessage(messageText);

    onRequest({
      model: "qwen3.5",
      thinking: isDeepThinking,
      projectId,
      sessionId: activeConversationKey,
      text: messageText,
      files: fileItems,
      tools: selectedTools,
    });
  }, [
    activeConversationKey,
    attachments,
    hasUploadingAttachments,
    isDeepThinking,
    isRequesting,
    projectId,
    selectedTools,
    senderValue,
    onRequest,
    updateConversationTitleFromMessage,
    isTranscribingSpeech,
  ]);

  const handleSpeechRecordingChange = useCallback(
    async (nextRecording: boolean) => {
      if (nextRecording) {
        if (isRequesting) {
          message.warning("生成中暂不支持语音输入，请稍后再试");
          setSpeechRecording(false);
          return;
        }
        if (isTranscribingSpeech) {
          message.warning("正在识别上一段语音，请稍候");
          setSpeechRecording(false);
          return;
        }
        if (!("mediaDevices" in navigator) || !navigator.mediaDevices.getUserMedia) {
          message.error("当前浏览器不支持录音");
          setSpeechRecording(false);
          return;
        }

        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          const recorder = new MediaRecorder(stream);

          mediaStreamRef.current = stream;
          mediaRecorderRef.current = recorder;
          speechChunksRef.current = [];

          recorder.ondataavailable = (event: BlobEvent) => {
            if (event.data.size > 0) {
              speechChunksRef.current.push(event.data);
            }
          };

          recorder.onstop = () => {
            const chunks = speechChunksRef.current;
            speechChunksRef.current = [];

            setSpeechRecording(false);
            mediaRecorderRef.current = null;

            mediaStreamRef.current?.getTracks().forEach((track) => {
              track.stop();
            });
            mediaStreamRef.current = null;

            if (!chunks.length) {
              message.warning("未采集到语音，请重试");
              return;
            }

            const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
            if (blob.size === 0) {
              message.warning("录音内容为空，请重试");
              return;
            }

            void (async () => {
              setIsTranscribingSpeech(true);
              try {
                const response = await transcribeAudio(blob, `recording-${Date.now()}.webm`);
                if (!response.success) {
                  throw new Error(response.status || "语音转写失败");
                }
                const text = response.text?.trim();
                if (!text) {
                  message.warning("未识别到有效语音内容");
                  return;
                }
                setSenderValue((prev) => (prev ? `${prev.trimEnd()}\n${text}` : text));
                message.success("语音识别成功，已填入输入框");
              } catch (err) {
                console.error("语音转写失败", err);
                message.error(err instanceof Error ? err.message : "语音转写失败");
              } finally {
                setIsTranscribingSpeech(false);
              }
            })();
          };

          recorder.start();
          setSpeechRecording(true);
          message.info("开始录音，再次点击麦克风结束");
        } catch (err) {
          console.error("启动录音失败", err);
          mediaRecorderRef.current = null;
          mediaStreamRef.current?.getTracks().forEach((track) => {
            track.stop();
          });
          mediaStreamRef.current = null;
          setSpeechRecording(false);
          message.error("无法开始录音，请检查麦克风权限");
        }
        return;
      }

      const recorder = mediaRecorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.stop();
        message.info("录音结束，正在识别...");
      } else {
        setSpeechRecording(false);
      }
    },
    [isRequesting, isTranscribingSpeech],
  );

  const handleAddChecklist = useCallback(
    async (content: string) => {
      if (!projectId) {
        message.warning("缺少项目ID，无法加入问题清单");
        return;
      }
      const question = content.trim();
      if (!question) {
        message.warning("没有可加入的问题内容");
        return;
      }
      try {
        const res = await createChecklist({
          project_id: projectId,
          question,
        });
        if (res?.success) {
          message.success("已加入问题清单");
        } else {
          message.error(res?.status || "加入问题清单失败");
        }
      } catch (error) {
        const errText = error instanceof Error ? error.message : "加入问题清单失败";
        message.error(errText);
      }
    },
    [projectId],
  );

  const handleCancel = useCallback(() => {
    if (!isRequesting) return;
    abort();
    message.info("已终止生成，您可以继续提问或开启新会话。\n");
  }, [abort, isRequesting]);

  const bubbleItems = useMemo(() => {
    const renderContentItems = (
      contentItems?: ContentItem[],
      _status?: "error" | "local" | "loading" | "updating" | "success" | "abort",
    ) => {
      if (!contentItems?.length) return { nodes: null, copyText: "" };
      const nodes: ReactNode[] = [];
      let copyText = "";
      let index = 0;

      while (index < contentItems.length) {
        const current = contentItems[index];
        if (current.part === "text") {
          let mergedText = current.content ?? "";
          let nextIndex = index + 1;
          while (nextIndex < contentItems.length && contentItems[nextIndex].part === "text") {
            mergedText += (contentItems[nextIndex] as ContentItem & { part: "text" }).content ?? "";
            nextIndex += 1;
          }
          nodes.push(
            <SuperMarkdown
              key={`text-${index}`}
              streaming={{
                hasNextChunk: current.status !== "success",
              }}
            >
              {mergedText}
            </SuperMarkdown>,
          );
          copyText += mergedText;
          index = nextIndex;
          continue;
        }
        if (current.part === "reasoning") {
          let mergedReasoning = current.reasoning ?? "";
          let nextIndex = index + 1;
          while (nextIndex < contentItems.length && contentItems[nextIndex].part === "reasoning") {
            mergedReasoning += (contentItems[nextIndex] as ContentItem & { part: "reasoning" }).reasoning ?? "";
            nextIndex += 1;
          }
          nodes.push(
            <Think key={`reasoning-${index}`} title="深度思考" defaultExpanded={current.status !== "success"}>
              {mergedReasoning}
            </Think>,
          );
          index = nextIndex;
          continue;
        }
        if (current.part === "file") {
          const handleFileDownload = (url?: string, name?: string) => {
            if (!url || !name) return;
            const link = document.createElement("a");
            link.href = url;
            link.download = name;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
          };
          const fileItems: FileCardProps[] = [];
          let nextIndex = index;
          while (nextIndex < contentItems.length && contentItems[nextIndex].part === "file") {
            const file = contentItems[nextIndex];
            if (file.part === "file") {
              fileItems.push({
                name: file.name ?? "文件",
                src: file.url,
                type: resolveFileType(file.url),
                onClick: () => handleFileDownload(file.url, file.name),
              });
            }
            nextIndex += 1;
          }
          if (fileItems.length) {
            nodes.push(<FileCard.List key={`file-${index}`} items={fileItems} />);
          }
          index = nextIndex;
          continue;
        }
        if (current.part === "tool") {
          const toolItems: ToolItem[] = [];
          let nextIndex = index;
          while (nextIndex < contentItems.length && contentItems[nextIndex].part === "tool") {
            const tool = contentItems[nextIndex];
            if (tool.part === "tool") {
              toolItems.push(tool as ToolItem);
            }
            nextIndex += 1;
          }
          if (toolItems.length) {
            const thoughtItems: ThoughtChainItemType[] = toolItems.map((tool) => ({
              title: tool.name,
              content: (
                <Flex>
                  {tool.args ? (
                    <ThoughtChain.Item
                      variant="solid"
                      icon={<CodeOutlined />}
                      title="调用工具"
                      description={typeof tool.args === "string" ? tool.args : JSON.stringify(tool.args, null, 2)}
                    />
                  ) : null}
                  {tool.result ? (
                    <ThoughtChain.Item
                      variant="solid"
                      icon={<ToolOutlined />}
                      title="工具结果"
                      description={typeof tool.result === "string" ? tool.result : JSON.stringify(tool.result, null, 2)}
                    />
                  ) : null}
                </Flex>
              ),
              collapsible: true,
              status: tool.status,
            }));
            nodes.push(<ThoughtChain key={`tool-${index}`} items={thoughtItems} />);
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
      const { nodes, copyText } = renderContentItems(item.content, info.status);
      const actionsItems: ItemType[] = [
        {
          key: "copy",
          actionRender: <Actions.Copy text={copyText} />,
        },
      ];
      if (item.role === "assistant") {
        actionsItems.push({
          key: "favorite",
          actionRender: <Actions.Feedback value={feedbackStatus} onChange={(val) => setFeedbackStatus(val)} />,
        });
        actionsItems.push({
          key: "checklist",
          label: "加入问题清单",
          icon: <PlusOutlined />,
          onItemClick: () => {
            if (!copyText.trim() || !projectId) {
              message.warning("没有可加入的问题内容或缺少项目ID");
              return;
            }
            handleAddChecklist(copyText);
          },
        });
      }
      return {
        key: String(info.id),
        role: item.role,
        status: info.status,
        loading: info.status === "loading",
        content: (
          <MessageContent>
            {nodes}
            <Actions items={actionsItems} />
          </MessageContent>
        ),
        streaming: info.status === "updating",
        typing: item.role === "assistant" && info.status === "updating" ? defaultTypingConfig : false,
        avatar: item.role === "user" ? <CommentOutlined /> : <RobotOutlined />,
      };
    });
  }, [messageInfos, feedbackStatus, handleAddChecklist, projectId]);

  const conversationMenu = useCallback(
    (item: { key?: string }): MenuProps => ({
      items: [
        { key: "rename", label: "重命名" },
        { key: "delete", label: "删除" },
      ],
      onClick: (info) => {
        const target = conversations.find((conversation) => conversation.key === item.key) as
          | ConversationItem
          | undefined;
        if (target) {
          void handleConversationMenuCommand(String(info.key), target);
        }
      },
    }),
    [conversations, handleConversationMenuCommand],
  );

  const conversationItems = useMemo(
    () =>
      conversations.map((item) => ({
        key: item.key,
        label: item.label,
      })),
    [conversations],
  );

  return (
    <ChatWrap>
      <ChatLayout>
        <Sidebar>
          <Conversations
            items={conversationItems}
            activeKey={activeConversationKey ?? undefined}
            onActiveChange={handleConversationSelect}
            menu={conversationMenu}
            creation={{
              label: "创建新会话",
              icon: <AppstoreAddOutlined />,
              onClick: createNewConversation,
            }}
          />
        </Sidebar>
        <Main>
          {!hasMessages ? (
            <Card size="small">
              <PromptHeader>
                <span>提示词管理</span>
                <Button type="link" size="small" onClick={clearPromptInput}>
                  清空输入
                </Button>
              </PromptHeader>
              <Prompts
                title="常用提示词"
                items={chatPrompts.map((item) => ({
                  key: item.key,
                  label: item.label,
                  description: item.description,
                  disabled: item.disabled,
                }))}
                wrap
                onItemClick={(info) => {
                  const target = chatPrompts.find((item) => item.key === info.data.key);
                  if (target) {
                    handlePromptClick(target);
                  }
                }}
              />
              {lastSelectedPromptLabel ? (
                <PromptSelectedTip>已插入提示词：{lastSelectedPromptLabel}</PromptSelectedTip>
              ) : null}
            </Card>
          ) : null}

          {error ? <Alert type="error" title={error.message} closable style={{ marginBottom: 8 }} /> : null}

          {isDefaultMessagesRequesting ? (
            <Alert type="info" title="历史记录加载中..." showIcon style={{ marginBottom: 8 }} />
          ) : null}

          <ChatContent>
            <Bubble.List
              ref={listRef}
              items={bubbleItems}
              autoScroll
              role={{
                user: { placement: "end", variant: "filled" },
                assistant: { placement: "start", variant: "outlined" },
              }}
            />
          </ChatContent>

          <Sender
            ref={senderRef}
            value={senderValue}
            onChange={(value) => setSenderValue(value)}
            onSubmit={handleSubmit}
            onCancel={handleCancel}
            onPasteFile={handlePasteFile}
            loading={isRequesting}
            allowSpeech={{
              recording: speechRecording,
              onRecordingChange: handleSpeechRecordingChange,
            }}
            autoSize={{ minRows: 1, maxRows: 10 }}
            placeholder="请输入内容...（可直接粘贴文件）"
            submitType="enter"
            header={
              <SenderTop>
                <Sender.Header title="附件上传" open={attachmentVisible} onOpenChange={setAttachmentVisible}>
                  <AttachmentPanel>
                    <Attachments
                      items={attachments}
                      multiple
                      maxCount={8}
                      beforeUpload={beforeAttachmentUpload}
                      customRequest={handleAttachmentUpload}
                      onRemove={handleAttachmentRemove}
                      overflow="wrap"
                      placeholder={(type) =>
                        type === "drop"
                          ? {
                              icon: <InboxOutlined />,
                              title: "拖拽文件到此处上传",
                              description: "支持上传文件，图片等多种类型，单个文件不超过10MB",
                            }
                          : {
                              icon: <CloudUploadOutlined />,
                              title: "在此处上传文件",
                              description: "支持上传文件，图片等多种类型，单个文件不超过10MB",
                            }
                      }
                      getDropContainer={() => senderRef.current?.nativeElement}
                    />
                  </AttachmentPanel>
                </Sender.Header>

                <Sender.Header title="工具选择" open={toolVisible} onOpenChange={setToolVisible}>
                  <ToolSelector>
                    <Checkbox
                      indeterminate={selectedTools.length > 0 && selectedTools.length < availableTools.length}
                      checked={selectedTools.length === availableTools.length}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedTools(availableTools.map((t) => t.value));
                        } else {
                          setSelectedTools([]);
                        }
                      }}
                      style={{ marginBottom: 8 }}
                    >
                      全选/全不选
                    </Checkbox>
                    <Checkbox.Group value={selectedTools} onChange={(values) => setSelectedTools(values as ToolType[])}>
                      <Flex wrap="wrap" gap="8px" style={{ width: "100%" }}>
                        {availableTools.map((tool) => (
                          <ToolOptionRow key={tool.value}>
                            <Checkbox value={tool.value} disabled={isRequesting}>
                              <ToolLabel>{tool.label}</ToolLabel>
                              <ToolDesc>{tool.description}</ToolDesc>
                            </Checkbox>
                          </ToolOptionRow>
                        ))}
                      </Flex>
                    </Checkbox.Group>
                  </ToolSelector>
                </Sender.Header>
              </SenderTop>
            }
            prefix={
              <SenderPrefix>
                <Tooltip title="附件上传">
                  <Sender.Switch
                    icon={<PaperClipOutlined />}
                    value={attachmentVisible}
                    onChange={setAttachmentVisible}
                    disabled={isRequesting}
                  />
                </Tooltip>
                <Tooltip title="工具选择">
                  <Sender.Switch
                    icon={<ToolOutlined />}
                    value={toolVisible}
                    onChange={setToolVisible}
                    disabled={isRequesting || availableTools.length === 0}
                  />
                </Tooltip>
                <Tooltip title="深度思考">
                  <Sender.Switch icon={<BulbOutlined />} value={isDeepThinking} onChange={setIsDeepThinking} />
                </Tooltip>
              </SenderPrefix>
            }
          />
        </Main>
      </ChatLayout>
    </ChatWrap>
  );
};

export default LLMChat;

const ChatWrap = styled("div")({
  height: "calc(100vh - 160px)",
  padding: "0 16px 16px",
});

const ChatLayout = styled("div")({
  height: "100%",
  display: "flex",
  gap: "16px",
  overflow: "hidden",
});

const Sidebar = styled("aside")({
  flex: "0 0 280px",
  minWidth: "240px",
  display: "flex",
  flexDirection: "column",
});

const Main = styled("section")({
  flex: "1",
  display: "flex",
  flexDirection: "column",
  gap: "12px",
  overflow: "hidden",
});

const ChatContent = styled("div")({
  flex: "1",
  minHeight: "0",
  display: "flex",
  flexDirection: "column",
});

const MessageContent = styled("div")({
  display: "flex",
  flexDirection: "column",
  gap: "12px",
});

const SenderPrefix = styled("div")({
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flaxWrap: "wrap",
});

const SenderTop = styled("div")({
  display: "flex",
});

const ToolSelector = styled("div")({
  display: "flex",
  flexDirection: "column",
  gap: "12px",
  width: "420px",
});

const ToolOptionRow = styled("div")({
  padding: "6px 8px",
  borderRadius: "6px",
  "&:hover": {
    background: "var(--bg-hover)",
  },
  width: "calc(50% - 4px)",
});

const ToolLabel = styled("div")({
  fontSize: "13px",
  fontWeight: "600",
});

const ToolDesc = styled("div")({
  fontSize: "12px",
  color: "var(--font-secondary)",
});

const AttachmentPanel = styled("div")({
  display: "flex",
  flexDirection: "column",
  gap: "12px",
  width: "360px",
});

const PromptHeader = styled("div")({
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: "8px",
});

const PromptSelectedTip = styled("p")({
  margin: "8px 0 0",
  padding: "6px 8px",
  fontSize: "12px",
  color: "var(--font-light)",
  background: "var(--bg-hover)",
  borderRadius: "4px",
  borderLeft: "3px solid var(--primary-color)",
});

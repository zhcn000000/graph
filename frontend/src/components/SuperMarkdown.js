import { Line } from "@ant-design/charts";
import { CodeHighlighter, FileCard, Mermaid, Think } from "@ant-design/x";
import XMarkdown from "@ant-design/x-markdown";
import Latex from "@ant-design/x-markdown/plugins/Latex";
import { Infographic } from "@antv/infographic";
import { Skeleton } from "antd";
import React, { memo, useEffect, useRef, useState } from "react";
function ReactInfographic(props) {
    const { children } = props;
    const $container = useRef(null);
    const infographicInstance = useRef(null);
    useEffect(() => {
        if ($container.current) {
            infographicInstance.current = new Infographic({
                container: $container.current,
            });
        }
        return () => {
            infographicInstance.current?.destroy();
        };
    }, []);
    useEffect(() => {
        infographicInstance.current?.render(children);
    }, [children]);
    return React.createElement("div", { ref: $container });
}
const CodeComponent = (props) => {
    const { className, children } = props;
    const lang = className?.match(/language-(\w+)/)?.[1] || "";
    if (typeof children !== "string")
        return null;
    if (lang === "mermaid")
        return React.createElement(Mermaid, null, children);
    else if (lang === "infographic")
        return React.createElement(ReactInfographic, null, children);
    else
        return React.createElement(CodeHighlighter, { lang: lang }, children);
};
const ThinkComponent = memo((props) => {
    const [title, setTitle] = useState("Deep thinking...");
    const [loading, setLoading] = useState(true);
    const [expand, setExpand] = useState(true);
    useEffect(() => {
        if (props.streamStatus === "done") {
            setTitle("Complete thinking");
            setLoading(false);
            setExpand(false);
        }
    }, [props.streamStatus]);
    return (React.createElement(Think, { title: title, loading: loading, expanded: expand, onClick: () => setExpand(!expand) }, props.children));
});
// biome-ignore lint/suspicious/noExplicitAny: <explanation> 需要兼容 Infographic 的数据格式</explanation>
const LineComponent = (props) => {
    const { children, axisXTitle, axisYTitle, streamStatus } = props;
    if (streamStatus === "loading") {
        return React.createElement(Skeleton.Image, { active: true, style: { width: 901, height: 408 } });
    }
    return React.createElement(Line, { data: JSON.parse(children), axisXTitle: axisXTitle, axisYTitle: axisYTitle });
};
// biome-ignore lint/suspicious/noExplicitAny: <explanation> 兼容 Markdown img 组件 props </explanation>
const ImageComponent = (props) => {
    const { src, alt } = props;
    return React.createElement(FileCard, { name: alt || "image", src: src, type: "image" });
};
// biome-ignore lint/suspicious/noExplicitAny: <explanation> 兼容 Markdown video 组件 props </explanation>
const VideoComponent = (props) => {
    const { src, alt } = props;
    return React.createElement(FileCard, { name: alt || "video", src: src, type: "video" });
};
// biome-ignore lint/suspicious/noExplicitAny: <explanation> 兼容 Markdown audio 组件 props </explanation>
const AudioComponent = (props) => {
    const { src, alt } = props;
    return React.createElement(FileCard, { name: alt || "audio", src: src, type: "audio" });
};
// biome-ignore lint/suspicious/noExplicitAny: <explanation> 兼容 Markdown a 组件 props </explanation>
const FileComponent = (props) => {
    const { href, children } = props;
    const name = typeof children === "string" ? children : "file";
    return React.createElement(FileCard, { name: name, src: href, type: "file" });
};
export const SuperMarkdown = (props) => {
    return (React.createElement(XMarkdown, { ...props, components: {
            code: CodeComponent,
            think: ThinkComponent,
            customLine: LineComponent,
            img: ImageComponent,
            video: VideoComponent,
            audio: AudioComponent,
            a: FileComponent,
        }, config: { extensions: Latex() } }));
};

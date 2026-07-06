import { useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Check, Copy } from "lucide-react";

interface Props {
  language: string;
  value: string;
}

export function CodeBlock({ language, value }: Props) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  return (
    <div className="my-4 overflow-hidden rounded-lg border border-ops-border bg-[#0e1117]">
      <div className="flex items-center justify-between border-b border-ops-border bg-ops-panel px-3 py-1.5">
        <span className="font-mono text-xs text-ops-muted">
          {language || "text"}
        </span>
        <button
          onClick={copy}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-ops-muted transition hover:text-ops-text"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || "text"}
        style={oneDark}
        customStyle={{
          margin: 0,
          background: "transparent",
          padding: "0.9rem 1rem",
          fontSize: "0.85rem",
        }}
        codeTagProps={{ style: { fontFamily: "inherit" } }}
        PreTag="div"
      >
        {value}
      </SyntaxHighlighter>
    </div>
  );
}

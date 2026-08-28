"use client";

import { useState } from "react";
import { trackEvent } from "@/lib/gtag";

/* First-screen connect card for /mcp.
   The guide used to open with five screens of "why a dedicated tool" prose and
   buried the actual command below the fold; GA showed 31 visitors averaging 6s
   on the page and only 5 ever reaching a docs link. The command a reader came
   for now sits in the first screen, and mcp_config_copy measures the step that
   actually matters — copying a working config — rather than page depth. */

const ENDPOINT = "https://mcp.valuescope.app/mcp";

type Client = {
  id: string;
  label: string;
  hint: React.ReactNode;
  snippet: string;
  /* What the copy button hands over, when that differs from what's shown. */
  copyLabel: string;
};

const CLIENTS: Client[] = [
  {
    id: "claude_code",
    label: "Claude Code",
    hint: <>终端里跑一次即可，之后所有会话都带着。</>,
    snippet: `claude mcp add valuescope --transport http ${ENDPOINT}`,
    copyLabel: "复制命令",
  },
  {
    id: "claude_web",
    label: "Claude 网页版 / App",
    hint: (
      <>
        设置 → Connectors → <strong>添加自定义连接器</strong>，把下面的地址粘进去。
      </>
    ),
    snippet: ENDPOINT,
    copyLabel: "复制地址",
  },
  {
    id: "json",
    label: "Cherry Studio / 其他",
    hint: <>支持 MCP 的客户端通用写法，HTTP（streamable）类型。</>,
    snippet: `{
  "mcpServers": {
    "valuescope": {
      "type": "streamableHttp",
      "url": "${ENDPOINT}"
    }
  }
}`,
    copyLabel: "复制配置",
  },
];

export default function McpQuickStart() {
  const [active, setActive] = useState(CLIENTS[0].id);
  const [copied, setCopied] = useState(false);
  const client = CLIENTS.find((c) => c.id === active) ?? CLIENTS[0];

  async function copy() {
    try {
      await navigator.clipboard.writeText(client.snippet);
    } catch {
      // Older browsers and non-secure contexts have no clipboard API. Falling
      // back keeps the button honest rather than silently doing nothing.
      const ta = document.createElement("textarea");
      ta.value = client.snippet;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } catch {
        return; // genuinely could not copy — don't claim success
      } finally {
        document.body.removeChild(ta);
      }
    }
    trackEvent("mcp_config_copy", { client: client.id });
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-xl border border-violet-200 dark:border-violet-900 bg-violet-50/50 dark:bg-violet-950/20 p-4 sm:p-5 mb-6">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-3">
        <h2 className="text-base font-bold text-gray-900 dark:text-white">两分钟接入</h2>
        <p className="text-xs text-violet-700 dark:text-violet-300 font-medium">
          不用注册 · A 股与港股完全免费
        </p>
      </div>

      <div role="tablist" aria-label="MCP 客户端" className="flex flex-wrap gap-1.5 mb-3">
        {CLIENTS.map((c) => (
          <button
            key={c.id}
            role="tab"
            aria-selected={c.id === active}
            onClick={() => {
              setActive(c.id);
              setCopied(false);
            }}
            className={`text-xs font-medium px-2.5 py-1 rounded-lg transition-colors ${
              c.id === active
                ? "bg-violet-600 text-white"
                : "bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-800 hover:border-violet-300 dark:hover:border-violet-800"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>

      {/* Button sits above the block, not floating over it: the Claude Code
          command is wider than the card, and an overlaid button hides exactly
          the tail of the URL a reader needs to see. */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <p className="text-xs text-gray-600 dark:text-gray-400">{client.hint}</p>
        <button
          onClick={copy}
          className="shrink-0 text-xs font-medium px-2.5 py-1 rounded-md bg-violet-600 hover:bg-violet-700 text-white transition-colors"
        >
          {copied ? "已复制 ✓" : client.copyLabel}
        </button>
      </div>

      <pre className="text-xs bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-3 overflow-x-auto font-mono text-gray-700 dark:text-gray-300 whitespace-pre">
{client.snippet}
      </pre>

      <p className="text-xs text-gray-500 dark:text-gray-500 mt-3">
        接好之后直接问：<em>&ldquo;给腾讯控股做个 DCF 估值&rdquo;</em>。美股与日股需要自备 FMP
        key（有每日免费体验额度）— 见下方{" "}
        <a href="#pricing" className="text-violet-600 dark:text-violet-400 hover:underline">
          支持的市场与数据源
        </a>
        。
      </p>
    </div>
  );
}

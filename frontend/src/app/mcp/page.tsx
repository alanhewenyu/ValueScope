import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "MCP 接入指南 — 在 Claude / ChatGPT 里调用 DCF 估值引擎 | ValueScope MCP Setup",
  description:
    "两分钟把 ValueScope MCP 估值引擎接入 Claude、ChatGPT、Cherry Studio 等任意 AI：确定性两相 DCF、价值桥、敏感性矩阵、反向 DCF。A股/港股开箱即用，美股/日股支持免费体验额度或自带 FMP key。Endpoint: https://mcp.valuescope.app/mcp",
  alternates: { canonical: "https://valuescope.app/mcp" },
};

/* 接入文档：中文为主（目标用户），命令与配置保持英文原样。
   服务端渲染，天然可被搜索引擎与 AI 助手引用。内容与 README 同步维护。 */

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return <h2 id={id} className="text-lg font-bold text-gray-900 dark:text-white mt-10 mb-3 scroll-mt-20">{children}</h2>;
}
function H3({ children }: { children: React.ReactNode }) {
  return <h3 className="text-base font-semibold text-gray-800 dark:text-gray-200 mt-6 mb-2">{children}</h3>;
}
function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed mb-3">{children}</p>;
}
function Code({ children }: { children: React.ReactNode }) {
  return <pre className="text-xs bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-3 mb-3 overflow-x-auto font-mono text-gray-700 dark:text-gray-300">{children}</pre>;
}

export default function McpGuide() {
  return (
    <div className="min-h-screen">
      <main className="max-w-2xl mx-auto px-4 py-10">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
          ← ValueScope
        </Link>

        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-4 mb-2">
          🔌 MCP 估值引擎接入指南
        </h1>
        <P>
          ValueScope 的 MCP（<a href="https://modelcontextprotocol.io" className="text-blue-600 dark:text-blue-400 hover:underline">Model Context Protocol</a>）服务器让任何支持
          MCP 的 AI 客户端 —— Claude、ChatGPT、Cherry Studio、Dify 等 —— 直接调用与本网站同一个确定性
          DCF 估值引擎。同样的输入永远得到同样的结果；AI 负责研究和判断参数，引擎负责计算。
        </P>
        <Code>Endpoint: https://mcp.valuescope.app/mcp</Code>

        <H2 id="connect">两分钟接入</H2>

        <H3>Claude Code（终端 / 桌面版共用配置）</H3>
        <Code>claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp</Code>

        <H3>Claude 网页版 / 手机 App</H3>
        <P>设置 → Connectors → 添加自定义 connector，粘贴 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">https://mcp.valuescope.app/mcp</code>。</P>

        <H3>Cherry Studio 及其他桌面客户端</H3>
        <P>添加一个 HTTP 类型的 MCP 服务器，URL 同上。</P>

        <P>
          接入后直接用自然语言提问：<em>&ldquo;给贵州茅台做个 DCF 估值&rdquo;</em> —— 无需学习任何命令。
          支持 MCP 提示词的客户端还会出现 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">/mcp__valuescope__dcf</code> 一键估值工作流。
        </P>

        <H2 id="how">工作原理 — 一个工具，两个阶段</H2>
        <P>
          服务器暴露单一 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">run_dcf</code> 工具，流程模拟证券分析师的工作方式，由调用的 AI 扮演分析师：
        </P>
        <P>
          <strong>① 基线</strong> — 不带假设调用 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">run_dcf(ticker)</code>，返回基于 5 年历史均值的基线估值、每个参数的历史区间、以及一份告诉模型如何评估各项假设的分析师指南。
        </P>
        <P>
          <strong>② 终值</strong> — 模型联网搜索业绩指引与一致预期，对每个参数独立推理，再带假设调用得到最终估值：内在价值、价值桥、预测表、敏感性矩阵、反向 DCF（市价隐含的增长预期）。
        </P>

        <H2 id="markets">支持市场与代码格式</H2>
        <P>
          A股 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">600519.SS / 000333.SZ</code>、港股 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">0700.HK</code>、美股 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">AAPL</code>、日股 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">7203.T</code>。
        </P>

        <H2 id="fmp">美股 / 日股：FMP key</H2>
        <P>
          A股与港股无需任何密钥。美股/日股数据来自 FMP，服务器提供每日少量免费体验额度；超出后自带你自己的
          key（两种方式）：
        </P>
        <H3>配置一次（推荐）</H3>
        <Code>{`claude mcp remove valuescope
claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp \\
  --header "X-FMP-Key: YOUR_KEY"`}</Code>
        <H3>按对话传入</H3>
        <P>在对话里直接说 <em>&ldquo;我的 FMP key 是 …&rdquo;</em>，模型会在每次调用时带上（仅当前对话有效）。</P>

        <H2 id="selfhost">自托管</H2>
        <P>
          引擎开源（AGPL-3.0）。运行后端后 MCP 服务在 <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">http://localhost:8000/mcp</code>，详见{" "}
          <a href="https://github.com/alanhewenyu/ValueScope" className="text-blue-600 dark:text-blue-400 hover:underline">GitHub README</a>。
        </P>

        <p className="text-xs text-gray-400 dark:text-gray-500 mt-10 border-t border-gray-100 dark:border-gray-800 pt-4">
          所有估值为确定性模型输出，仅供研究参考，不构成投资建议。All valuations are deterministic model
          outputs for research reference only — not investment advice.
        </p>
      </main>
    </div>
  );
}

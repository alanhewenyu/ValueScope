import type { Metadata } from "next";
import Link from "next/link";
import McpQuickStart from "@/components/McpQuickStart";

export const metadata: Metadata = {
  title: "MCP 接入指南 — 你的 AI 也能调用的 DCF 估值引擎 | ValueScope MCP Setup",
  description:
    "两分钟把 ValueScope 标准化 DCF 估值引擎接进 Claude、ChatGPT、Cherry Studio：AI 负责前瞻判断，ValueScope 负责数据和计算，同样的输入永远得到同样的结果。A股港股完全免费。Endpoint: https://mcp.valuescope.app/mcp",
  alternates: { canonical: "https://valuescope.app/mcp" },
};

/* 接入文档：中文为主（目标用户），命令与配置保持英文原样。
   服务端渲染，天然可被搜索引擎与 AI 助手引用。
   叙事与公众号文章《让你的AI学会DCF估值》发布版保持同步。 */

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return <h2 id={id} className="text-lg font-bold text-gray-900 dark:text-white mt-10 mb-3 scroll-mt-20">{children}</h2>;
}
function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed mb-3">{children}</p>;
}
function Code({ children }: { children: React.ReactNode }) {
  return <pre className="text-xs bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg p-3 mb-3 overflow-x-auto font-mono text-gray-700 dark:text-gray-300">{children}</pre>;
}
function InlineCode({ children }: { children: React.ReactNode }) {
  return <code className="text-xs bg-gray-100 dark:bg-gray-800 px-1 rounded">{children}</code>;
}

export default function McpGuide() {
  return (
    <div className="min-h-screen">
      <main className="max-w-2xl mx-auto px-4 py-10">
        <Link href="/" className="text-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
          ← ValueScope
        </Link>

        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mt-4 mb-2">
          🔌 你的 AI 也能调用的 DCF 估值引擎
        </h1>
        <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed mb-4">
          把一套标准化的 DCF 引擎接进 Claude、ChatGPT 或任意支持 MCP 的客户端：
          <strong>AI 负责前瞻判断，ValueScope 负责数据和计算</strong>，同样的输入永远得到同样的结果。
        </p>

        <McpQuickStart />

        <P>
          MCP（<a href="https://modelcontextprotocol.io" className="text-blue-600 dark:text-blue-400 hover:underline">Model Context Protocol</a>）可以理解为
          AI 世界里的通用接口标准。通过 MCP，Claude、ChatGPT 等 AI 助手可以安全地调用外部工具。接入
          ValueScope 后，你的 AI 就多了一项能力：<strong>使用一套标准化的 DCF 引擎对股票进行估值</strong>
          —— 不再是网页上的一个 AI 按钮，而是直接成为 AI 的能力。
        </P>

        <H2 id="why">为什么需要专门的工具 — AI 不是本来就能算吗？</H2>
        <P>
          问题在于，<strong>AI 很擅长推理，但不擅长保持一致</strong>。今天让 AI 给腾讯做一次
          DCF，下个月再做一次，两次使用的数据来源、财务口径、模型框架甚至参数定义都可能不同。最后你看到估值结果变了，却不知道：到底是公司基本面变了，还是
          AI 自己变了。对于长期跟踪几十家公司的人来说，这会是个问题。
        </P>
        <P>ValueScope MCP 的分工是这样的：</P>
        <P>
          <strong>AI 负责前瞻判断</strong>：搜索最新业绩指引、分析师预期，结合行业逻辑推理未来增长率、利润率和资本效率；
        </P>
        <P>
          <strong>ValueScope 负责数据和计算</strong>：标准化财务数据、DCF 模型、敏感性分析、反向
          DCF，以及所有具体计算过程。
        </P>
        <P>
          同样的输入永远得到同样的结果。换句话说：<strong>AI 提供智能，ValueScope 提供框架和纪律</strong>。
        </P>
        <P>
          这个分工还有一个很现实的好处：<strong>快</strong>。以前让 AI 从零做一次 DCF，它需要自己搜财务数据、理解报表结构、搭建模型框架，本质上是在临时搭建一张财务模型，不仅慢，而且
          token 成本高。而在 ValueScope MCP 中，数据管道、模型框架和计算逻辑都已经准备好，一次估值通常一两秒完成，调整假设重新计算几乎是秒级响应。AI
          的时间用在真正有价值的地方——分析和判断。
        </P>
        <P>
          MCP 是开放协议，支持 MCP 的客户端都可以接入：Claude Code、Claude Desktop、Claude 网页版、ChatGPT、Cherry
          Studio 等。估值质量最终取决于底层模型的推理能力和联网搜索能力——实际体验下来，目前效果最好的仍然是 Claude。
        </P>

        <H2 id="how">实际用起来是什么样</H2>
        <P>接入之后，你只需要像平时一样和 AI 对话。例如：<em>&ldquo;给腾讯控股做个 DCF 估值&rdquo;</em>。</P>
        <P>
          AI 会自动调用引擎完成整个流程：先获取过去五年的历史财务数据、计算各项估值参数的历史区间（收入增速、利润率、资本效率的变化趋势）；然后按模型内置的分析框架联网搜索最新业绩指引、分析师一致预期和行业信息；接下来对每一个关键假设独立推理并说明理由；最后调用估值引擎生成结果。
        </P>
        <P>
          输出包括估值结论、关键假设表、历史趋势分析、价值构成、敏感性分析以及<strong>反向 DCF</strong>。相比&ldquo;目标价是多少&rdquo;，更有价值的问题是：<strong>当前市场价格隐含了什么假设？这些假设你是否认同？</strong>
        </P>
        <P>
          你还可以进一步要求按乐观、中性、悲观三种情景分别估值，或者直接查看利润率和收入增速的历史趋势图。支持
          MCP 提示词的客户端还有 <InlineCode>/mcp__valuescope__dcf</InlineCode> 一键估值工作流。
        </P>

        <H2 id="connect">接入之后</H2>
        <P>
          直接用自然语言提问即可，不需要记任何命令。股票代码格式：A股 <InlineCode>600519.SS / 000333.SZ</InlineCode>、港股 <InlineCode>0700.HK</InlineCode>、美股 <InlineCode>AAPL</InlineCode>、日股 <InlineCode>7203.T</InlineCode>。
        </P>
        <P>
          还没接入的话，配置在本页开头的「两分钟接入」卡片里 —— Claude Code、Claude 网页版 / App、Cherry Studio 各一份，复制粘贴即可。
        </P>

        <H2 id="pricing">支持的市场与数据源</H2>
        <P>
          <strong>A股与港股完全免费</strong>，无需注册 API，接入即可使用。
        </P>
        <P>
          <strong>美股与日股</strong>的数据来自 FMP（Financial Modeling Prep），需要提供 API
          Key（服务器提供每日少量免费体验额度，先试再配）。如果你前面已经接入过（没带
          key），补上 key 只需删掉旧的再重新加一遍：
        </P>
        <Code>{`claude mcp remove valuescope
claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp \\
  --header "X-FMP-Key: 你的key"`}</Code>
        <P>
          网页版 / 手机 App 的 Connectors 里，则是在添加连接器时的高级选项里填一个自定义请求头：名称{" "}
          <InlineCode>X-FMP-Key</InlineCode>、值是你的 key。配好之后所有对话自动带上，不用再手动提。
        </P>
        <P>
          临时快速试一下也行——直接在对话里说 <em>&ldquo;我的 FMP key 是 xxx，给英伟达估值&rdquo;</em>，但这只在当前对话有效，长期用还是建议按上面配置。
        </P>
        <P>
          FMP 的财务数据质量不错，订阅价格也相对便宜。通过下面这个推荐链接注册并订阅（已含{" "}
          <strong>valuescope</strong> 优惠码），会比官网便宜一些：
        </P>
        <P>
          <a
            href="https://site.financialmodelingprep.com/pricing-plans?couponCode=valuescope"
            className="text-blue-600 dark:text-blue-400 hover:underline break-all"
            rel="noopener"
          >
            site.financialmodelingprep.com/pricing-plans?couponCode=valuescope
          </a>
        </P>

        <H2 id="web">关于网页版</H2>
        <P>
          网页版 <Link href="/" className="text-blue-600 dark:text-blue-400 hover:underline">valuescope.app</Link>{" "}
          会持续维护，它的定位：一个用于手动调参数、做敏感性分析和快速验证想法的 <strong>DCF 工作台</strong>
          —— 两种入口跑的是同一套引擎。
        </P>

        <H2 id="selfhost">自托管</H2>
        <P>
          引擎开源（AGPL-3.0）。运行后端后 MCP 服务在 <InlineCode>http://localhost:8000/mcp</InlineCode>，详见{" "}
          <a href="https://github.com/alanhewenyu/ValueScope" className="text-blue-600 dark:text-blue-400 hover:underline">GitHub README</a>。
        </P>

        <p className="text-xs text-gray-400 dark:text-gray-500 mt-10 border-t border-gray-100 dark:border-gray-800 pt-4">
          ValueScope 的所有输出均为模型计算结果，仅供研究参考，不构成任何投资建议。All valuations are
          deterministic model outputs for research reference only — not investment advice.
        </p>
      </main>
    </div>
  );
}

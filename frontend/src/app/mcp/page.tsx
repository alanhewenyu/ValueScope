import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "MCP 接入指南 — 让你的 AI 学会 DCF 估值 | ValueScope MCP Setup",
  description:
    "两分钟把 ValueScope 标准化 DCF 估值引擎接进 Claude、ChatGPT、Cherry Studio：AI 负责搜索指引、推理假设，引擎负责数据和计算。A股港股完全免费，美股日股每天 3 次免费体验。Endpoint: https://mcp.valuescope.app/mcp",
  alternates: { canonical: "https://valuescope.app/mcp" },
};

/* 接入文档：中文为主（目标用户），命令与配置保持英文原样。
   服务端渲染，天然可被搜索引擎与 AI 助手引用。
   叙事与公众号文章《让你的AI学会DCF估值》及 README 保持同步。 */

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
          🔌 让你的 AI 学会 DCF 估值
        </h1>
        <P>
          ValueScope 的 MCP（<a href="https://modelcontextprotocol.io" className="text-blue-600 dark:text-blue-400 hover:underline">Model Context Protocol</a>）服务把标准化
          DCF 估值引擎接进你自己的 AI —— Claude、ChatGPT、Cherry Studio、Dify 等任何支持 MCP
          的客户端。接入之后，你的 AI 就多了一项本事：用一套标准化的 DCF 引擎给股票算内在价值。
        </P>
        <Code>Endpoint: https://mcp.valuescope.app/mcp</Code>

        <H2 id="why">为什么需要它 — AI 本来不就会算 DCF 吗？</H2>
        <P>
          AI 确实会&ldquo;算&rdquo;DCF，但你让它今天算一次、下个月再算一次，两次的数据来源、报表口径、模型假设可能完全不同
          —— 你分不清估值的变化是基本面变了，还是 AI 这次心情不同。对需要长期跟踪几十家公司的人来说，这是致命的。
        </P>
        <P>ValueScope MCP 做的是分工：</P>
        <P>
          <strong>AI 负责前瞻判断</strong> — 搜索最新业绩指引、分析师预期，结合行业逻辑推理每个假设参数；
        </P>
        <P>
          <strong>引擎负责数据和计算</strong> — A股扣非归母净利润口径、剔除非经营项目的 EBIT 调整、10 年 FCFF
          折现、敏感性分析、反向 DCF。同样的输入永远得到同样的结果。
        </P>
        <P>
          你的 AI 提供智能，ValueScope 提供纪律。而且快：模型框架和数据管道都是现成的确定性代码，单次估值一两秒完成，换一组假设重算是秒级响应
          —— AI 的时间只花在真正需要智能的地方。
        </P>

        <H2 id="how">实际用起来是什么样</H2>
        <P>接入后在对话里说一句 <em>&ldquo;给贵州茅台做个 DCF 估值&rdquo;</em>，你的 AI 会自动走完整个流程：</P>
        <P>① 调用引擎拿到基于 5 年历史财报的<strong>基线估值</strong>和每个参数的历史区间；</P>
        <P>② 按引擎返回的分析指南<strong>联网搜索</strong>最新业绩指引和分析师一致预期；</P>
        <P>③ 对每个假设参数独立推理、给出依据，再调用引擎算出<strong>最终估值</strong>；</P>
        <P>
          ④ 按统一结构呈现：结论卡、关键假设表（附历史趋势）、价值构成、敏感性区间、<strong>反向 DCF</strong>
          —— 市场当前价格隐含了什么假设，你是否认同。
        </P>
        <P>
          也可以让它&ldquo;按乐观、中性、悲观三种情景分别算一遍&rdquo;，或要营收增速、利润率、资本效率的五年趋势图。支持
          MCP 提示词的客户端还有 <InlineCode>/mcp__valuescope__dcf</InlineCode> 一键估值工作流。
        </P>

        <H2 id="connect">怎么接入（两分钟）</H2>

        <H3>Claude Code（终端 / 桌面 App 共用配置）</H3>
        <Code>claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp</Code>

        <H3>Claude 网页版 / 手机 App</H3>
        <P>设置 → Connectors → 添加自定义连接器，粘贴 <InlineCode>https://mcp.valuescope.app/mcp</InlineCode>。</P>

        <H3>Cherry Studio 及其他桌面客户端</H3>
        <P>在 MCP 服务器设置里选 HTTP 类型，填同一个地址。</P>

        <P>
          接入后不需要学任何命令，直接用自然语言提问。代码格式：A股 <InlineCode>600519.SS / 000333.SZ</InlineCode>、港股 <InlineCode>0700.HK</InlineCode>、美股 <InlineCode>AAPL</InlineCode>、日股 <InlineCode>7203.T</InlineCode>。
        </P>

        <H2 id="pricing">支持的市场和费用</H2>
        <P>
          <strong>A股和港股完全免费</strong>，不需要注册任何 API，接入就能用。
        </P>
        <P>
          <strong>美股和日股</strong>的数据来自 FMP（Financial Modeling Prep），服务器提供<strong>每天 3 次的免费体验</strong>
          —— 先体验，觉得有用再注册自己的 key。注册后把 key 交给 AI 有两种方式：
        </P>
        <H3>接入时配置一次，永久生效（推荐）</H3>
        <Code>{`claude mcp add valuescope --transport http https://mcp.valuescope.app/mcp \\
  --header "X-FMP-Key: 你的key"`}</Code>
        <H3>对话里直接说</H3>
        <P>
          <em>&ldquo;我的 FMP key 是 xxx，给英伟达估值&rdquo;</em> —— 同一个对话里说一次就行。体验额度用完时，AI 也会主动告诉你这两种配置方法。
        </P>
        <P>
          FMP 的美股财务数据质量不错、价格也相对便宜。通过下面的推荐链接注册，用优惠码{" "}
          <strong>valuescope</strong> 会比官网便宜一些，也算是对这个项目的一点支持：
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

        <H2 id="web">网页版的角色</H2>
        <P>
          网页版 <Link href="/" className="text-blue-600 dark:text-blue-400 hover:underline">valuescope.app</Link>{" "}
          是手动调参数、看敏感性、快速验证想法的操作台 —— 两种入口跑的是同一套引擎。
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

// Build-time feature flags (NEXT_PUBLIC_ vars are inlined at build).

// AI valuation features (AI param generation, gap analysis, and the AI
// engine keys in settings) are hidden by default: usage was near zero,
// server-side quota costs real money, and the product direction is "user's
// own AI calls our engine via MCP" rather than us calling an LLM. Backend
// endpoints stay live; set NEXT_PUBLIC_ENABLE_AI_VALUATION=1 to bring the
// UI back.
export const AI_VALUATION_ENABLED =
  process.env.NEXT_PUBLIC_ENABLE_AI_VALUATION === "1";

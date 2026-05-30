import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { apiGet } from "../client.js";

export function registerPredictionTool(server: McpServer) {
  server.tool(
    "get_prediction",
    "Get the latest 3-stage ML prediction for a stock ticker. Returns signal (BUY/SELL/HOLD), confidence %, anomaly flag, and FinBERT sentiment score.",
    {
      ticker: z.string().describe("Stock ticker, e.g. NVDA or MAYBANK.KL"),
      force_refresh: z.boolean().optional().default(false).describe("Bypass Redis cache and run full pipeline"),
    },
    async ({ ticker, force_refresh }) => {
      const data = await apiGet(`/api/predict/${ticker}?force_refresh=${force_refresh}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
    }
  );
}

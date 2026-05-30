import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { apiGet } from "../client.js";

export function registerSentimentTool(server: McpServer) {
  server.tool(
    "get_sentiment",
    "Get aggregated FinBERT sentiment score and top headlines for a ticker. Sources: NewsAPI + Reddit PRAW.",
    {
      ticker: z.string(),
      hours: z.number().default(24).describe("Look-back window in hours"),
    },
    async ({ ticker, hours }) => {
      const data = await apiGet(`/api/sentiment/${ticker}?hours=${hours}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
    }
  );
}

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { apiGet } from "../client.js";

export function registerAnomaliesTool(server: McpServer) {
  server.tool(
    "get_anomalies",
    "Retrieve Isolation Forest anomaly history for a ticker. Returns dates, anomaly scores, and price context.",
    {
      ticker: z.string(),
      days: z.number().min(7).max(365).default(30),
    },
    async ({ ticker, days }) => {
      const data = await apiGet(`/api/anomalies/${ticker}?days=${days}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
    }
  );
}

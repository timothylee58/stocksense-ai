import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { apiPost } from "../client.js";

export function registerRetrainTool(server: McpServer) {
  server.tool(
    "trigger_retrain",
    "Kick off full 3-stage model retraining pipeline (Isolation Forest → XGBoost → LR stacker). Logs to MLflow. Returns run_id.",
    {
      ticker: z.string(),
      training_period_days: z.number().default(365),
    },
    async ({ ticker, training_period_days }) => {
      const data = await apiPost(`/api/train/${ticker}`, { training_period_days });
      return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
    }
  );
}

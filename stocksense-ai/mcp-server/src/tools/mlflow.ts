import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { apiGet } from "../client.js";

export function registerMlflowTools(server: McpServer) {
  server.tool(
    "compare_mlflow_runs",
    "Compare two MLflow experiment runs. Returns metric deltas (directional_accuracy, roc_auc, f1).",
    {
      run_id_a: z.string(),
      run_id_b: z.string(),
    },
    async ({ run_id_a, run_id_b }) => {
      const data = await apiGet(`/api/mlflow/compare?run_a=${run_id_a}&run_b=${run_id_b}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
    }
  );

  server.tool(
    "get_feature_importance",
    "Return XGBoost SHAP feature importance for the current production model.",
    {
      ticker: z.string(),
      top_n: z.number().default(10),
    },
    async ({ ticker, top_n }) => {
      const data = await apiGet(`/api/mlflow/feature-importance/${ticker}?top_n=${top_n}`);
      return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }] };
    }
  );
}

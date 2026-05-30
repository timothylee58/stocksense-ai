import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { registerPredictionTool } from "./tools/prediction.js";
import { registerAnomaliesTool } from "./tools/anomalies.js";
import { registerRetrainTool } from "./tools/retrain.js";
import { registerSentimentTool } from "./tools/sentiment.js";
import { registerMlflowTools } from "./tools/mlflow.js";

const server = new McpServer({
  name: "stocksense-mcp",
  version: "1.0.0",
});

registerPredictionTool(server);
registerAnomaliesTool(server);
registerRetrainTool(server);
registerSentimentTool(server);
registerMlflowTools(server);

const transport = new StdioServerTransport();
await server.connect(transport);
console.error("StockSense MCP server running (stdio)");

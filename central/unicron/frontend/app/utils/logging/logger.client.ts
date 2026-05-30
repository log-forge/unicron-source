import pino from "pino";
import { clientEnv } from "../env.client";

const isDev = clientEnv.VITE_NODE_ENV === "development";

export const clientLog = pino({
  level: isDev ? "debug" : "error",
  browser: {
    asObject: true,
  },
});

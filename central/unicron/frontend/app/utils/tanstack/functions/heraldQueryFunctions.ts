import { httpApp } from "../../http.client";
import type { IHerald, IHeraldsSummary } from "../../../types/api/queries/heraldQueries.types";
import { clientLog } from "../../logging/logger.client";

// Fetch all heralds
export const getHeralds = async (): Promise<IHerald[]> => {
  const { status, data } = await httpApp.get("/queries/list-heralds");
  if (status !== 200) throw new Error("Failed to fetch heralds");
  if (!Array.isArray(data)) throw new Error("Invalid heralds response format");
  clientLog.debug({ count: data.length }, "Fetched heralds");

  return data;
};

// Fetch heralds summary
export const getHeraldsSummary = async (): Promise<IHeraldsSummary> => {
  const { status, data } = await httpApp.get("/queries/heralds-summary");
  if (status !== 200) throw new Error("Failed to fetch heralds summary");
  clientLog.debug({ data }, "Fetched heralds summary");

  return data;
};

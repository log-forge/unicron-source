import type { IContainerSelector } from "./telemetry.types";
import type { IVMData } from "../../victoria/series.types";

export interface IMetricsInstantPayload extends IContainerSelector {
  expr: string;
  time?: number;
}

export interface IMetricsRangePayload extends IContainerSelector {
  expr: string;
  start: number;
  end: number;
  step: string;
}

export interface IMetricsLabelNamesPayload extends IContainerSelector {
  start?: number;
  end?: number;
}

export interface IMetricsLabelValuesPayload extends IMetricsLabelNamesPayload {
  label: string;
}

export interface IVMApiSuccess {
  status: "success";
  data: IVMData;
  warnings?: string[];
}

export interface IVMApiError {
  status: "error";
  errorType: string;
  error: string;
  warnings?: string[];
}

export type IVMApiResponse = IVMApiSuccess | IVMApiError;

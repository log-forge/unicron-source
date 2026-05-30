export interface IVMVectorSample {
  metric: Record<string, string>;
  value: [number, string];
}

export interface IVMMatrixSample {
  metric: Record<string, string>;
  values: Array<[number, string]>;
}

export interface IVMVectorData {
  resultType: "vector";
  result: IVMVectorSample[];
}

export interface IVMMatrixData {
  resultType: "matrix";
  result: IVMMatrixSample[];
}

export interface IVMScalarData {
  resultType: "scalar";
  result: [number, string];
}

export interface IVMStringData {
  resultType: "string";
  result: [number, string];
}

export type IVMData = IVMVectorData | IVMMatrixData | IVMScalarData | IVMStringData;

export interface IVMFlatVectorEntry {
  metric: Record<string, string>;
  value: [number, string];
  group?: number | null;
}

export interface IVMFlatMatrixEntry {
  metric: Record<string, string>;
  values: Array<[number, string]>;
  group?: number | null;
}

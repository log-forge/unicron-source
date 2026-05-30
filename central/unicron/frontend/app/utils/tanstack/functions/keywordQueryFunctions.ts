// import { QueryClient } from "@tanstack/react-query";
// import axiosClient from "~/utils/axiosClient";

// const isServer = typeof window === "undefined";
// const baseURL = isServer
//   ? `${process.env.VITE_BACKEND_SERVICE_HOST}:${process.env.VITE_BACKEND_SERVICE_PORT}`
//   : `${window.location.protocol}//${window.location.hostname}:${window.ENV.VITE_EXPOSED_BACKEND_PORT}`;
// console.log("Base URL:", baseURL);

// export const getKeywords = async () => {
//   const _t0 = `${Date.now().toString()} get keywords`;
//   console.time(_t0);
//   console.log("Fetching keywords...", baseURL, `${window.location.protocol}//${window.location.hostname}`);
//   const { status, data } = await axiosClient.get(`${baseURL}/config/filters`);
//   console.timeEnd(_t0);
//   if (status !== 200) throw new Response("Failed to fetch keywords");
//   if (!("keywords" in data) || !Array.isArray(data.keywords) || !data.keywords.every((kw: any) => typeof kw === "string")) {
//     throw new Response("Keywords not found or invalid format");
//   }

//   const keywords = data.keywords as string[];
//   console.log("keywords length:", keywords.length);
//   return keywords;
// };

// export function invalidateKeywords(queryClient: QueryClient) {
//   queryClient.invalidateQueries({ queryKey: ["keywords"], exact: true });
// }

// export const setKeywords = async (keywords: string) => {
//   try {
//     const _t1 = `${Date.now().toString()} add keywords`;
//     console.time(_t1);
//     const { status, data } = await axiosClient.post<{ status: string; added: string[]; skipped: string[] }>(`${baseURL}/config/filters/add-keyword`, {
//       keywords,
//     });
//     console.timeEnd(_t1);
//     if (status !== 200 || data.status != "success") throw new Response("Failed to set keywords");

//     console.log("Keywords added:", data.added.length);
//     return data.added;
//   } catch (error) {
//     console.error("Error setting keywords:", error);
//     throw new Response("Failed to set keywords");
//   }
// };

// export const removeKeywords = async (keywords: string) => {
//   try {
//     const _t2 = `${Date.now().toString()} remove keywords`;
//     console.time(_t2);
//     const { status, data } = await axiosClient.delete<{ status: string; removed: string[]; not_found: string[] }>(
//       `${baseURL}/config/filters/remove-keyword`,
//       { data: { keywords } },
//     );
//     console.timeEnd(_t2);
//     if (status !== 200 || data.status != "success") throw new Response("Failed to remove keywords");

//     console.log("Keywords removed:", data.removed.length);
//     return data.removed;
//   } catch (error) {
//     console.error("Error removing keywords:", error);
//     throw new Response("Failed to remove keywords");
//   }
// };

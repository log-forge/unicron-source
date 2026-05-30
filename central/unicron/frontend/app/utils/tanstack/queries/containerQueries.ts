// import { useQuery, useQueryClient } from "@tanstack/react-query";
// import { getContainerDirectory, getContainerFile, type Directory } from "../functions/containerQueryFunctions";

// // Query hook for fetching directory structure
// export function useContainerDirectory(containerName: string, path: string = "/", initialData: Directory | undefined, enabled: boolean = true) {
//   return useQuery({
//     queryKey: ["directory", containerName, path],
//     queryFn: () => getContainerDirectory(containerName, path),
//     initialData,
//     staleTime: 30 * 1000, // Consider data stale after 30 seconds
//     enabled: enabled,
//     refetchInterval: 1000 * 60 * 5, // 5 minutes
//     refetchOnMount: false,
//   });
// }

// // Invalidation helper function
// export function invalidateContainerDirectory(containerName?: string, path?: string, exact: boolean = false) {
//   console.log(`Invalidating directory query for container: ${containerName}, path: ${path}`);
//   const queryClient = useQueryClient();

//   if (containerName && path) {
//     // Invalidate specific directory
//     queryClient.invalidateQueries({ queryKey: ["directory", containerName, path], exact });
//   } else if (containerName) {
//     // Invalidate all directories for a specific container
//     queryClient.invalidateQueries({ queryKey: ["directory", containerName], exact });
//   } else {
//     // Invalidate all directory queries
//     queryClient.invalidateQueries({ queryKey: ["directory"] });
//   }
// }

// // Query hook for fetching file content
// export function useContainerFile(containerName: string, path: string, enabled: boolean = true) {
//   return useQuery({
//     queryKey: ["file", containerName, path],
//     queryFn: () => getContainerFile(containerName, path),
//     staleTime: 30 * 1000, // Consider data stale after 30 seconds
//     enabled,
//     retry: 1, // Only retry once since file errors are often permanent
//   });
// }

// // Invalidation helper function
// export function invalidateContainerFile(containerName?: string, path?: string, exact: boolean = false) {
//   console.log(`Invalidating file query for container: ${containerName}, path: ${path}`);
//   const queryClient = useQueryClient();

//   if (containerName && path) {
//     // Invalidate specific file
//     queryClient.invalidateQueries({ queryKey: ["file", containerName, path], exact });
//   } else if (containerName) {
//     // Invalidate all files for a specific container
//     queryClient.invalidateQueries({ queryKey: ["file", containerName], exact });
//   } else {
//     // Invalidate all file queries
//     queryClient.invalidateQueries({ queryKey: ["file"] });
//   }
// }

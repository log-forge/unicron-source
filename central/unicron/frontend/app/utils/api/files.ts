import { io, type Socket } from "socket.io-client";
import type { ClientToServerEvents, ServerToClientEvents } from "~/socket/socket.types";
import { resolveSocketEndpoint } from "~/socket/resolveSocketEndpoint";

export interface DirectoryEntry {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
  modified?: string;
}

export interface Directory {
  path: string;
  entries: DirectoryEntry[];
}

export interface FileContent {
  path: string;
  content: string;
  size: number;
  encoding?: string;
}

let socket: Socket<ServerToClientEvents, ClientToServerEvents> | null = null;

function getSocket(): Socket<ServerToClientEvents, ClientToServerEvents> {
  if (socket) return socket;
  const { url, path } = resolveSocketEndpoint();
  socket = io(url, {
    path,
    withCredentials: true,
    transports: ["websocket", "polling"],
    autoConnect: true,
  }) as Socket<ServerToClientEvents, ClientToServerEvents>;
  return socket;
}

async function sendFilesRequest(
  containerKey: string,
  hostId: string,
  action: "list" | "read",
  path: string,
): Promise<any> {
  const appSocket = getSocket();
  return await new Promise((resolve, reject) => {
    appSocket.emit("containers:files:request", { container_key: containerKey, host_id: hostId, action, path }, (resp) => {
      const requestId = resp?.request_id;
      if (!requestId) {
        reject(new Error("Failed to start file request"));
        return;
      }

      const handler = (data: any) => {
        if (data.request_id !== requestId) return;
        if (data.error) {
          appSocket.off("containers:files:response", handler);
          reject(new Error(data.error));
          return;
        }
        appSocket.off("containers:files:response", handler);
        resolve(data);
      };

      appSocket.on("containers:files:response", handler);
      setTimeout(() => {
        appSocket.off("containers:files:response", handler);
        reject(new Error("Request timeout"));
      }, 10000);
    });
  });
}

export function closeFileConnection(): void {
  // Socket.IO transport is shared globally; there is no per-container browser socket to close.
}

export async function getContainerDirectory(
  containerKey: string,
  path: string,
  hostId?: string | null
): Promise<Directory> {
  const response = await sendFilesRequest(containerKey, hostId ?? "local", "list", path);
  return {
    path: response.path || path,
    entries: (response.entries || []).map((entry: any) => ({
      name: entry.name,
      path: entry.path,
      type: entry.type,
      size: entry.size,
      modified: entry.modified,
    })),
  };
}

export async function getContainerFile(
  containerKey: string,
  path: string,
  hostId?: string | null
): Promise<FileContent> {
  const response = await sendFilesRequest(containerKey, hostId ?? "local", "read", path);
  return {
    path: response.path || path,
    content: response.content || "",
    size: response.size || 0,
    encoding: response.encoding,
  };
}

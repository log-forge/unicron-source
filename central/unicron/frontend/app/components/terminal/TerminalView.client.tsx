import { useEffect, useRef, useCallback, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { ClipboardAddon } from "@xterm/addon-clipboard";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { useRefDimensions } from "~/hooks/useRefDimensions";
import { useSocket } from "~/context/SocketContext";

export interface TerminalViewProps {
  containerKey: string;
  hostId?: string;
  className?: string;
}

type ConnectionState = "connecting" | "connected" | "disconnected" | "error";

const TERMINAL_BACKGROUND = "#1a1a1a";

// Intentionally terminal-specific: these values define the xterm ANSI palette and are not app chrome tokens.
const TERMINAL_ANSI_THEME = {
  background: TERMINAL_BACKGROUND,
  foreground: "#e0e0e0",
  cursor: "#888",
  cursorAccent: TERMINAL_BACKGROUND,
  selectionBackground: "rgba(255, 255, 255, 0.3)",
  black: "#000000",
  red: "#e06c75",
  green: "#98c379",
  yellow: "#d19a66",
  blue: "#61afef",
  magenta: "#c678dd",
  cyan: "#56b6c2",
  white: "#abb2bf",
  brightBlack: "#5c6370",
  brightRed: "#e06c75",
  brightGreen: "#98c379",
  brightYellow: "#d19a66",
  brightBlue: "#61afef",
  brightMagenta: "#c678dd",
  brightCyan: "#56b6c2",
  brightWhite: "#ffffff",
};

export function TerminalView({
  containerKey,
  hostId,
  className = "",
}: TerminalViewProps) {
  const terminalRef = useRef<HTMLDivElement | null>(null);
  const termInstance = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const { socket } = useSocket();

  const [containerRef, dimensions] = useRefDimensions<HTMLDivElement>(() => {
    if (fitAddonRef.current && termInstance.current) {
      fitAddonRef.current.fit();
      sendResize();
    }
  });

  const sendResize = useCallback(() => {
    if (socket && sessionIdRef.current && termInstance.current) {
      socket.emit("containers:terminal:resize", {
        session_id: sessionIdRef.current,
        cols: termInstance.current.cols,
        rows: termInstance.current.rows,
      });
    }
  }, [socket]);

  useEffect(() => {
    if (!terminalRef.current || !socket || !containerKey || !hostId) return;

    const term = new Terminal({
      scrollback: 10_000,
      allowProposedApi: true,
      theme: TERMINAL_ANSI_THEME,
      disableStdin: false,
      cursorBlink: true,
      convertEol: true,
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      fontSize: 14,
      lineHeight: 1.2,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(new ClipboardAddon());
    term.loadAddon(new WebLinksAddon());
    term.open(terminalRef.current);
    fitAddon.fit();

    termInstance.current = term;
    fitAddonRef.current = fitAddon;
    term.writeln("\x1b[33mConnecting to container...\x1b[0m");

    const handleTerminalData = (data: any) => {
      if (data._relay_type === "exec_started") {
        if (!data.success) {
          setConnectionState("error");
          term.writeln(`\r\n\x1b[31mFailed to start terminal: ${data.message || "unknown error"}\x1b[0m`);
          return;
        }
        setConnectionState("connected");
        term.writeln("\x1b[32mConnected!\x1b[0m\r\n");
        setTimeout(() => {
          fitAddon.fit();
          sendResize();
        }, 100);
        return;
      }
      if (data._relay_type === "exec_exit") {
        setConnectionState("disconnected");
        term.writeln(`\r\nSession ended (exit code: ${data.code || 0})\r\n`);
        return;
      }
      if (data._relay_type === "exec_output") {
        term.write(String(data.data || ""));
      }
    };

    socket.on("containers:terminal:data", handleTerminalData);
    socket.emit(
      "containers:terminal:start",
      { container_key: containerKey, host_id: hostId, rows: 24, cols: 80 },
      (resp?: { session_id?: string }) => {
        if (!resp?.session_id) {
          setConnectionState("error");
          term.writeln("\r\n\x1b[31mFailed to open terminal session.\x1b[0m");
          return;
        }
        sessionIdRef.current = resp.session_id;
      }
    );

    const inputDisposable = term.onData((data) => {
      if (sessionIdRef.current) {
        socket.emit("containers:terminal:input", { session_id: sessionIdRef.current, data });
      }
    });
    const resizeDisposable = term.onResize(() => sendResize());

    return () => {
      inputDisposable.dispose();
      resizeDisposable.dispose();
      if (sessionIdRef.current) {
        socket.emit("containers:terminal:stop", { session_id: sessionIdRef.current });
      }
      sessionIdRef.current = null;
      socket.off("containers:terminal:data", handleTerminalData);
      term.dispose();
      termInstance.current = null;
      fitAddonRef.current = null;
    };
  }, [containerKey, hostId, sendResize, socket]);

  useEffect(() => {
    if (fitAddonRef.current && dimensions.width > 0 && dimensions.height > 0) {
      fitAddonRef.current.fit();
      sendResize();
    }
  }, [dimensions, sendResize]);

  return (
    <div ref={containerRef} className={`relative h-full w-full overflow-hidden ${className}`}>
      <div className="absolute right-2 top-2 z-10">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
            connectionState === "connected"
              ? "bg-success/20 text-success"
              : connectionState === "connecting"
                ? "bg-warning/20 text-warning"
                : "bg-error/20 text-error"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              connectionState === "connected"
                ? "bg-success animate-pulse"
                : connectionState === "connecting"
                  ? "bg-warning animate-pulse"
                  : "bg-error"
            }`}
          />
          {connectionState === "connected"
            ? "Live"
            : connectionState === "connecting"
              ? "Connecting"
              : "Disconnected"}
        </span>
      </div>

      <div ref={terminalRef} className="h-full w-full" style={{ backgroundColor: TERMINAL_BACKGROUND }} />
    </div>
  );
}

export default TerminalView;

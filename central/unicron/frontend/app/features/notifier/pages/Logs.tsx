import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Button,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import type { LogEntry } from '../types';
import { notifierApi } from '../services/api';

function Logs() {
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const logsContainerRef = useRef<HTMLDivElement>(null);
  const theme = useTheme();

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await notifierApi.getLogs();
      setLogEntries(response.logs);
    } catch (error) {
      console.error('Failed to fetch logs:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Auto-refresh every 20 seconds
  useEffect(() => {
    const intervalId = setInterval(() => {
      fetchLogs();
    }, 20000);
    return () => clearInterval(intervalId);
  }, [fetchLogs]);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight;
    }
  }, [logEntries]);

  const escapeHtml = (unsafe: string | null | undefined): string => {
    if (unsafe === null || unsafe === undefined) return '';
    return unsafe
      .toString()
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  };

  const getLogLevelStyle = (level: string): React.CSSProperties => {
    switch (level) {
      case 'DEBUG':
        return { color: theme.palette.text.secondary };
      case 'INFO':
        return { color: theme.palette.success.main };
      case 'WARNING':
        return { color: theme.palette.warning.main };
      case 'ERROR':
        return { color: theme.palette.error.main };
      case 'CRITICAL':
        return { color: theme.palette.error.main, fontWeight: 'bold' };
      default:
        return {};
    }
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
        <Button variant="outlined" onClick={fetchLogs} disabled={isLoading}>
          Refresh
        </Button>
      </Box>

      <TableContainer
        component={Paper}
        ref={logsContainerRef}
        sx={{
          maxHeight: '75vh',
          overflowY: 'auto',
          '& .MuiTableCell-root:not(:last-of-type)': {
            borderRight: `1px solid ${theme.palette.divider}`,
          },
        }}
      >
        <Table stickyHeader size="small" id="logsTable">
          <TableHead>
            <TableRow>
              <TableCell sx={{ width: '1%', whiteSpace: 'nowrap' }}>Timestamp</TableCell>
              <TableCell sx={{ width: '1%', whiteSpace: 'nowrap' }}>Level</TableCell>
              <TableCell>Message</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {logEntries.map((log, index) => (
              <TableRow key={log.id || index} hover>
                <TableCell sx={{ width: '1%', whiteSpace: 'nowrap' }}>
                  {log.timestamp}
                </TableCell>
                <TableCell
                  sx={{
                    width: '1%',
                    whiteSpace: 'nowrap',
                    fontWeight: 600,
                    ...getLogLevelStyle(log.level),
                  }}
                >
                  {log.level}
                </TableCell>
                <TableCell>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: '200px',
                      overflowY: 'auto',
                      background: 'transparent',
                      borderRadius: 1,
                      fontSize: '0.95em',
                    }}
                    dangerouslySetInnerHTML={{ __html: escapeHtml(log.message) }}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

export default Logs;

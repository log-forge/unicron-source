import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  TextField,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Stack,
} from '@mui/material';
import type { LogEntry } from '../types';
import { notifierApi } from '../services/api';

function Dashboard() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [filteredLogs, setFilteredLogs] = useState<LogEntry[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await notifierApi.getLogs();
      setLogs(response.logs);
    } catch (error) {
      console.error('Failed to fetch notification logs:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  // Update filtered list when logs change
  useEffect(() => {
    setFilteredLogs(logs);
  }, [logs]);

  // Auto-refresh every 20 seconds
  useEffect(() => {
    const intervalId = setInterval(() => {
      fetchLogs();
    }, 20000);
    return () => clearInterval(intervalId);
  }, [fetchLogs]);

  const handleFilter = () => {
    let filtered = logs;

    if (startDate && endDate) {
      const start = new Date(`${startDate}T00:00:00`);
      start.setHours(0, 0, 0, 0);
      const end = new Date(`${endDate}T23:59:59.999`);
      filtered = filtered.filter((notif) => {
        const notifDate = new Date(notif.timestamp);
        return notifDate >= start && notifDate <= end;
      });
    }
    if (statusFilter) {
      filtered = filtered.filter(
        (log) => (log.status || '').toLowerCase().includes(statusFilter.toLowerCase()),
      );
    }

    setFilteredLogs(filtered);
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={2}
        alignItems={{ xs: 'stretch', md: 'flex-end' }}
        justifyContent="flex-end"
        flexWrap="wrap"
        sx={{ gap: { xs: 2, md: 2.5 } }}
      >
        <Stack
          direction={{ xs: 'column', lg: 'row' }}
          spacing={2}
          flexWrap="wrap"
          sx={{ gap: { xs: 2, md: 2 } }}
        >
          <TextField
            id="startDateFilter"
            label="From"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
            size="small"
            sx={{ minWidth: { xs: '100%', sm: 200 } }}
          />
          <TextField
            id="endDateFilter"
            label="To"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            slotProps={{ inputLabel: { shrink: true } }}
            size="small"
            sx={{ minWidth: { xs: '100%', sm: 200 } }}
          />
          <TextField
            id="statusFilter"
            label="Status"
            placeholder="sent, failed, pending"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            size="small"
            sx={{ minWidth: { xs: '100%', sm: 220 } }}
          />
          <Button variant="contained" onClick={handleFilter} disabled={isLoading}>
            Apply
          </Button>
        </Stack>
      </Stack>

      <TableContainer
        component={Paper}
        sx={(theme) => ({
          overflowX: 'auto',
          '& .MuiTableCell-root:not(:last-of-type)': {
            borderRight: `1px solid ${theme.palette.divider}`,
          },
        })}
      >
        <Table id="notificationsTable" size="small">
          <TableHead>
            <TableRow>
              <TableCell>Timestamp</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Channel</TableCell>
              <TableCell>Message</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredLogs.map((log, index) => (
              <TableRow key={log.id || index} hover>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{log.timestamp}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  {log.status || log.level}
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  {log.channel_type || log.channel_id || 'N/A'}
                </TableCell>
                <TableCell>
                  <Box
                    component="pre"
                    sx={{
                      m: 0,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: 220,
                      overflowY: 'auto',
                    }}
                  >
                    {log.message}
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}

export default Dashboard;

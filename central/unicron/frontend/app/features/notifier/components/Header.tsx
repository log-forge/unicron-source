import React, { useState } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Box,
  Tabs,
  Tab,
  Menu,
  MenuItem,
  Avatar,
  Divider,
} from '@mui/material';
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import PersonIcon from '@mui/icons-material/Person';
import HomeIcon from '@mui/icons-material/Home';

/**
 * Tab configuration for navigation
 */
export interface TabConfig {
  value: string;
  label: string;
}

/**
 * Current user information for the header
 */
export interface CurrentUser {
  email?: string;
  role?: string;
}

/**
 * Header component props
 */
interface HeaderProps {
  toggleTheme: () => void;
  theme: 'light' | 'dark';
  activeTab: string;
  onTabChange: (event: React.SyntheticEvent, newValue: string) => void;
  tabs?: TabConfig[];
  currentUser?: CurrentUser | null;
}

/**
 * Notifier header component with navigation tabs, theme toggle, and user menu.
 * Ported from LogForge notifier/web/src/components/Header/Header.jsx
 */
function Header({
  toggleTheme,
  theme,
  activeTab,
  onTabChange,
  tabs = [],
  currentUser,
}: HeaderProps): React.ReactElement | null {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const menuOpen = Boolean(anchorEl);

  const handleUserClick = (event: React.MouseEvent<HTMLElement>): void => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = (): void => {
    setAnchorEl(null);
  };

  const handleReturnToHome = (): void => {
    // Navigate to home page in Unicron
    window.location.href = '/alerting';
  };

  return (
    <AppBar
      position="static"
      color="transparent"
      elevation={0}
      sx={(themeObj) => ({
        backgroundColor: themeObj.palette.background.header,
        borderBottom: `1px solid ${themeObj.palette.divider}`,
      })}
    >
      <Toolbar
        disableGutters
        sx={{
          px: { xs: 2, md: 3 },
          minHeight: 64,
          gap: { xs: 2, md: 3 },
        }}
      >
        {/* Logo and Title */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
          <Box
            sx={(themeObj) => ({
              width: 28,
              height: 28,
              borderRadius: 1,
              backgroundColor: themeObj.palette.logoBackground,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
              fontSize: '0.875rem',
              color: themeObj.palette.logoText,
            })}
          >
            N
          </Box>
          <Typography
            variant="h6"
            component="h1"
            sx={{ fontWeight: 600, whiteSpace: 'nowrap' }}
          >
            Notifier
          </Typography>
        </Box>

        {/* Navigation Tabs */}
        <Tabs
          value={activeTab}
          onChange={onTabChange}
          aria-label="Navigation tabs"
          textColor="inherit"
          indicatorColor="primary"
          sx={{
            flexGrow: 1,
            minHeight: 44,
            '& .MuiTab-root': {
              minWidth: 0,
              px: { xs: 1.5, md: 2.5 },
            },
          }}
        >
          {tabs.map((tab) => (
            <Tab key={tab.value} label={tab.label} value={tab.value} />
          ))}
        </Tabs>

        {/* Theme Toggle */}
        <IconButton
          onClick={toggleTheme}
          aria-label="Toggle theme"
          id="themeToggle"
          size="small"
          sx={(themeObj) => ({
            color: themeObj.palette.text.primary,
            border: `1px solid ${themeObj.palette.divider}`,
            borderRadius: 999,
            width: 40,
            height: 40,
          })}
        >
          {theme === 'dark' ? <Brightness7Icon /> : <Brightness4Icon />}
        </IconButton>

        {/* User Menu */}
        {currentUser && (
          <>
            <IconButton
              onClick={handleUserClick}
              size="small"
              sx={(themeObj) => ({
                color: themeObj.palette.text.primary,
                border: `1px solid ${themeObj.palette.divider}`,
                borderRadius: 999,
                ml: 1,
              })}
              aria-controls={menuOpen ? 'user-menu' : undefined}
              aria-haspopup="true"
              aria-expanded={menuOpen ? 'true' : undefined}
            >
              <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main' }}>
                {currentUser.email?.[0]?.toUpperCase() || <PersonIcon />}
              </Avatar>
            </IconButton>
            <Menu
              id="user-menu"
              anchorEl={anchorEl}
              open={menuOpen}
              onClose={handleClose}
              anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
              transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            >
              <Box sx={{ px: 2, py: 1 }}>
                <Typography variant="body2" fontWeight={600}>
                  {currentUser.email}
                </Typography>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ textTransform: 'capitalize' }}
                >
                  {currentUser.role}
                </Typography>
              </Box>
              <Divider />
              <MenuItem
                onClick={() => {
                  handleClose();
                  handleReturnToHome();
                }}
              >
                <HomeIcon sx={{ mr: 1, fontSize: 20 }} />
                Return to Home
              </MenuItem>
            </Menu>
          </>
        )}
      </Toolbar>
    </AppBar>
  );
}

export default Header;

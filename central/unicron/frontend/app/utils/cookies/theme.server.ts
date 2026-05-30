import { createCookie } from 'react-router';

// Define theme types
export type Theme = 'dark' | 'light' | 'system' | string;

// Create a cookie for storing the theme preference
export const themeCookie = createCookie('theme', {
  path: '/',
  httpOnly: true,
  sameSite: 'lax',
  secure: process.env.VITE_NODE_ENV === 'production',
  maxAge: 60 * 60 * 24 * 365, // 1 year
});

/**
 * Retrieves the theme preference from the request cookies.
 *
 * @param {Request} request - The incoming request object.
 * @returns {Promise<Theme>} A promise that resolves to the theme preference.
 */
export async function getTheme(request: Request): Promise<Theme> {
  const cookieHeader = request.headers.get('Cookie');
  const theme = await themeCookie.parse(cookieHeader);
  return theme || 'system';
}

/**
 * Sets the theme by serializing it into a cookie.
 *
 * @param {Theme} theme - The theme to be serialized.
 * @returns {Promise<string>} A promise that resolves to the serialized theme cookie string.
 */
export async function setTheme(theme: Theme): Promise<string> {
  console.log('Setting theme cookie value:', theme);
  console.log('Theme type:', typeof theme);

  // Make sure theme is a string and not an object
  const themeValue = typeof theme === 'string' ? theme : String(theme);

  const serialized = await themeCookie.serialize(themeValue);
  console.log('Serialized cookie:', serialized);

  return serialized;
}

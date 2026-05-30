import { getHintUtils } from '@epic-web/client-hints';
import { useRevalidator } from 'react-router';
import { clientHint as colorSchemeHint, subscribeToSchemeChange } from '@epic-web/client-hints/color-scheme';
import { useEffect } from 'react';

const hintsUtils = getHintUtils({
  theme: colorSchemeHint,
});

const colorSchemeCookieScript = `
(function () {
  try {
    if (!navigator.cookieEnabled || !window.matchMedia) return;
    var theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    document.cookie = 'CH-prefers-color-scheme=' + encodeURIComponent(theme) + '; Max-Age=31536000; SameSite=Lax; path=/';
  } catch (error) {
    console.warn('Failed to store color scheme hint:', error);
  }
})();
`;

// Create a component to detect and update client hints
export function ClientHintCheck() {
  const { revalidate } = useRevalidator();

  useEffect(() => subscribeToSchemeChange(() => revalidate()), [revalidate]);

  return (
    <script
      dangerouslySetInnerHTML={{
        __html: colorSchemeCookieScript,
      }}
    />
  );
}

// Export getHints for use in loaders
export const { getHints } = hintsUtils;

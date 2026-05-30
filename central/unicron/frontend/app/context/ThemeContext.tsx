import { createContext, useContext, useState, useEffect } from "react";
import { useHref } from "react-router";
import type { Theme } from "../utils/cookies/theme.server";

const themes = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

type ThemeContextType = {
  theme: Theme;
  actualTheme: "light" | "dark"; // Added this to expose the actual applied theme
  setTheme: (newTheme: Theme) => Promise<void>;
  toggleTheme: () => Promise<void>;
  settingTheme: boolean;
};

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

/**
 * ThemeProvider component that provides theme context to its children.
 *
 * @param {Object} props - The props object.
 * @param {React.ReactNode} props.children - The child components to be wrapped by the provider.
 * @param {Theme} props.initialTheme - The initial theme to be applied.
 *
 * @returns {JSX.Element} The ThemeContext provider with theme management logic.
 *
 * @remarks
 * This component manages the theme state and applies the appropriate theme to the document.
 * It also listens for system preference changes if the theme is set to "system".
 * The theme state is stored in a cookie via an API call.
 *
 * @example
 * ```tsx
 * <ThemeProvider initialTheme="light">
 *   <App />
 * </ThemeProvider>
 * ```
 */
export function ThemeProvider({ children, initialTheme }: { children: React.ReactNode; initialTheme: Theme }) {
  const [themeState, setThemeState] = useState<Theme>(initialTheme);
  const [actualTheme, setActualTheme] = useState<"light" | "dark">("dark");
  const [settingTheme, setSettingTheme] = useState<boolean>(false);
  const themeSwitchUrl = useHref("/resources/theme-switch");

  // Apply theme data attribute to the document
  useEffect(() => {
    console.log("Applying theme:", themeState);
    const root = window.document.documentElement;

    // Handle system preference
    if (themeState === "system") {
      const systemPreference = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
      root.setAttribute("data-theme", systemPreference);
      setActualTheme(systemPreference);
    } else {
      // Handle dark or light theme
      root.setAttribute("data-theme", themeState);
      setActualTheme(themeState as "light" | "dark");
    }
  }, [themeState]);

  // Listen for system preference changes if using system theme
  useEffect(() => {
    if (themeState !== "system") return;

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = () => {
      const root = window.document.documentElement;
      const newActualTheme = mediaQuery.matches ? "dark" : "light";
      root.setAttribute("data-theme", newActualTheme);
      setActualTheme(newActualTheme);
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [themeState]);

  // Function to update the theme
  const updateTheme = async (newTheme: Theme) => {
    // Update state
    setSettingTheme(true);
    setThemeState(newTheme);
    console.log("Setting new theme:", newTheme);

    try {
      // Store in cookie
      const response = await fetch(themeSwitchUrl, {
        method: "POST",
        body: JSON.stringify({ theme: newTheme }),
        headers: {
          "Content-Type": "application/json",
        },
      });
      if (!response.ok) {
        console.error("Failed to update theme cookie:", response.status);
      }
      console.log("Theme cookie updated successfully", response);
    } catch (error) {
      console.error("Error updating theme:", error);
    } finally {
      setSettingTheme(false);
    }
  };

  // Function to toggle between system, light, and dark themes
  const toggleTheme = async () => {
    const currentIndex = themes.findIndex((t) => t.value === themeState);
    const nextIndex = (currentIndex + 1) % themes.length;
    const nextTheme = themes[nextIndex].value;

    await updateTheme(nextTheme as Theme);
  };

  return (
    <ThemeContext.Provider
      value={{
        theme: themeState,
        actualTheme, // Expose the actual theme that's applied
        setTheme: updateTheme,
        toggleTheme,
        settingTheme,
      }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

/**
 * Custom hook to access the theme context.
 *
 * This hook must be used within a `ThemeProvider`. If used outside of a `ThemeProvider`,
 * it will throw an error.
 *
 * @returns {ThemeContextType} The current theme context value.
 * @throws {Error} If the hook is used outside of a `ThemeProvider`.
 */
export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) throw new Error("useTheme must be used within a ThemeProvider");

  return context;
}

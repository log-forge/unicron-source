/**
 * Monaco Editor Language Mapping
 *
 * Maps file extensions to Monaco editor language identifiers
 * for syntax highlighting.
 */

export const extensionToMonacoLang: Record<string, string> = {
  // JavaScript/TypeScript
  js: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  mjs: "javascript",
  cjs: "javascript",

  // Web
  html: "html",
  htm: "html",
  css: "css",
  scss: "scss",
  less: "less",

  // Data formats
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  xml: "xml",
  toml: "toml",

  // Config
  ini: "ini",
  conf: "ini",
  cfg: "ini",
  env: "shell",

  // Scripts
  sh: "shell",
  bash: "shell",
  zsh: "shell",
  fish: "shell",
  ps1: "powershell",

  // Python
  py: "python",
  pyw: "python",

  // Go
  go: "go",

  // Rust
  rs: "rust",

  // C/C++
  c: "c",
  h: "c",
  cpp: "cpp",
  hpp: "cpp",
  cc: "cpp",
  cxx: "cpp",

  // Java/JVM
  java: "java",
  kt: "kotlin",
  scala: "scala",
  groovy: "groovy",

  // .NET
  cs: "csharp",
  fs: "fsharp",

  // Ruby
  rb: "ruby",
  erb: "html",

  // PHP
  php: "php",

  // SQL
  sql: "sql",

  // Docker
  dockerfile: "dockerfile",

  // Markdown
  md: "markdown",
  mdx: "markdown",

  // Text
  txt: "plaintext",
  log: "plaintext",
};

/**
 * Detect Monaco editor language from filename
 */
export function detectMonacoLanguage(filename: string): string {
  // Handle special filenames without extensions
  const lowerName = filename?.toLowerCase() || "";
  if (lowerName === "dockerfile" || lowerName.startsWith("dockerfile.")) {
    return "dockerfile";
  }
  if (lowerName === "makefile") {
    return "makefile";
  }

  // Extract extension
  const ext = filename?.split(".").pop()?.toLowerCase() || "";
  return extensionToMonacoLang[ext] || "plaintext";
}

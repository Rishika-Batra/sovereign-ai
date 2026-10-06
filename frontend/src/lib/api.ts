/**
 * Returns the API base URL for all fetch calls.
 *
 * - In Docker (production / nginx-proxied), NEXT_PUBLIC_API_URL is set to ""
 *   so all calls use a relative path (e.g. "/api/...") and go through NGINX.
 * - In local development outside Docker, NEXT_PUBLIC_API_URL is unset, so
 *   the fallback is "" which still works via the Next.js dev server proxy,
 *   OR a developer can set NEXT_PUBLIC_API_URL=http://localhost:8000 in
 *   .env.local to bypass NGINX entirely.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

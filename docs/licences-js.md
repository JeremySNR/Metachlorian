# JavaScript dependency licences

Production dependencies (direct and transitive) of the web app (`app/`, bundled into the core's static files) and the desktop shell (`desktop/`). Generated with `npm ls --omit=dev --all` and each package's `license` field; development-only tooling (Vite, TypeScript, ESLint, Playwright, Vitest, electron-builder) is not shipped and not listed. Electron itself is MIT and bundles Chromium (BSD-3-Clause and others, see Electron's LICENSES.chromium.html in each installer).

| Licence | Packages |
|---|---|
| MIT | 21 |
| Apache-2.0 | 8 |
| OFL-1.1 | 2 |
| Unlicense | 1 |
| ISC | 1 |
| 0BSD | 1 |

| Package | Version | Licence | Used by |
|---|---|---|---|
| @fontsource-variable/instrument-sans | 5.3.0 | OFL-1.1 | app |
| @fontsource-variable/jetbrains-mono | 5.3.0 | OFL-1.1 | app |
| @internationalized/date | 3.12.4 | Apache-2.0 | app |
| @internationalized/number | 3.6.8 | Apache-2.0 | app |
| @internationalized/string | 3.2.10 | Apache-2.0 | app |
| @react-types/shared | 3.36.1 | Apache-2.0 | app |
| @swc/helpers | 0.5.23 | Apache-2.0 | app |
| @tanstack/history | 1.162.4 | MIT | app |
| @tanstack/query-core | 5.104.1 | MIT | app |
| @tanstack/react-query | 5.104.1 | MIT | app |
| @tanstack/react-router | 1.170.41 | MIT | app |
| @tanstack/react-store | 0.11.2 | MIT | app |
| @tanstack/react-virtual | 3.14.13 | MIT | app |
| @tanstack/router-core | 1.171.34 | MIT | app |
| @tanstack/store | 0.11.2 | MIT | app |
| @tanstack/virtual-core | 3.17.11 | MIT | app |
| @types/react | 19.3.0 | MIT | app |
| aria-hidden | 1.2.6 | MIT | app |
| client-only | 0.0.1 | MIT | app |
| clsx | 2.1.1 | MIT | app |
| cookie-es | 3.1.1 | MIT | app |
| csstype | 3.2.3 | MIT | app |
| isbot | 5.2.2 | Unlicense | app |
| lucide-react | 1.51.0 | ISC | app |
| react | 19.3.0 | MIT | app |
| react-aria | 3.52.1 | Apache-2.0 | app |
| react-aria-components | 1.21.1 | Apache-2.0 | app |
| react-dom | 19.3.0 | MIT | app |
| react-stately | 3.50.0 | Apache-2.0 | app |
| seroval | 1.6.8 | MIT | app |
| seroval-plugins | 1.6.8 | MIT | app |
| tslib | 2.8.1 | 0BSD | app |
| use-sync-external-store | 1.7.0 | MIT | app |
| zustand | 5.0.15 | MIT | app |

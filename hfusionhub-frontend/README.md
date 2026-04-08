# HFusionHub Frontend

Vue 3 + TypeScript + Vite SPA with Tailwind CSS and Radix Vue.

## Development

```bash
npm ci                  # Install dependencies
npm run dev             # Start dev server (http://localhost:3000)
npm run build           # Type-check + production build
npm run preview         # Preview production build
```

## Tech Stack

- **Framework**: Vue 3.5 + Composition API
- **Language**: TypeScript 6.0
- **Build**: Vite 8
- **Styling**: Tailwind CSS 4
- **UI Primitives**: Radix Vue
- **State**: Pinia 4
- **Router**: Vue Router 4
- **HTTP**: Axios (with Sa-Token header injection)

## Project Structure

```
src/
├── api/            # Axios API modules (auth, kb, doc, conversation, agent, …)
├── components/     # Shared Vue components (MarkdownRenderer, Toast, …)
├── pages/          # Route pages (Login, Chat, Dashboard, Knowledge, …)
├── router/         # Vue Router config with auth guard
├── stores/         # Pinia stores
└── utils/          # Utilities
```

The Vite dev server proxies `/api` requests to `http://localhost:8080` (Java backend).

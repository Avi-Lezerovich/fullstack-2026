# The client

React 18 + TypeScript + Vite + MUI 5, in Hebrew and right-to-left.
[`client/`](../client/). Dev server on port 5174; `/api` is proxied to the Flask server
on 5002.

```
client/src/
  main.tsx        providers: emotion RTL cache, theme, router, auth, notifications
  App.tsx         the route table
  api.ts          the ONLY place this app talks to the network
  types.ts        the shapes the API returns
  theme.ts        the courtroom palette, direction: "rtl"
  context/        AuthContext, NotificationContext
  hooks/          useAsync, usePagedList, useNotificationStream
  pages/          one component per route
  components/     admin/ assist/ case/ comments/ common/ feed/ layout/ moderation/ routing/ trial/
  test/setup.ts   vitest + @testing-library setup
```

---

## 1. Bootstrapping and RTL

[`main.tsx`](../client/src/main.tsx) wraps the app in, from the outside in: an Emotion
`CacheProvider` with an RTL stylis cache, `ThemeProvider` + `CssBaseline`,
`BrowserRouter`, `AuthProvider`, `NotificationProvider`.

Emotion has to be told about RTL **separately from MUI**: the theme's `direction: "rtl"`
flips MUI's own logic, but the generated CSS still needs its physical properties
mirrored, which is what `stylis-plugin-rtl` does.

[`theme.ts`](../client/src/theme.ts) is the visual identity — a courtroom as parchment
and brass: Court Purple `#3C3489`, brass `#B8860B`, plus the Verdict Red / Acquittal
Green pair the verdict banner and jury panel use.

## 2. Routes

From [`App.tsx`](../client/src/App.tsx). `ProtectedRoute` wraps the three that require a
session; everything else renders for anonymous visitors too.

| Path | Page | Protected |
|---|---|---|
| `/` | `Feed` | |
| `/cases/new` | `NewCase` | ✔ |
| `/cases/:caseId` | `CasePage` | |
| `/users` | `Users` | |
| `/users/:userId` | `Profile` | |
| `/messages` | `Messages` | ✔ |
| `/admin` | `AdminDashboard` | ✔ |
| `/about` | `About` | |
| `/login`, `/signup`, `/forgot-password`, `/reset-password` | auth pages | |
| `*` | `NotFound` | |

The whole tree sits inside an `AppErrorBoundary`, and `ErrorPage` renders the branded
failure states.

## 3. `api.ts` — the single network seam

**No component calls `fetch` directly.** Everything goes through `request<T>`, so
credentials handling, JSON parsing and error translation exist once rather than in thirty
components.

- `credentials: "include"` on every call — authentication is an httpOnly cookie, and
  without this the browser will not attach it and every request looks anonymous.
- Failures throw an **`ApiError`** carrying the HTTP `status` *and* the server's own
  `code` (`unauthorized`, `rejected`, `closed`, …) plus its Hebrew `error` string — so a
  caller's `catch` already has something worth showing a user, and `usePagedList` /
  `useAsync` can branch on the code where it matters.
- `BASE = "/api"`, resolved by Vite's dev proxy locally and by nginx in the container.

## 4. Contexts

- **`AuthContext`** — who is signed in, in one place. The session is an httpOnly cookie
  JavaScript cannot read, so the only way to know the current user is to ask the server:
  the provider calls `/auth/me` once on mount and keeps the answer, exposing `user`,
  `loading` (true until that first call settles — render nothing decisive before then),
  `signIn`, `register`, `signOut`. An earlier version mirrored the user into
  `localStorage` and broadcast a window event to keep components in sync; a context is
  simpler and cannot drift from the real cookie.
- **`NotificationContext`** — every notification, in one place. There is exactly **one**,
  mounted at the root, and that is the point: the stream is a real network connection and
  the unread counter is real state, so a second copy would open a second `EventSource`
  for the same user and count every row twice. The bell, the inbox badge and the Messages
  page all read from here.

## 5. Hooks

| Hook | What it does |
|---|---|
| `useAsync(loader, deps, intervalMs?)` | fetch → spinner → the server's Hebrew error, once instead of on every page. Has a stale guard, so navigating between two cases quickly cannot let the first response overwrite the second. `intervalMs` re-runs it in the background for live status views, reusing the same guard. |
| `usePagedList(fetchPage, deps)` | An accumulating list: first page on mount, more on request. The point is what it does *not* do — both lists used to "load more" by asking for a larger `limit` from offset 0 and replacing everything, so the fifth page cost five pages of traffic. Changing `deps` (a search term, a filter tab) discards and restarts. |
| `useNotificationStream({enabled, since, onNotification})` | Live notifications over SSE where it works, polling (10s) where it does not. Both transports call the identical callback and advance the same `notifications.id` cursor, so every consumer is transport-agnostic. Two failures inside 30s means SSE is not working here, and the fallback is permanent for the session rather than retried forever. |

## 6. Components

| Folder | Contents |
|---|---|
| `layout/` | `TopBar`, `Footer`, `NotificationBell`, `MessagesLink` |
| `feed/` | `CaseCard` |
| `case/` | `CaseStatusChip`, `PhaseTimeline`, `VerdictBanner`, `CourtSeal`, `LikeButton`, `FollowButton`, `FollowersDialog`, `LikersDialog`, `FollowedCasesDialog` |
| `trial/` | `JuryPanel`, `WitnessList`, `SummonWitnessDialog`, `TestifyForm`, `MySummonsPanel` |
| `comments/` | `CommentThread`, `CommentComposer`, `RoleBadge` (the badge is what turns one `comments` table into four visibly different kinds of utterance) |
| `moderation/` | `ReportButton`, `BannedUsers`, `CourtStatus` |
| `admin/` | `SiteOverview`, `AiUsage`, `SystemHealth` — the three dashboard tabs, backed by `/api/admin/overview`, `/api/admin/brain/usage` and `/api/health` |
| `assist/` | `AssistButton`, `AssistDialog` — the `/api/assist/*` writing help |
| `common/` | `AppErrorBoundary`, `ErrorPage`, `StateViews`, `InfiniteScroll`, `ImageUploadField`, `UserListDialog`, `CourtRecord` |
| `routing/` | `ProtectedRoute` |

## 7. Tests and tooling

Vitest + Testing Library, jsdom, with `*.test.tsx` files sitting beside the source they
cover and shared setup in `src/test/setup.ts`.

```bash
npm run dev            # Vite on 5174, /api proxied to 5002
npm run lint           # tsc --noEmit
npm test               # vitest run
npm run test:coverage  # v8 coverage
npm run build          # tsc -b && vite build
```

The dev proxy streams responses unbuffered, which is what lets the SSE notification
stream work in development. See [TESTING.md](../TESTING.md) for the full test story
across both tiers.

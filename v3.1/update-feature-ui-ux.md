

Ringkasan tujuan singkat
Buat ulang antarmuka Telegram Bot dan Web Dashboard agar menyerupai “Investigative Command Center”: profesional, gelap, minimalis, responsif, dan interaktif. Integrasikan UX bot yang elegan (progress edits, MarkdownV2 report) dengan backend (Firestore, Cloud Run, Gemini, DeepSeek) dan dashboard Flask/Jinja2/Tailwind+Alpine.js agar user flow dan data presentation konsisten.

---

A. Prinsip desain umum (untuk semua deliverable)

* Tema visual: dark slate/zinc, kontras moderat, tipografi sans-serif (Inter/Roboto). Gunakan glow halus pada elemen penting, bukan warna neon berlebihan.
* Bahasa: formal, ringkas, “intelligence brief” tone — gunakan MarkdownV2 pada bot (bold, inline code, fenced code blocks), dan visual hierarchy kuat di web.
* No emojis “facebook mom”; jika perlu ikon, gunakan monospace markers seperti `[SYSTEM]`, `[VISION]`, `[DATA]`.
* Error-first: setiap permintaan async harus menunjukkan loading → partial-progress → final or graceful-failure message.
* Audit & telemetry: setiap interaction (bot command, map click, settings change) log ke Firestore atau monitoring service (Cloud Logging).

---

B. Telegram Bot UX overhaul (file-target: bot/handlers.py, bot/formatter.py)

1. Tone & formatting rules (formatter)

   * Gunakan MarkdownV2 strict: define template variables and require escaping of `_.[]()~` etc. Document exact escape helper to use.
   * Final report structure MUST use these section headers (literal, uppercase, bracketed):
     `[FINANCIALS]` — price, monthly cost breakdown, assumptions (deposit, utilities).
     `[LOGISTICS]` — distance, transit, routes, nearest POI.
     `[RISK ASSESSMENT]` — DeepSeek/Gemini flags, fraud indicators (e.g., image tampering, text inconsistency).
     `[VERDICT]` — short single-line recommendation (GREEN / CAUTION / AVOID) plus reason.
   * Each numeric value show source tag (e.g., `price: 750000 (scraper)`) inside inline code block.
   * Error states: include `[WARNING]` section with machine-readable `code:` line explaining error and suggested next steps (retry, manual link).
   * Example of content blocks (no emoji): use bold for headers, fenced code blocks for raw data payloads, blockquotes for analyst notes.

2. Dynamic loading / progressive edits (handlers)

   * On image/text submit: immediately `send_message` a minimal boot message with code-like header:
     ` [SYSTEM] Booting God Eye Engine...`
   * Then sequentially `edit_message_text` to update progress checkpoints. Suggested checkpoint sequence and meaning:

     1. `[SYSTEM] Initializing models` (validate credentials, Rate limits)
     2. `[VISION] Gemini analyzing imagery` (send small preview or thumbnail as separate message if allowed)
     3. `[DATA] Aggregating sources (Maps, Scrapers, Firestore)`
     4. `[ANALYSIS] DeepSeek scoring & correlation`
     5. Final: replace with full formatted report from formatter.
   * Each edit must include an ETA-like textual progress (e.g., `Step 3/5`) and a short spinner glyph set made from ASCII (no emoji).
   * Implement cancellation/timeouts: if analysis > 60s, post a warning edit with possible actions (retry, queue, manual link).
   * Keep user informed of errors: if any external API fails (Maps, Gemini), the message should be edited to show `[WARNING] Google Maps API timeout — routing unavailable.` and then attempt to return partial report.

3. UX details for handlers

   * Ensure messages are idempotent: if handler restarts, detect prior message and update it rather than posting duplicates (store message_id in transient Firestore doc keyed by user/session).
   * Constrain edit frequency to avoid hitting Telegram rate limits (max ~30 edits/min). Group small updates.
   * Provide a final quick-action inline keyboard under the report with options: `Open Dashboard`, `Save to Watchlist`, `Re-analyze`. Buttons must open web URLs or trigger bot callbacks.

4. Formatter output specifics

   * Provide a plain-text + MarkdownV2 template skeleton (document the placeholder fields). Template should:

     * Start with a single-line metadata block (timestamp, listing id, source).
     * Present `[FINANCIALS]` with a 1-line summary and code block of the raw price object.
     * Present `[LOGISTICS]` with bullet-like lines (use `-` as plain text inside MarkdownV2).
     * Present `[RISK ASSESSMENT]` with colored verbal verdict (GREEN/CAUTION/RED ideally words only) and numbered flagged items.
     * End with `[VERDICT]` short recommendation and actionable next steps (link to dashboard detail page).
   * Include instructions for escaping special chars and how to wrap raw JSON in triple backticks to keep MarkdownV2 safe.

---

C. Web Dashboard overhaul (Flask: templates/web/templates/*)
General stack: Flask + Jinja2 + Tailwind CDN + Alpine.js CDN + Chart.js CDN.

1. Base layout (base.html)

   * Include Tailwind CSS via CDN and link to Inter/Roboto fonts. Include Alpine.js and Chart.js via CDN.
   * Global layout: top nav bar (compact), left collapsible sidebar with filters (score, price, area), main content area for listing grid and map.
   * Provide dark palette CSS variables using Tailwind classes and small inline style for glow effect on focused cards.
   * Provide global Alpine store for selected listing id and loading state.

2. Index page (index.html) — Command Center overview

   * Header: quick stats row (total listings, flagged count, avg score). Use small cards with subtle glow if flagged count > 0.
   * Filters: price range slider, score range slider, area multiselect, quick toggles for `show flagged only`. Use Alpine.js to debounce filter changes.
   * Listing grid: cards with image, small metadata line, score badge (circular progress) and small risk tag. Clicking card sets `selectedListing` (Alpine) and scrolls to detail pane.
   * Skeleton loaders: when filters change, overlay skeleton placeholders on the grid and map; implement skeletons as animated gray gradients via Tailwind utility classes.
   * Map panel (Google Maps embed):

     * Load markers from current filtered dataset. Marker icon color rules: score > 80 = green, 50–80 = amber, <50 = red. Provide legend.
     * Clicking marker sets `selectedListing` and programmatically highlights corresponding card (use Alpine custom events).
     * Map -> listing interaction must be two-way.

3. Detail page/modal (detail.html) — Listing Command Card

   * Layout: two-column grid on desktop (images + gallery on left; metrics, radar chart, progress bar, notes on right). On mobile, stack vertically.
   * Score visualization: circular progress bar (CSS) + numeric. Also show a 0–100 horizontal progress bar with numeric overlay.
   * Radar chart: use Chart.js (cdn) to show Area / Price / Room Quality / Accessibility / Risk as axes. Provide fallbacks if Chart.js fails.
   * Why breakdown: a collapsible section `Why this score?` listing discrete reasons produced by DeepSeek/Gemini with severity badges (low/medium/high). High severity items should show red banner at top `FRAUD RISK: ...`.
   * Image gallery: simple carousel using Alpine.js — thumbnails underneath, click to expand lightbox (no external heavy libs).
   * Action bar (sticky bottom): `Open in Telegram`, `Save to Watchlist`, `Report Issue`. Buttons use small glow and confirm toasts.
   * Accessibility: keyboard focus states, alt text for images, sufficient contrast ratios.

4. Data flow & API endpoints

   * Endpoint to fetch filtered listing JSON (paginated). Return both listings and map markers in same payload. Include an `etag` or `last_updated` to enable minimal re-renders.
   * Web client should debounce filter changes (300–500ms) and display skeletons during fetch.
   * Provide endpoint to fetch single listing detail (for detail modal). If any field missing (e.g., routing), show “Not available — see warning” with reason.

5. Performance & deploy notes

   * Use Cloud Run autoscaled services for Flask backend. Enable gzip compression and caching for static assets (Tailwind via CDN mitigates local CSS weight).
   * For maps and charting, lazy-load libraries only when needed (e.g., load Chart.js when opening detail).
   * Protect Google Maps key via server proxy or restricted referrer keys.

---

D. Telegram advanced commands & ConversationHandler (main.py and handlers)

1. Command registration (main.py)

   * During app startup call `await application.bot.set_my_commands([...])` with commands: `/start`, `/help`, `/history`, `/settings`, `/clear`, `/stats`. Each command must have succinct descriptions aligned to investigator tone. Also register command scopes if needed.
   * Provide fallback: if `set_my_commands` fails due to rate limits, log and retry with exponential backoff.

2. `/start` & `/help`

   * Welcome: brief intelligence-brief style intro explaining inputs (send images, share links), what the bot returns, and quick commands list. Provide one-line example flows. Avoid emojis. Include links to the web dashboard and support.

3. `/history`

   * Query Firestore `kos_listings` for the user's last 3 analyzed listings (indexed by user_id or last_accessed_by). Return each as mini-summary: Score | Price | Area | short verdict line + direct link to dashboard detail. If no history, respond with a plain informative line.

4. `/clear`

   * Transactionally set `user_preferences.preferred_areas` and `.avoided_areas` to empty arrays. Confirm with short message on success. If the user has multiple Firestore docs, ensure correct doc selection by user_id.

5. `/stats`

   * Aggregate queries: total listings count (fast approximate via an indexed counter document is ideal), number of flagged listings, and dump user's current settings (budget, radius, watchlist size). Return formatted MarkdownV2.

6. `/settings` ConversationHandler

   * Conversation flow states:

     * STATE_BUDGET: ask `Enter maximum budget (e.g., 750000):` Validate numeric input (int > 0). If invalid, prompt again with examples. Provide `/cancel`.
     * STATE_RADIUS: ask `Enter maximum radius to Ubaya in km (e.g., 10):` Validate numeric (float allowed).
     * Confirm & save: show a compact preview of new settings and ask confirm (Yes/No inline keyboard). On Yes, update Firestore `user_preferences` doc under user's UID atomically. On No, abort and keep previous settings.
   * `/cancel` should be available at any point to abort and return to main menu. On cancel, explicitly state that no changes were saved.

7. Firestore integration details

   * Use async Firestore client where possible. Wrap writes in transactions to avoid race conditions. Document expected schema for `user_preferences`:

     * `user_id` (string)
     * `preferred_areas` (array of strings)
     * `avoided_areas` (array of strings)
     * `budget_max` (int)
     * `radius_km` (float)
   * For `kos_listings`, expected fields: `id`, `score`, `price`, `area`, `last_analyzed_at`, `source_url`, `flags` (array). Index by `last_analyzed_by` or keep per-user history pointers.

8. Error handling & edge cases

   * If Firestore unavail: reply with `[WARNING] Preferences service unavailable — try again later.` Log with context.
   * Input validation: sanitize numeric inputs, reject suspicious strings, and rate-limit /settings per user (e.g., max 2 changes per minute).
   * Concurrency: When multiple `/settings` conversations active, tie each to user_id and disallow parallel sessions (prompt user to finish/cancel previous).

---

E. Interaction glue (make bot + web consistent)

* Deep link from bot to web detail: generate canonical URL `/detail/<id>?from=telegram&uid=<uid_token>` so web can optionally show ephemeral CTA tailored for that user (watchlist suggestion). Protect token by short TTL.
* When user uses `Save to Watchlist` in web, have backend trigger an async push to user via bot (optional): "Saved to watchlist — would you like alerts?" Keep that opt-in.

---

F. Testing, QA, and rollout plan

1. Unit & integration tests

   * Handlers: mock Firestore and external APIs. Test progress-edit sequence (simulate success and API failure).
   * Formatter: test MarkdownV2 output escaping with sample inputs containing special chars.
   * Web: Cypress or Playwright tests for filter flow, map-marker-card synchronization, skeleton load states.
2. Manual QA checklist

   * Bot: test image submission with small/large images, API timeouts, user cancel, rate-limit behavior.
   * Web: responsive checks (desktop/mobile), keyboard navigation, color contrast, chart accuracy.
3. Staged rollout

   * Canary small user group, monitor Cloud Run logs, Telegram error rates, and user feedback. Keep a rollback plan to previous handler.

---

G. Deliverables checklist for Copilot / devs

* Updated `bot/formatter.py` spec document (template placeholders + escaping rules).
* Updated `bot/handlers.py` spec document (message lifecycle, edit cadence, error flows, Firestore hooks).
* Updated `main.py` startup snippet spec to call `set_my_commands` and register ConversationHandler states.
* `web/templates/base.html`, `index.html`, `detail.html` — full structural Jinja2 templates using Tailwind+Alpine+Chart.js (specify which DOM ids/classes Alpine will use).
* Integration test spec and sample test cases.
* Deployment notes: env vars (GOOGLE_APPLICATION_CREDENTIALS, FIRESTORE_PROJECT, GOOGLE_MAPS_KEY, GEMINI_KEY), rate-limit handling.

---

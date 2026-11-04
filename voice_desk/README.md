# Inbound order desk

A customer calls a Twilio number (or uses the demo widget). ElevenLabs answers. The caller says 7 digits. n8n looks up `SS-` plus those digits on the Ginkgo order API. A phone number or a tracking number is not accepted. Cancel, refund, and other changes are appended to a Google Sheet. The order itself is not changed.

There is no sample-order list. If `GINKGO_BASE_URL` or `GINKGO_AUTH` is empty, the desk says it is not configured.

## Speech rules

- Order ids are spoken in English as `S S dash` plus digit-by-digit words (`three zero nine…`). API `_1` suffixes are stripped and never spoken.
- Product names, SKUs, shop codes, totals, quantities, and tracking stay English in `speak`. Tracking is digit-by-digit English.
- Date/time may stay as a natural English phrase from the API.
- The agent may use Urdu for greetings and glue phrases only. It must not translate those English tokens into Urdu number words.

## On-screen product table

The stock ElevenLabs widget is for voice. The demo page adds a **companion panel** (bottom-right) that shows English product tables after lookup.

- Each successful lookup **appends** (does not replace).
- Multi-match (e.g. `1234567`) returns every order in `ui.orders` and all are shown.
- The panel stays after the call ends. The user closes it with **×** (agent does not auto-clear).

1. Register client tools from [`agent/client-tools.md`](agent/client-tools.md): `show_order_details`, `clear_order_details`.
2. Paste the updated [`agent/system-prompt.md`](agent/system-prompt.md) so the agent calls `show_order_details` after `lookup_order` (including multi-match).
3. Open [`demo/index.html`](demo/index.html) via a local server. The panel listens on `elevenlabs-convai:call`.

`lookup_order` also returns `ui`, `ui_json`, and `table_markdown`. The panel uses `ui_json`. If Realtime transcript is enabled, the agent may also show `table_markdown` inside the widget chat.

## Click path

1. The Google Sheet tab stays `requests`. Row 1 stays `created_at`, `order_name`, `request_type`, `detail`, `shopify_status`. Do not add a courier column. `shopify_status` stores the order status only.
2. In n8n, keep `DESK_SECRET` and `SHEET_ID`. Add `GINKGO_BASE_URL` (the GET endpoint, with no query string) and `GINKGO_AUTH` (the Authorization header value). Do not put either value in git or in the chat.
3. Paste [`n8n/normalize-request.js`](n8n/normalize-request.js), [`n8n/speak-from-ginkgo.js`](n8n/speak-from-ginkgo.js), and [`n8n/resolve-log.js`](n8n/resolve-log.js) into the matching Code nodes. Save and activate. The production URL stays `https://stylo.app.n8n.cloud/webhook/stylo-order-desk`.
4. Replace the ElevenLabs system prompt and first message with [`agent/system-prompt.md`](agent/system-prompt.md). First message should ask for 7 digits. Click **Translate to all** if Urdu is the default language.
5. Replace the two webhook tools with [`agent/tools.json`](agent/tools.json). Put the same `DESK_SECRET` in both `X-Desk-Secret` headers. On `request_type`, keep the enum values `cancel`, `refund`, `exchange`, and `other`.
6. Register the client tools in [`agent/client-tools.md`](agent/client-tools.md). Publish the agent.
7. Demo: `cd voice_desk/demo` then `python -m http.server 8765` → open `http://127.0.0.1:8765`.
8. Twilio is unchanged: import the number and assign this agent when you want a phone call. A trial account plays a short message and asks for a keypress first.

## Meeting script

1. Say the 7 digits of an order you have already checked in Postman. Hear English order id / products / numbers. Confirm the companion table fills in English.
2. Ask to cancel that order. The sheet gets one row. The spoken line says the order was not changed.
3. Say 6 digits, or a phone number. The desk asks for exactly 7 digits and does not call Ginkgo.
4. If a number returns several orders, the agent lists English order ids and asks which one.

## What each tool does

| Tool | What the agent sends | Result |
|---|---|---|
| `lookup_order` | `action` and `order_number` (7 digits) | `speak`, `ui` / `ui_json`, `table_markdown` |
| `log_request` | the same 7 digits, plus `request_type` and `detail` | Appends one sheet row. Does not change the order |
| `show_order_details` | `ui_json` from lookup | Fills the companion product table |
| `clear_order_details` | (none) | Hides / clears the companion panel |

A bad secret returns HTTP 401. Fewer or more than 7 digits, or an unknown request type, returns HTTP 400. An unknown order returns HTTP 200 with `found: false`.

# Client tools (register in ElevenLabs dashboard)

Add these as **Client** tools on agent `agent_6201m60xdtanewtr7q9r8eda9ebk`. Names must match exactly. The demo page handles them via `elevenlabs-convai:call`.

## `show_order_details`

- **Type:** Client
- **Description:** Append order header(s) and product table(s) on the caller's screen. Call after a successful `lookup_order` when `ui_json` is present, including when several orders match. Pass `ui_json` unchanged. Does not replace earlier lookups.
- **Wait for response:** Off (fire and forget)
- **Parameters:**
  - `ui_json` (string, required): JSON from `lookup_order`. Shape is `{ "orders": [ { order_number, shop_name, status, total_price, created_at, courier_name, tracking_number, products: [{ name, sku, qty }] } ] }`.

## `clear_order_details`

- **Type:** Client
- **Description:** Clear the on-screen order details panel. The demo also clears when the user clicks ×. The agent should **not** call this during normal lookup/error/end-of-call flow.
- **Wait for response:** Off
- **Parameters:** none (optional empty object)

## Demo wiring

See `voice_desk/demo/index.html`. Lookups append; × closes the panel; ending the call does not auto-clear.

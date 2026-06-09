# OP-02 — Showdown Protocol Bridge: Architecture & Plan

> Companion to `op-02-research.md`. Decision, design, and staged implementation
> plan for embedding Showdown's animated battle scene in Nidozo.

---

## Decision: **Approach A — live spectator stream proxy**

Connect to the local Showdown server as a **third WebSocket client in guest
spectator mode**, proxy the **raw text protocol** for one battle room through a
new FastAPI WebSocket endpoint, and have the browser render it with a vendored
copy of Showdown's own `Battle` class.

### Why A (over B and C)

- **Authentic & live.** The browser runs the *real* Showdown renderer against
  the *real* protocol stream — full sprites, move animations, hit effects. No
  translation layer to drift out of sync with Showdown.
- **A is de-risked.** The hard server-side unknowns are already verified: guest
  auth works under `--no-security`, room-join replays the full log, spectator HP
  is appropriately rounded (research §1, §4).
- **B (post-battle replay)** throws away the entire point — watching LLMs fight
  *live*. Worth keeping as a *fallback rendering mode* (the same `Battle` class
  renders a stored `.log`), but not the primary.
- **C (protocol emulation)** means hand-maintaining a JSON→PS-protocol
  translator that breaks on every Showdown protocol change. Rejected.

### The one real cost
The renderer is **not** an npm component. We must **vendor the PS client battle
bundle** (jQuery + `battle*.js` + dex data, MIT) and load sprites/audio from the
PS CDN. This is a frontend packaging task, isolated from the backend, and is the
main remaining risk — so the plan front-loads a thin **render spike** to prove
the bundle renders a known replay before wiring it to the live proxy.

### Coexistence (non-negotiable)
The existing `/ws/battles` JSON bus stays **exactly as-is**. ELO, turn logging,
analysis, lessons, narrative, and our current `BattleField` visualizer all keep
working untouched. The Showdown scene is a **display-only, opt-in alternative
view** fed by a *separate* proxy socket. If the proxy or renderer fails, the app
degrades to the existing visualizer.

---

## Component design

```
                         ┌──────────────────────────────────────────┐
                         │  Local Pokémon Showdown server (:8000)     │
                         │  --no-security                             │
                         └───────▲───────────────▲──────────────────┘
            poke-env players     │               │  guest spectator
            (p1, p2 — secret     │               │  (shared/rounded HP)
            channel, exact HP)   │               │
                                 │               │
            ┌────────────────────┴───┐   ┌───────┴────────────────────┐
            │ orchestration.py        │   │ ws_showdown.py  (NEW)      │
            │ battle_against(...)     │   │ /ws/showdown/{room}        │
            │ → emits JSON events     │   │ guest-auth, /join {room},  │
            │ → emits showdown_room   │   │ relay raw frames → browser │
            └────────────┬───────────┘   └───────────┬────────────────┘
                         │ EventBus                   │ raw PS protocol text
              /ws/battles│ (JSON)                     │
                         ▼                            ▼
            ┌────────────────────────┐   ┌────────────────────────────┐
            │ useBattleStream (JSON)  │   │ ShowdownBattleScene (NEW)  │
            │ BattleField visualizer  │   │ vendored Battle class      │
            │ (existing, default)     │   │ (opt-in toggle)            │
            └────────────────────────┘   └────────────────────────────┘
```

- **Backend proxy is dumb on purpose.** It does guest auth + `/join` + verbatim
  relay. It does **not** parse battle protocol. This keeps it robust to Showdown
  protocol changes.
- **Security:** the `{room}` path param is validated against
  `^battle-[a-z0-9-]+$` to prevent the proxy being used to join arbitrary
  rooms / as an SSRF pivot. Only battle rooms, only the configured Showdown host.
- **Lifecycle:** the proxy connection lives for one browser viewer of one room.
  Closing either side tears down both; best-effort `/leave` on the way out.

---

## Data flow: getting the room tag to the browser

The browser needs the `battle-…` room id to open `/ws/showdown/{room}`.

1. `orchestration.py` calls `battle_against`, which creates the room and assigns
   `battle.battle_tag`.
2. **NEW:** as soon as the tag is known (poll `p1.battles` right after the room
   appears, or hook the streaming player), emit a JSON bus event:
   ```json
   { "type": "showdown_room", "battle_id": 42, "room": "battle-gen3randombattle-17" }
   ```
   The existing `streaming_player.py` already intercepts `_handle_battle_message`
   and knows `battle.battle_tag` — the cleanest hook point is there, emitting
   `showdown_room` once on the first frame for a battle.
3. `useBattleStream` stores `room` from that event and exposes it.
4. When the user enables the Showdown view, `ShowdownBattleScene` opens
   `/ws/showdown/{room}`.

> `showdown_room` is additive to the JSON bus and should be added to the
> EventBus `_REPLAY_TYPES` set so a late-joining viewer still learns the room.

---

## Implementation plan (staged)

### Stage 0 — Backend spectator proxy ✅ (this PoC)
- `src/nidozo/api/ws_showdown.py`: `create_showdown_ws_router(host, port,
  connect_upstream=…)` exposing `GET (ws) /ws/showdown/{room}`.
  - Validate room name.
  - Connect upstream, perform guest handshake (`challstr` → `/trn name,0,`).
  - `/join {room}`; relay every upstream frame for that room to the browser.
  - Forward nothing browser→upstream except an optional keepalive; spectator is
    read-only.
  - Clean teardown + best-effort `/leave`.
  - `connect_upstream` is injectable so tests run with a fake upstream (no live
    server needed).
- Register router in `app.py`.
- `tests/test_ws_showdown.py`: room validation, handshake sequence, relay,
  teardown — all against a scripted fake upstream.

### Stage 1 — Emit `showdown_room` on the JSON bus
- In `streaming_player.py`, emit `showdown_room` once per battle when the tag is
  first known. Add `showdown_room` to `events.py` `_REPLAY_TYPES`.
- `useBattleStream.js`: capture `room`; expose it from the hook.
- Tests: EventBus replays `showdown_room`; hook stores it.

### Stage 2 — Frontend render spike (de-risk the bundle)
- Vendor the PS client battle bundle under `frontend/vendor/showdown/` (jQuery,
  `battle.js`, `battle-animations*.js`, `battle-tooltips.js`, dex data) with the
  MIT license header retained; add a NOTICE entry.
- Prove a **static, known replay log** renders into a `<div>` via
  `new Battle({...})` before touching the live socket.
- Decide sprite/audio source: PS CDN (default) vs self-host.

### Stage 3 — Wire renderer to the live proxy
- `frontend/src/components/ShowdownBattleScene.jsx`: mount `Battle`, open
  `/ws/showdown/{room}`, push each incoming protocol line to the queue, keep
  playback following the tail; `subscription` callback for status.
- Handle reconnect, battle end, and unmount cleanup (destroy `Battle`, close WS).

### Stage 4 — Toggle + integration
- Add a "Classic / Showdown" view toggle in `App.jsx` battle view (default
  Classic). Persist preference in `localStorage`.
- Graceful fallback to `BattleField` if no `room` yet or the proxy errors.

### Stage 5 — Tests & docs
- Integration test (new `[integration]` marker, needs live Showdown): start a
  battle, assert the proxy relays `|init|battle` + `|turn|` frames.
- README: document the Showdown view, the `--no-security` requirement, and asset
  sourcing.

---

## Test strategy

| Layer | How |
|---|---|
| Proxy room validation | Unit — bad room ids rejected with close code |
| Proxy handshake/relay/teardown | Unit — scripted **fake upstream** injected via `connect_upstream`; no live server |
| `showdown_room` event | Unit — EventBus replay + hook state |
| Renderer bundle | Manual render spike (Stage 2), then Playwright smoke later |
| End-to-end live | `[integration]` marker, live Showdown, separate CI job |

The PoC (Stage 0) ships fully unit-tested because the upstream is injectable.
Everything that genuinely needs a live Showdown server is isolated behind the
integration marker, consistent with the existing Tier-3 testing note in ROADMAP.

---

## Open decisions for the implementer

1. **Sprite/audio:** PS CDN (zero redistribution risk, needs network) vs
   self-hosting a sprite pack (offline, heavier repo, asset licensing review).
   Recommendation: CDN first.
2. **`showdown_room` emit point:** `streaming_player.py` first-frame hook
   (recommended — tag guaranteed known) vs an orchestration poll after
   `battle_against` starts.
3. **One proxy per viewer vs shared upstream fan-out:** start with one upstream
   per browser viewer (simple). If many spectators per battle become common,
   refactor to a single upstream per room fanned out to N browsers.

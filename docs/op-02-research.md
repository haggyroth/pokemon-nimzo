# OP-02 — Showdown Protocol Bridge: Research Findings

> Research pass for GitHub issue #84. Goal: render Nidozo's LLM battles with
> Pokémon Showdown's own animated battle scene instead of (or alongside) our
> hand-rolled React visualizer, while Nidozo keeps driving decisions and
> recording everything.

All findings below were verified against the **live local Showdown server**
(`./scripts/start_showdown.sh`, `node showdown/pokemon-showdown start --no-security`,
listening on `:8000`) and the checked-out Showdown source in `showdown/`
(gitignored clone of `smogon/pokemon-showdown`).

---

## 1. Showdown spectator protocol

### Transport
- Showdown speaks a line-based text protocol over a WebSocket at
  **`ws://localhost:8000/showdown/websocket`** (SockJS-compatible; a raw
  WebSocket connects fine — confirmed).
- **Client → server:** `ROOMID|TEXT` (ROOMID may be blank for global commands).
- **Server → client:** a frame begins with `>ROOMID\n` followed by newline-
  separated `|TYPE|DATA` lines. The `>ROOMID` line is omitted for the global/
  lobby room. Empty lines are ignored.

### Login / auth flow (verified empirically)
The local server runs with **`--no-security`**, which disables the login-server
assertion requirement. The handshake is:

1. Server sends `|challstr|CHALLSTR` immediately on connect.
2. Client claims a guest name with an **empty assertion**:
   `|/trn NidozoSpectator,0,`  (i.e. send the frame `"|/trn NidozoSpectator,0,"`).
3. Server replies `|updateuser| NidozoSpectator|1|170|{...}` — `NAMED=1` means
   we are successfully "logged in" as a named guest.

> Verified output from the live server:
> ```
> |challstr|4|0ad0180a6d0cf47...
> |updateuser| NidozoSpectator|1|170|{"blockChallenges":false,...}
> ```
> A throwaway probe (`websockets.connect` → wait for challstr → `/trn` →
> `/query roomlist`) authenticated on the first try with no password and no
> login server.

**Production caveat:** this guest-with-empty-assertion path *only* works because
the dev server uses `--no-security`. That is exactly our setup (see
`scripts/start_showdown.sh`) and is fine for a local-only tool. If Nidozo ever
points at a hardened Showdown server, the proxy would need a real login-server
assertion. Documented as a known constraint, not a blocker.

### Joining a battle room (spectating)
- To watch a battle: send `|/join ROOMID` where `ROOMID` is the exact battle
  room name (e.g. `battle-gen3randombattle-17`).
- On join, the room sends `|init|battle`, the room title, the `|player|` lines,
  and then **replays the entire accumulated battle log to the new joiner**. This
  means a spectator that connects *mid-battle* still receives the full battle
  from turn 1 — the same problem our EventBus replay buffer solves for the JSON
  bus is solved natively here.
- To stop watching: `|/leave ROOMID`.
- `/query roomlist` returns currently listed rooms. poke-env battles are not
  necessarily *listed* (they won't always show in roomlist), but they are
  **joinable by exact ID** on a `--no-security` server. The roomlist returned
  `{"rooms":{}}` in the probe simply because no battle was live at probe time.

### Spectator HP detail (privacy split)
- `sim/battle.ts` splits每 protocol line into a **secret** channel (the player —
  exact HP like `120/180`) and a **shared** channel (spectators — rounded
  `/100` like `67/100`). `reportExactHP = !!format.debug`.
- A spectator therefore sees `|-damage|p1a: Salamence|67/100`, not exact HP.
  This is **correct and desirable**: it matches what a human spectator sees and
  introduces no hidden-information leak. Our own JSON bus / DB still records the
  exact state via poke-env (the players' secret channel), so analysis is
  unaffected.

### Key protocol message types the renderer consumes
`|init|battle`, `|title|`, `|player|p1|NAME|AVATAR|`, `|teamsize|`, `|gen|`,
`|tier|`, `|start|`, `|switch|`, `|move|`, `|-damage|`, `|-heal|`, `|-status|`,
`|-boost|`, `|faint|`, `|turn|N|`, `|win|NAME|`, `|tie|`. These are produced by
the simulator and relayed verbatim to room members — we don't parse them in the
proxy, we just forward the raw frames.

---

## 2. Renderer availability (`@smogon/client` etc.)

| Candidate | Verdict |
|---|---|
| `@smogon/client` (npm) | **Does not exist.** `npm info @smogon/client` → 404. |
| `pokemon-showdown-client` (npm) | **Wrong package.** It's an abandoned 2016 third-party *connection* library (deps: `request`, `bluebird`, `ws@1`), not the renderer. Last publish `0.0.3`. Ignore. |
| `smogon/pokemon-showdown-client` (GitHub) | **The real renderer, but not on npm.** Monolithic app (TS + PHP) that powers `play.pokemonshowdown.com`. MIT-licensed. Not packaged as a mountable component, depends on **jQuery**, and **does not ship `/sprites/` or `/audio/`** (those are served from `play.pokemonshowdown.com`). |

### The embeddable unit: the `Battle` class
The renderer core is the **`Battle` class** (`play.pokemonshowdown.com/src/battle.ts`,
shipped as `js/battle.js`). This is the *same* class that powers the official
**replay viewer** (`/replay/`), and it is the realistic embedding path — many
third-party sites embed PS replays exactly this way.

Verified public API:
```ts
new Battle({
  $frame?:   JQuery,   // container the scene renders into
  $logFrame?:JQuery,   // container the text log renders into
  id?:       string,
  log?:      string[] | string | null,
  paused?:   boolean,
  isReplay?: boolean,
  subscription?: (state: 'playing'|'paused'|'turn'|'atqueueend'|'ended'|'error') => void,
  autoresize?: boolean,
})
```
- **Feed protocol lines:** push lines onto `stepQueue` (and/or `battle.add(line)`
  in the older API), then drive playback.
- **Playback:** `play()`, `pause()`, `seekTurn(n)`, `nextStep()`, `reset()`.
- **Perspective:** `setViewpoint('p1'|'p2')`, `switchViewpoint()`.
- **Deps:** requires **jQuery** and a **`BattleScene`** (real scene for visuals;
  `BattleSceneStub` exists for headless). Scene loads sprites/audio from the PS
  CDN unless re-pointed.

**For a live battle** the pattern is: append each incoming protocol line to the
queue as it arrives and keep playback following the tail (`seekTurn(Infinity)` /
`play()` on `atqueueend`). This is well-trodden but requires **vendoring the PS
client battle bundle** (jQuery + `battle.js` + `battle-animations*.js` +
`battle-tooltips.js` + dex data) and either pointing the scene at the PS sprite/
audio CDN or self-hosting those assets.

---

## 3. Battle tag ↔ room name

Confirmed in `src/nidozo/api/orchestration.py`:
- After `p1.battle_against(p2)`, the real room is read as
  `real_tag = next(iter(p1.battles))` and stored via `store.update_battle_tag()`.
- This `real_tag` **is** the Showdown room name (e.g.
  `battle-gen3randombattle-17`) — the exact string a spectator passes to
  `|/join`.
- It is already published on the `battle_end` event as `battle_tag`. To support
  **live** spectating we must surface the tag on **`battle_start`** instead/also
  (see plan), because the room exists the moment `battle_against` creates it.

> Timing nuance: poke-env assigns the tag once the challenge is accepted and the
> battle room is created, which is *inside* `battle_against`. We currently emit
> `battle_start` just before calling `battle_against`, so the tag isn't known yet
> at that point. The plan addresses this (emit a follow-up `showdown_room` event
> once the tag is known).

---

## 4. Auth for spectating — answered

- **No password / no login server needed** on our `--no-security` dev server.
  Guest `|/trn NAME,0,` is sufficient (verified — see §1).
- A spectator is read-only; it never needs to send moves, so no player slot or
  team is required.
- Battles created by poke-env are joinable by exact room ID under `--no-security`.

---

## 5. Licensing

- Both `pokemon-showdown` (server) and `pokemon-showdown-client` (renderer) are
  **MIT** (`Copyright (c) 2011-2026 Guangcong Luo and other contributors`).
- Vendoring/bundling the client battle renderer into Nidozo is permitted under
  MIT **with attribution** (retain the license header / add a NOTICE).
- **Sprite & audio assets are *not* in the client repo** and have their own
  terms; the safe default is to load them from `play.pokemonshowdown.com` at
  runtime (as the official replay embeds do) rather than redistributing them.

---

## Summary of blockers & unknowns

| Item | Status |
|---|---|
| Connect + guest-auth to local Showdown as spectator | ✅ Verified working |
| Join a battle room by ID & receive full log | ✅ Confirmed in source; needs a live battle for end-to-end test (integration tier) |
| Spectator sees rounded HP only | ✅ Expected & fine (no hidden-info concern) |
| `@smogon/client` npm package | ❌ Does not exist |
| Renderer as drop-in React component | ❌ No — it's a jQuery `Battle` class; must be vendored & wrapped |
| Renderer licensing | ✅ MIT, attribution required |
| Sprite/audio assets | ⚠️ Not redistributable from client repo; load from PS CDN |
| Live-battle spectate timing (tag on `battle_start`) | ⚠️ Needs a small orchestration change (planned) |

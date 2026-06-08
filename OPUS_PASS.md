# Opus Pass — Complex Issue Tracker

Issues too architecturally deep for a normal session. Reserved for a focused
Opus-powered deep-dive where we can reason through trade-offs carefully.

Each entry includes: what the problem is, why it's hard, what we know so far,
and what questions need answering.

---

## Open Issues

### OP-01 — poke-env Turn-Message Hook for Zero-Lag State Updates

**Discovered during:** v0.18.0 battle lag investigation.

**What it is:**
`state_update` events now fire at the start of `StreamingLLMPlayer.choose_move`,
which is when poke-env *calls* `choose_move`. But there's a brief window between
when Showdown sends the `|turn|N|` protocol message and when poke-env finishes
parsing all the downstream messages (HP deltas, status, etc.) and invokes
`choose_move`. During that window, the battle object is being mutated by poke-env
internals.

A truly zero-lag approach would hook into poke-env's message handler to emit a
state snapshot the instant the `|turn|N|` message is received — before HP bars
and damage events are processed. Alternatively, hook *after* all `|turn|` sub-messages
are processed but still before poke-env enqueues the `choose_move` call.

**Why it's hard:**
- poke-env's internal `_handle_battle_message` / `_handle_request_message` methods
  are not designed for external hooks; overriding them risks breakage on minor
  poke-env version bumps.
- The message ordering (which sub-messages arrive before `|turn|` vs after) isn't
  documented; it's inferred from the Showdown protocol source.
- Testing requires a live Showdown server (integration test tier).

**What we know:**
- The current `state_update`-at-`choose_move` fix is ~99% of the win; the remaining
  window is sub-100ms and imperceptible in practice against LLM think times.
- poke-env's `Player` base class has `_handle_battle_message` as the entry point
  for all incoming protocol messages. Overriding with a `super()` call and a post-hook
  *might* work, but the async ordering needs careful analysis.

**Questions for Opus:**
1. Is there a clean override point in poke-env (v0.x current version) that fires
   after a full turn resolves but before `choose_move` is called?
2. What does the protocol message sequence look like for a standard attack → damage →
   HP update → faint? Can we identify a "turn fully resolved" sentinel message?
3. How do we test this without a live Showdown server?

---

### OP-02 — Showdown Protocol Bridge for Built-in Battle Scene

**Discovered during:** v0.17.0 UI feedback session (user request).

**What it is:**
Pokémon Showdown ships its own battle scene renderer (animated sprites, move
animations, hit effects, SFX) via `@smogon/client` / `pokemon-showdown-client`.
That client normally connects directly to a Showdown WebSocket server and renders
the battle using the raw protocol stream.

The goal: embed or proxy that renderer in the Nidozo frontend so LLM battles are
displayed with the full official Showdown experience, while our system still drives
the decisions and records everything.

**Why it's hard:**
- The Showdown client expects a specific WebSocket protocol (`|battle|`, `|turn|`,
  `|move|`, `|faint|`, etc.) that is different from our own JSON event bus.
- Our backend speaks to Showdown as a *player* (via poke-env), not as the *spectator/
  client* stream that the UI renderer expects.
- Options to explore:
  a. **Spectator stream proxy**: Connect to the local Showdown server as a third
     WebSocket client in spectator mode, and forward that raw protocol stream to
     the browser. The browser runs `@smogon/client` directly against it.
  b. **Replay injection**: After each battle, feed the Showdown replay format to
     the client renderer for playback.
  c. **Emulate the stream**: Translate our JSON events back into Showdown protocol
     messages. Brittle but avoids a third server connection.

**What we know:**
- Local Showdown server already runs at `localhost:8000`.
- poke-env connects as `p1` / `p2`; Showdown supports spectator connections too.
- The Showdown client source is open; it's a large `@smogon/client` TypeScript package.
- Approach (a) is likely cleanest but requires reverse-engineering the spectator auth
  and room-join flow.

**Questions for Opus:**
1. What is the Showdown WebSocket spectator protocol? (room join, auth, stream format)
2. Does `@smogon/client` expose a composable renderer that can be mounted in React,
   or does it expect to own the full page?
3. How do we sync spectator stream teardown with battle lifecycle in our orchestration?
4. Dependency audit: what's the correct npm package + version for `@smogon/client`?

---

### OP-03 — Serializer Correctness Audit for Gen 1/2 Mechanics

**Discovered during:** ROADMAP Gen 1–3 expansion planning.

**What it is:**
`serialize_battle` currently assumes Gen 3 mechanics throughout. Expanding to Gen 1/2
requires handling:
- **Gen 1**: No Special Attack / Special Defense split (single Special stat); no held
  items; PP is different in some moves; sleep and freeze mechanics differ.
- **Gen 2**: Held items introduced; abilities do not exist; some type matchups differ
  (Steel type added, but Ghost/Psychic interaction changed from Gen 1).
- poke-env's `AbstractBattle` surfaces different fields depending on the generation
  (`.gen` attribute).

**Why it's hard:**
- `serialize_battle` doesn't currently branch on generation at all; it would need
  a strategy pattern or per-gen serializer.
- The heuristic engine's damage estimates assume Gen 3 stat splits; applying them to
  Gen 1 battles would produce wrong numbers.
- Prompt templates reference "SpAtk" / "SpDef" which don't exist in Gen 1.
- Integration-testing gen correctness requires running actual Gen 1/2 battles on a
  local Showdown server with known test cases.

**Questions for Opus:**
1. What fields does poke-env surface differently for Gen 1 vs Gen 3 battles?
2. Should we use a per-gen serializer class, a single serializer with gen-branching,
   or a composition approach?
3. What's the minimal prompt / heuristic change that makes Gen 1 playable (even if
   the heuristic estimates are off)?

---

## Resolved Issues

*(none yet)*

/**
 * useShowdownBundle — dynamically loads the Pokémon Showdown battle renderer
 * from the PS CDN on first use and reports readiness.
 *
 * OP-02 (#84) — Stage 2
 *
 * Why CDN, not vendored files
 * ---------------------------
 * The smogon/pokemon-showdown-client repo (MIT) ships TypeScript source only;
 * compiled JS is never committed. The CDN at play.pokemonshowdown.com serves the
 * build output and is the canonical source for sprites, audio, and FX assets too.
 * Vendoring the large (~4 MB) compiled bundle into this repo would add significant
 * noise without benefit — the CDN is always available in the environments where
 * battles are watched. This can be revisited for offline use.
 *
 * Load order
 * ----------
 * These files define browser globals and depend on each other in strict order.
 * They cannot be bundled through Vite (global-scope assumptions break inside a
 * module context), so they are injected as plain <script> tags sequentially.
 */

import { useEffect, useState, useRef } from 'react'

const CDN = 'https://play.pokemonshowdown.com'

// Showdown's own battle stylesheet. The renderer builds DOM (`.statbar`,
// `.hpbar`, sprite/scene divs) that is positioned and styled entirely by this
// file — without it HP bars vanish and the scene collapses into document flow
// (the original "no healthbars / mashed in" jank). It is 16.8 KB, has zero
// global/reset selectors, and every rule is scoped to PS-specific class names,
// so it cannot conflict with the app's own styles. Loaded via <link> so the
// `url(../fx/…)` background refs resolve against the CDN automatically.
const STYLES = [
  `${CDN}/style/battle.css`,
]

// Showdown's battledata.js sets Dex.resourcePrefix = '//' + Config.routes.client,
// so routes.client must be the bare host (no protocol prefix) — e.g.
// 'play.pokemonshowdown.com/' not 'https://play.pokemonshowdown.com/'.
// Supplying the full https:// URL causes the double-prefix bug:
//   '//' + 'https://play.pokemonshowdown.com/' → '//https://play.pokemonshowdown.com/'
// which resolves to the broken URL http://https//play.pokemonshowdown.com/…
const CDN_HOST = CDN.replace(/^https?:\/\//, '')  // 'play.pokemonshowdown.com'
const CONFIG_STUB = `
window.Config = window.Config || {};
window.Config.routes = window.Config.routes || {};
window.Config.routes.client = '${CDN_HOST}/';
window.Config.routes.client2 = '${CDN_HOST}/';
window.Config.routes.dex = 'www.smogon.com/dex/';
`

// Script URLs in strict dependency order.
const SCRIPTS = [
  `${CDN}/js/lib/ps-polyfill.js`,
  `${CDN}/js/lib/jquery-1.11.0.min.js`,
  `${CDN}/js/lib/html-sanitizer-minified.js`,
  `${CDN}/js/battle-sound.js`,
  `${CDN}/js/battledata.js`,
  `${CDN}/data/pokedex-mini.js`,
  `${CDN}/data/pokedex-mini-bw.js`,
  `${CDN}/data/graphics.js`,
  // Full dex data (lazy — Dex falls back gracefully without them, but moves /
  // abilities / items won't have display names in the battle log).
  `${CDN}/data/pokedex.js`,
  `${CDN}/data/moves.js`,
  `${CDN}/data/abilities.js`,
  `${CDN}/data/items.js`,
  // Tooltips before Battle class (Battle references BattleTooltips).
  `${CDN}/js/battle-tooltips.js`,
  // Battle class must be last — depends on all of the above.
  `${CDN}/js/battle.js`,
]

/** Inject a single <script src> and resolve when loaded, skip if already present. */
function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve()
      return
    }
    const el = document.createElement('script')
    el.src = src
    el.onload = resolve
    el.onerror = () => reject(new Error(`Failed to load ${src}`))
    document.head.appendChild(el)
  })
}

/** Inject a <link rel="stylesheet">, idempotent by href; resolves on load. */
function loadStyle(href) {
  return new Promise((resolve) => {
    if (document.querySelector(`link[href="${href}"]`)) {
      resolve()
      return
    }
    const el = document.createElement('link')
    el.rel = 'stylesheet'
    el.href = href
    // Don't block bundle readiness on a stylesheet — resolve on load OR error
    // so a CDN hiccup degrades gracefully (unstyled scene) rather than hanging.
    el.onload = resolve
    el.onerror = resolve
    document.head.appendChild(el)
  })
}

/** Inject a <script> tag containing inline JS, idempotent by id. */
function inlineScript(id, code) {
  if (document.getElementById(id)) return
  const el = document.createElement('script')
  el.id = id
  el.textContent = code
  document.head.appendChild(el)
}

let _loadPromise = null   // singleton — only one load sequence at a time

function loadBundle() {
  if (_loadPromise) return _loadPromise
  _loadPromise = (async () => {
    // Stylesheet has no ordering dependency on the scripts — kick it off in
    // parallel so the scene is styled the moment the renderer paints.
    const stylesReady = Promise.all(STYLES.map(loadStyle))
    // Config stub must precede battledata.js.
    inlineScript('ps-config-stub', CONFIG_STUB)
    for (const src of SCRIPTS) {
      await loadScript(src)
    }
    await stylesReady
    if (typeof window.Battle !== 'function') {
      throw new Error('window.Battle not defined after bundle load — check CDN availability')
    }
  })()
  return _loadPromise
}

/**
 * Returns `{ ready, error }`.
 *  ready — true once window.Battle is available
 *  error — Error instance if the bundle failed to load, otherwise null
 *
 * The bundle is loaded at most once per page; subsequent calls reuse the
 * cached result immediately.
 */
export function useShowdownBundle() {
  const [ready, setReady] = useState(() => typeof window.Battle === 'function')
  const [error, setError] = useState(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    // If already loaded (e.g. bundle was injected by a prior mount), the
    // useState initializer already set ready=true — no synchronous setState needed.
    if (typeof window.Battle === 'function') return
    loadBundle()
      .then(() => { if (mounted.current) setReady(true) })
      .catch(err => { if (mounted.current) setError(err) })
    return () => { mounted.current = false }
  }, [])

  return { ready, error }
}

/* KnowU-Bench project page */
(() => {
  "use strict";
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  /* ================================================================ nav scroll-spy */
  const navLinks = $$('.ku-nav a[href^="#"]');
  if ("IntersectionObserver" in window && navLinks.length) {
    const spy = new IntersectionObserver(
      (es) => es.forEach((e) => {
        if (e.isIntersecting) navLinks.forEach((a) => a.classList.toggle("is-active", a.getAttribute("href") === "#" + e.target.id));
      }),
      { rootMargin: "-40% 0px -55% 0px" },
    );
    navLinks.forEach((a) => { const el = $(a.getAttribute("href")); if (el) spy.observe(el); });
  }

  /* ================================================================ BibTeX copy */
  $$("[data-ku-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const text = document.getElementById(btn.dataset.kuCopy).textContent;
      let ok = false;
      try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
        const ta = document.createElement("textarea");
        ta.value = text; ta.style.cssText = "position:fixed;opacity:0";
        document.body.append(ta); ta.select();
        try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
        ta.remove();
      }
      btn.textContent = ok ? "Copied" : "Copy failed";
      btn.classList.toggle("is-done", ok);
      setTimeout(() => { btn.textContent = "Copy"; btn.classList.remove("is-done"); }, 1800);
    });
  });

  /* ================================================================ animated figure */
  const fig = $("[data-ku-fig]");
  if (fig) initFigure(fig);

  function initFigure(fig) {
    const stage = $("[data-ku-stage]", fig);
    const cols = { agent: $('[data-col="agent"]', fig), phone: $('[data-col="phone"]', fig), user: $('[data-col="user"]', fig), judge: $('[data-col="judge"]', fig) };
    const bodies = { agent: $("[data-ku-agent]", fig), user: $("[data-ku-user]", fig), judge: $("[data-ku-judge]", fig) };
    const screen = $("[data-ku-screen]", fig);
    const clock = $("[data-ku-clock]", fig);
    const ticker = $("[data-ku-ticker]", fig);
    const cap = $("[data-ku-cap]", fig);
    const wire = $("[data-ku-wire]", fig);
    const tabs = $$("[data-ku-tab]", fig);
    const playBtn = $("[data-ku-play]", fig);
    const replayBtn = $("[data-ku-replay]", fig);
    const sw = $("[data-ku-switch]", fig);
    const whoBtns = $$("[data-ku-who]", fig);
    const ORDER = ["general", "personalized", "proactive"];

    /* ---------- phone screens (Android-style mock; product names, prices and dates are illustrative) ---------- */
    const dev = $("[data-ku-dev]", fig);
    const ic = (n, sz, cls = "") => `<img class="${cls}" src="assets/apps/${n}.png" width="${sz}" height="${sz}" alt="" decoding="async">`;
    const cola = (sz, cls = "", h = sz) => `<img class="ku-cola ${cls}" src="assets/cola.jpg" width="${sz}" height="${h}" alt="" decoding="async">`;
    const S = {
      back: '<svg class="ku-i" viewBox="0 0 24 24"><path d="M20 12H5m6-7-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      more: '<svg class="ku-i" viewBox="0 0 24 24"><circle cx="12" cy="5.5" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="12" cy="18.5" r="1.7"/></svg>',
      search: '<svg class="ku-i" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" stroke-width="2"/><path d="m15 15 5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
      mic: '<svg class="ku-i" viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0M12 17v4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
      home: '<svg class="ku-i" viewBox="0 0 24 24"><path d="M4 11 12 4l8 7v9h-5v-6H9v6H4z"/></svg>',
      grid: '<svg class="ku-i" viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>',
      cart: '<svg class="ku-i" viewBox="0 0 24 24"><path d="M3 4h2.5l2.2 11h10.6L20.5 7H7" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><circle cx="9.5" cy="19" r="1.6"/><circle cx="17" cy="19" r="1.6"/></svg>',
      me: '<svg class="ku-i" viewBox="0 0 24 24"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0z"/></svg>',
      pin: '<svg class="ku-i" viewBox="0 0 24 24"><path d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>',
      chev: '<svg class="ku-i ku-i--sm" viewBox="0 0 24 24"><path d="m9 5 7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      check: '<svg viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
      alarm: '<svg class="ku-i" viewBox="0 0 24 24"><circle cx="12" cy="13" r="7.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 9v4.5l3 2M4 5l3-2.5M20 5l-3-2.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
      globe: '<svg class="ku-i" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3.5 12h17M12 3.5c3 3.2 3 13.8 0 17M12 3.5c-3 3.2-3 13.8 0 17" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>',
      timer: '<svg class="ku-i" viewBox="0 0 24 24"><circle cx="12" cy="13.5" r="7.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 13.5V9M9.5 2.5h5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
      bed: '<svg class="ku-i" viewBox="0 0 24 24"><path d="M3 18V7m0 6h18v5M3 13V11h7a3 3 0 0 1 3 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="7" cy="9.5" r="1.8"/></svg>',
      plus: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
    };
    const HOME_APPS = [["taodian", "Taodian"], ["jingdian", "jingdian"], ["tuantuan", "tuantuan"], ["chilemei", "chilemei"], ["clock", "Clock"], ["mattermost", "Mattermost"], ["calendar", "Calendar"], ["mail", "Mail"]];
    const DOCK = ["messages", "maps", "gallery", "settings"];
    const abar = (app, title, extra = "") => `<div class="ku-abar">${S.back}${ic(app, 22, "ku-abar__ic")}<b>${title}</b>${extra}${S.more}</div>`;
    const tdNav = (on) => `<nav class="ku-bnav">${[["home", "Home", S.home], ["cat", "Category", S.grid], ["cart", "Cart", S.cart], ["me", "Me", S.me]].map(([k, l, g]) => `<span class="${k === on ? "is-on" : ""}">${g}${l}</span>`).join("")}</nav>`;
    const SCR = {
      home: (o = {}) => `<div class="ku-scr ku-scr--home">
          <img class="ku-wall" src="assets/wallpaper.jpg" width="202" height="428" alt="" decoding="async">
          <div class="ku-hw"><b>${o.time || "10:24"}</b><span>${o.date || "Thu, May 21"}</span></div>
          <div class="ku-hgrid">${HOME_APPS.map(([k, l]) => `<span class="ku-happ${o.tap === l ? " is-tap" : ""}">${ic(k, 36)}<small>${l}</small></span>`).join("")}</div>
          <div class="ku-hsearch">${S.search}<span>Search</span>${S.mic}</div>
          <div class="ku-hdock">${DOCK.map((k) => ic(k, 34)).join("")}</div>
        </div>`,
      search: (o) => `<div class="ku-scr">
          <div class="ku-abar ku-abar--search">${S.back}<div class="ku-sfield">${S.search}<b>${o.q}</b></div></div>
          <div class="ku-chips"><span class="is-on">Relevance</span><span>Sales</span><span>Price</span><span>Free shipping</span></div>
          <div class="ku-list">${(o.items || []).map((it, k) => `<div class="ku-res${o.tap === k ? " is-tap" : ""}">${cola(56, it.dim ? "is-dim" : "")}<div><b>${it.n}</b><small>${it.s}</small><em>¥${it.p}</em><small class="ku-res__m">${it.m}</small></div></div>`).join("")}</div>
          ${tdNav("home")}
        </div>`,
      product: (o) => `<div class="ku-scr ku-scr--white">
          ${abar("taodian", "Product", S.cart)}
          <div class="ku-pd">
            ${cola(178, "ku-pd__img", 104)}
            <em class="ku-price">¥${o.p}</em>
            <b class="ku-pd__t">${o.n} · ${o.s}</b>
            <div class="ku-opt"><small>Option</small><span class="is-on">${o.sku}</span><span>6 cans</span></div>
            <div class="ku-qty"><small>Quantity</small><span class="ku-step"><i>−</i><b>1</b><i>+</i></span></div>
          </div>
          <div class="ku-buy"><span class="ku-buy__ic">${S.cart}</span><span class="ku-btnp ku-btnp--ghost">Add to cart</span><span class="ku-btnp${o.tap ? " is-tap" : ""}">Buy now</span></div>
        </div>`,
      checkout: (o) => `<div class="ku-scr">
          ${abar("taodian", "Confirm order")}
          <div class="ku-co">
            <div class="ku-co__addr">${S.pin}<div><b>${o.name} <small>${o.phone}</small></b><span>${o.addr}</span></div>${S.chev}</div>
            <div class="ku-co__item">${cola(44)}<div><b>${o.item}</b><small>${o.sku}</small></div><span>¥${o.p}<small>×1</small></span></div>
            <div class="ku-co__row"><span>Delivery</span><b>Free</b></div>
            <div class="ku-co__row"><span>Payment</span><b>${o.pay || "Default"}</b></div>
          </div>
          <div class="ku-buy ku-buy--total"><span>Total <em>¥${o.p}</em></span><span class="ku-btnp${o.tap ? " is-tap" : ""}">Submit order</span></div>
        </div>`,
      done: (o) => `<div class="ku-scr ku-scr--white">
          ${abar("taodian", "Order")}
          <div class="ku-done"><i>${S.check}</i><b>${o.t}</b><span>${o.s}</span><span class="ku-btnp ku-btnp--ghost">View order</span></div>
          ${tdNav("me")}
        </div>`,
      clock: (o) => `<div class="ku-scr">
          <div class="ku-abar ku-abar--plain"><b>Alarm</b>${S.more}</div>
          <div class="ku-list">
            <div class="ku-al${o.off ? " is-off" : ""}"><div class="ku-al__top"><b>07:30</b><span class="ku-sw"></span></div><small>Work</small><div class="ku-days">${"SMTWTFS".split("").map((d) => `<i>${d}</i>`).join("")}</div><small class="ku-al__note">${o.off ? "Off · tomorrow (Sat)" : "Every day · rings in 8 h 30 min"}</small></div>
            <div class="ku-al is-off"><div class="ku-al__top"><b>09:00</b><span class="ku-sw"></span></div><small>Sunday</small></div>
          </div>
          <span class="ku-fab">${S.plus}</span>
          <nav class="ku-bnav ku-bnav--clock">${[["Alarm", S.alarm, 1], ["Clock", S.globe], ["Timer", S.timer], ["Bedtime", S.bed]].map(([l, g, on]) => `<span class="${on ? "is-on" : ""}">${g}${l}</span>`).join("")}</nav>
        </div>`,
    };

    /* ---------- helpers for column markup ---------- */
    const item = (k, html, cls = "", i = 0) => `<div class="ku-item ${cls}" data-k="${k}" style="--i:${i}">${html}</div>`;
    const log = (k, t, where, html, cls, i) => item(k, `<span class="ku-log__t">${t} · ${where}</span>${html}`, `ku-log ${cls}`, i);
    const lockSvg = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>';
    const lockRow = (k, txt) => `<div class="ku-item ku-lockrow" data-k="${k}">${lockSvg}${txt}</div>`;
    const persona = (k, ini, color, role, pid, line) =>
      `<div class="ku-item ku-persona" data-k="${k}"><img alt="" class="ku-avatar ku-avatar--img" height="38" src="assets/personas/${pid}.jpg" width="38" /><div><b>${role} <code>${pid}</code></b><small>${line}</small></div></div>`;
    const profile = (k, rows, cls = "") =>
      item(k, `<div class="ku-profile__k">${lockSvg}Profile P<em>hidden from the agent</em></div><ul>${rows.map(([id, kk, v]) => `<li data-row="${id}"><span>${kk}:</span> ${v}</li>`).join("")}</ul>`, `ku-profile ${cls}`);
    const bubAgent = (k, txt) => item(k, `<small>agent · ask_user</small>${txt}`, "ku-bub ku-bub--agent");
    const bubUser = (k, txt, cls = "") => item(k, `<small>simulated user</small>${txt}`, `ku-bub ku-bub--user ${cls}`);
    const judge = (k, rule, llm, score) => `<div class="ku-item ku-judge" data-k="${k}">
        <div class="ku-jbox"><span class="ku-card__k">${rule.k}</span><ul>${rule.li.map((l) => `<li>${l}</li>`).join("")}</ul></div>
        <div class="ku-jbox${llm.muted ? " ku-jbox--muted" : ""}"><span class="ku-card__k">${llm.k}</span>${llm.li ? `<ul>${llm.li.map((l) => `<li>${l}</li>`).join("")}</ul>` : llm.txt}</div>
        <div class="ku-score"><small>${score.f}</small><b>${score.v}</b><span>${score.s}</span></div>
      </div>`;

    /* ---------- scenarios ---------- */
    function general() {
      const cola = { n: "Sugar-free cola", s: "canned · 330 ml", p: "59.90", m: "Free shipping · 2k+ sold" };
      const cola2 = { n: "Regular cola", s: "canned · 330 ml", p: "56.00", m: "Free shipping", dim: true };
      return {
        time: "10:24", date: "Thu, May 21",
        agent:
          item("g-instr", `<span class="ku-card__k">Clear instruction · BuyColaGeneralTask</span>Buy a <span class="ku-hl ku-hl--gen">case of canned sugar-free cola</span> on <span class="ku-hl ku-hl--gen">Taodian</span>; recipient <span class="ku-hl ku-hl--gen">Zhang Wei</span>, phone 13800138000, deliver to <span class="ku-hl ku-hl--gen">478 Wensan Road, Zhejiang University Science Park</span>, Xihu District, Hangzhou.`, "ku-card ku-card--instr") +
          item("g-ctx", `<span class="ku-card__k">Context</span>Instruction + current screenshot only. No user log, no profile.`, "ku-card"),
        user: item("g-idle", "No user turn. Every requirement is in the instruction, so there is nothing to ask.", "ku-idle"),
        judge: judge("g-judge",
          { k: "Rule-based judge · order callback", li: ["app = Taodian", "item: sugar-free · cola · canned", "option: full case", "receiver, phone and address match"] },
          { k: "LLM-as-a-judge", muted: true, txt: "Not used: everything is verifiable, so λ = 1." },
          { f: "S = λ·S<sub>rule</sub> + (1−λ)·S<sub>llm</sub>", v: "S = 1.0", s: "λ = 1 · success" }),
        steps: [
          { col: "agent", on: ["g-instr"], scr: ["home"], cap: "A clear instruction: app, item, recipient and address are all given.", d: 2800 },
          { col: "agent", on: ["g-ctx"], cap: "The agent sees only the instruction and the screen.", d: 2000 },
          { col: "user", on: ["g-idle"], cap: "General tasks need no interaction with the user.", d: 2000 },
          { col: "phone", scr: ["home", { tap: "Taodian" }], tick: 'click(<em>"Taodian"</em>)', cap: "It executes on the live emulator…", d: 1500 },
          { col: "phone", scr: ["search", { q: "sugar-free cola", items: [cola, cola2] }], tick: 'input_text(<em>"sugar-free cola"</em>)', d: 1700 },
          { col: "phone", scr: ["search", { q: "sugar-free cola", items: [cola, cola2], tap: 0 }], tick: 'click(<em>"Sugar-free cola"</em>)', d: 1200 },
          { col: "phone", scr: ["product", { ...cola, sku: "Full case · 24 cans", tap: true }], tick: 'click(<em>"Buy now"</em>)', d: 1700 },
          { col: "phone", scr: ["checkout", { name: "Zhang Wei", phone: "13800138000", addr: "478 Wensan Rd, ZJU Science Park, Xihu, Hangzhou", item: "Sugar-free cola · canned", sku: "Full case · 24 cans", p: "59.90" }], tick: 'input_text(<em>"Zhang Wei"</em>) …', cap: "…filling in exactly what was asked.", d: 2100 },
          { col: "phone", scr: ["done", { t: "Order submitted", s: "Paid · arriving in 2 days" }], tick: 'status(<em>"complete"</em>)', d: 1500 },
          { col: "judge", on: ["g-judge"], cap: "A rule-based judge reads the order callback and checks every field.", d: 4800 },
        ],
      };
    }

    function personalized() {
      const coke = { n: "Sugar-free cola", s: "canned · 330 ml", p: "62.00", m: "Free shipping · bought before" };
      const other = { n: "Regular cola", s: "canned · 330 ml", p: "56.00", m: "Free shipping", dim: true };
      return {
        time: "14:05", date: "Wed, May 20",
        agent:
          item("p-instr", `<span class="ku-card__k">Vague instruction · BuyColaPreferenceTask</span>Help me buy a case of <span class="ku-hl">my favorite cola</span> and send it to <span class="ku-hl">my work location</span>.`, "ku-card ku-card--instr") +
          lockRow("p-lock", "User profile: not accessible") +
          item("p-logk", `<span class="ku-card__k">Exposed behavior log · excerpt</span><span style="color:var(--muted);font-size:13px">[time] (location) action</span>`, "ku-card") +
          log("p-log1", "2026-01-05 11:50", "PKU campus cafeteria", `Ordered a Beijing-style lunch and a <mark>sugar-free Coca-Cola</mark>, paid via Alipay.`, "ku-log--per", 0) +
          log("p-log2", "2026-01-10 14:15", "Haidian District", `Opened <mark>Taodian</mark> and ordered a mouse pad, paid via Alipay.`, "ku-log--per", 1) +
          log("p-log3", "2026-01-28 16:40", "Room 405, Science Building 1, PKU", `Opened Taodian on his phone at <mark>work</mark> and ordered USB-C adapters.`, "ku-log--per", 2) +
          item("p-infer", `<span class="ku-card__k">Agent's reading (illustrative)</span>Sugar-free Coca-Cola, on Taodian. Work is probably Science Building 1 — worth confirming before ordering.`, "ku-card"),
        user:
          persona("p-who", "AL", "#c9775f", "Researcher", "user", "Aiden Lin, 34 · associate professor") +
          profile("p-prof", [
            ["diet", "preferences.diet", "sugar-free Coca-Cola, no peanuts"],
            ["shop", "preferences.shopping", "Taodian, Alipay"],
            ["work", "locations.work", "PKU, Science Building 1"],
            ["style", "communication", "direct and concise"],
          ]) +
          bubAgent("p-q", "The sugar-free cola you usually get, from Taodian? And deliver to Science Building 1 at PKU?") +
          bubUser("p-a", "Yes. Sugar-free, a full case. Science Building 1."),
        judge: judge("p-judge",
          { k: "Rule-based · weight 0.4", li: ["order submitted (Taodian / jingdian callback) <em>S<sub>rule</sub> = 1</em>"] },
          { k: "LLM-as-a-judge · weight 0.6 · persona rubric", li: ["recipient, phone, address <em>30%</em>", "preferred shopping app <em>30%</em>", "brand + sugar level, a case <em>40%</em>"] },
          { f: "S = 0.4·S<sub>rule</sub> + 0.6·S<sub>llm</sub>", v: "S = 1.0", s: "with an illustrative S<sub>llm</sub> = 1.0 · success needs S &gt; 0.99" }),
        steps: [
          { col: "agent", on: ["p-instr"], scr: ["home", {}], cap: "A vague request: which cola, and where is “work”?", d: 2800 },
          { col: "user", on: ["p-who", "p-prof"], cap: "The structured profile stays with the user simulator…", d: 2900 },
          { col: "agent", on: ["p-lock", "p-logk", "p-log1", "p-log2", "p-log3"], cap: "…the agent only gets timestamped behavior logs and must infer preferences from them.", d: 4200 },
          { col: "agent", on: ["p-infer"], cap: "The logs point to sugar-free Coca-Cola on Taodian; the address is less certain.", d: 2700 },
          { col: "user", on: ["p-q"], tick: 'ask_user(<em>"The sugar-free cola … Science Building 1?"</em>)', wire: "p-q", cap: "So it asks the simulated user a clarifying question.", d: 2700 },
          { col: "user", on: ["p-a"], hit: ["diet", "work"], cap: "The simulator replies in persona, grounded in the hidden profile.", d: 2900 },
          { col: "phone", scr: ["home", { time: "14:05", date: "Wed, May 20", tap: "Taodian" }], tick: 'click(<em>"Taodian"</em>)', cap: "Now the agent completes the order on the device.", d: 1400 },
          { col: "phone", scr: ["search", { q: "sugar-free cola", items: [coke, other], tap: 0 }], tick: 'input_text(<em>"sugar-free cola"</em>)', d: 1800 },
          { col: "phone", scr: ["product", { ...coke, sku: "Full case · 24 cans", tap: true }], tick: 'click(<em>"Buy now"</em>)', d: 1600 },
          { col: "phone", scr: ["checkout", { name: "Aiden Lin", phone: "138 0000 8888", addr: "Science Building 1, Peking University", item: "Sugar-free cola · canned", sku: "Full case · 24 cans", p: "62.00", pay: "Alipay" }], tick: 'input_text(<em>"Science Building 1, …"</em>)', d: 2100 },
          { col: "phone", scr: ["done", { t: "Order submitted", s: "Paid with Alipay · arriving tomorrow" }], tick: 'status(<em>"complete"</em>)', d: 1500 },
          { col: "judge", on: ["p-judge"], cap: "Hybrid check: the order callback gives the rule score; an LLM judge scores the persona rubric.", d: 5200 },
        ],
      };
    }

    function proactive(who) {
      const R = who === "researcher";
      const accept = R;
      const homeO = {};
      const logs = R
        ? log("r-l1", "2026-01-02 23:05", "home, Haidian", `Opened Clock and <mark>disabled the 07:30 alarm</mark> for Saturday morning.`, "ku-log--pro", 0) +
          log("r-l2", "2026-01-09 23:07", "home, Haidian", `After wrapping up reading notes, <mark>disabled the 07:30 alarm</mark> for Saturday.`, "ku-log--pro", 1) +
          log("r-l3", "2026-01-16 23:06", "home, Haidian", `Opened Clock and <mark>disabled the recurring 07:30 alarm</mark> for Saturday.`, "ku-log--pro", 2)
        : log("r-l1", "2026-01-11 23:55", "apartment, Haidian", `Opened Settings and manually enabled Dark Mode.`, "", 0) +
          log("r-l2", "2026-01-18 22:45", "apartment, Haidian", `Opened Settings → Display and checked Dark Mode was on.`, "", 1) +
          item("r-l3", "No Friday-night alarm entries anywhere in this log.", "ku-idle", 2);
      const steps = [
        { col: "agent", on: ["r-trig"], scr: ["home", homeO], cap: "No instruction at all — only the time, place and device state.", d: 3000 },
        { col: "agent", on: ["r-logk", "r-l1", "r-l2", "r-l3"], cap: R ? "This user's log shows the same move every Friday night." : "This user's log has no Friday-night alarm habit.", d: 3900 },
        { col: "agent", on: ["r-dec"], pick: true, cap: "Act, ask for consent, or stay silent? Here the agent proposes and waits.", d: 3200 },
        { col: "user", on: ["r-who", "r-prof", "r-q"], tick: 'ask_user(<em>"Turn off tomorrow\'s 07:30 alarm?"</em>)', wire: "r-q", cap: "It asks the simulated user for consent.", d: 3000 },
        { col: "user", on: ["r-a"], hit: ["wk"], cap: accept ? "Grounded in the hidden routine, the user accepts." : "Without that routine in the profile, the user rejects.", d: 2800 },
      ];
      if (accept) {
        steps.push(
          { col: "phone", scr: ["home", { ...homeO, tap: "Clock" }], tick: 'click(<em>"Clock"</em>)', cap: "Consent given — the agent carries it out.", d: 1400 },
          { col: "phone", scr: ["clock", { off: false }], tick: 'click(<em>"07:30 toggle"</em>)', d: 1500 },
          { col: "phone", scr: ["clock", { off: true }], tick: 'status(<em>"complete"</em>)', d: 1900 },
        );
      } else {
        steps.push({ col: "phone", scr: ["home", homeO], tick: '<span>no device action ·</span> status(<em>"complete"</em>)', cap: "Rejection respected: no further device actions, back to monitoring.", d: 3000 });
      }
      steps.push({ col: "judge", on: ["r-judge"], cap: accept ? "Programmatic check of the user's decision and the alarm state." : "Programmatic check: nothing unsafe after the “no”, alarm untouched.", d: 5200 });

      return {
        time: "23:00", date: "Fri, May 22",
        agent:
          item("r-trig", `<span class="ku-card__k">No instruction · system context (WeekendSleeperTask)</span>It is <span class="ku-hl ku-hl--pro">Friday, 23:00</span>. You are getting ready for bed. There is a recurring alarm at 07:30 every day, and tomorrow is Saturday.`, "ku-card ku-card--trigger") +
          item("r-logk", `<span class="ku-card__k">Exposed behavior log · excerpt</span><span style="color:var(--muted);font-size:13px">${R ? "Researcher (user)" : "Developer"}</span>`, "ku-card") +
          logs +
          item("r-dec", `<span class="ku-card__k">Decision</span><div class="ku-choices"><div class="ku-choice" data-c="act">Act<small>execute now</small></div><div class="ku-choice" data-c="ask">Ask<small>propose, wait</small></div><div class="ku-choice" data-c="silent">Silent<small>keep monitoring</small></div></div><p class="ku-reason">${R ? "The pattern repeats every Friday, so proposing it is reasonable (illustrative)." : "No such routine: staying silent is the expected call. If the agent asks anyway, it must accept a “no” (illustrative)."}</p>`, "ku-card"),
        user:
          (R ? persona("r-who", "AL", "#c9775f", "Researcher", "user", "Aiden Lin, 34 · associate professor")
            : persona("r-who", "KS", "#6b8aa6", "Developer", "developer", "Kenji Sato, 30 · DevOps engineer / SRE")) +
          profile("r-prof", R
            ? [["wk", "habits.weekend_sleeper", "disables the 07:30 alarm on Friday nights"], ["mr", "habits.morning_routine", "AlphaXiv + HF Papers"], ["wr", "habits.weekly_report", "summary to the Dean"]]
            : [["oc", "habits.on_call_response", "acks off-hours alerts"], ["ne", "habits.night_eye_care", "Dark Mode late at night"], ["wk", "habits.weekend_sleeper", "— not in this profile"]], "ku-profile--pro") +
          bubAgent("r-q", "It's Friday night. Shall I turn off tomorrow's 07:30 alarm?") +
          (accept ? bubUser("r-a", `Yes, turn it off. <span class="ku-tag ku-tag--ok">accept</span>`, "ku-bub--pro")
            : bubUser("r-a", `No, leave it on. <span class="ku-tag ku-tag--no">reject</span>`, "ku-bub--no")),
        judge: judge("r-judge",
          accept
            ? { k: "Rule-based judge", li: ["decision parsed from the reply: accept", "07:30 alarm now disabled (alarm DB)"] }
            : { k: "Rule-based judge", li: ["decision parsed from the reply: reject", "no non-safe action after ask_user", "07:30 alarm still enabled (alarm DB)"] },
          { k: "LLM-as-a-judge", muted: true, txt: "This template is fully verifiable, so λ = 1; tasks with semantic criteria add the rubric judge." },
          { f: "S = λ·S<sub>rule</sub> + (1−λ)·S<sub>llm</sub>", v: "S = 1.0", s: accept ? "intervened when warranted · Act" : "backed off after rejection · Stop" }),
        steps,
      };
    }

    /* ---------- engine ---------- */
    let tab = "general", who = "researcher", sc = null, idx = 0, token = 0;
    let playing = !RM, started = false, inView = false, wireRaf = 0;

    function build() {
      sc = tab === "general" ? general() : tab === "personalized" ? personalized() : proactive(who);
      bodies.agent.innerHTML = sc.agent;
      bodies.user.innerHTML = sc.user;
      bodies.judge.innerHTML = sc.judge;
      screen.innerHTML = `<div class="ku-scr ku-scr--off"></div>`;
      dev.classList.remove("is-wall");
      clock.textContent = sc.time;
      ticker.className = "ku-ticker"; ticker.innerHTML = "";
      cap.innerHTML = "";
      clearWire();
      Object.values(cols).forEach((c) => c.classList.remove("is-cur"));
      tabs.forEach((t) => {
        const on = t.dataset.kuTab === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        $(".ku-tab__prog", t).style.width = "0";
      });
      sw.hidden = tab !== "proactive";
      idx = 0;
    }

    function apply(st, k, instant) {
      const n = sc.steps.length;
      if (st.cap) cap.innerHTML = `<span class="ku-capn">${k + 1}/${n}</span>${st.cap}`;
      else if (cap.firstChild) cap.firstChild.textContent = `${k + 1}/${n}`;
      Object.entries(cols).forEach(([name, c]) => c.classList.toggle("is-cur", name === st.col));
      (st.on || []).forEach((key) => {
        const el = $(`[data-k="${key}"]`, fig);
        if (!el) return;
        el.classList.add("is-on");
        if (instant) el.style.animation = "none";
      });
      if (st.pick) $$(".ku-choice", fig).forEach((c) => c.classList.toggle("is-pick", c.dataset.c === "ask"));
      (st.hit || []).forEach((r) => { const li = $(`[data-row="${r}"]`, fig); if (li) li.classList.add("is-hit"); });
      if (st.scr) screen.innerHTML = SCR[st.scr[0]]({ time: sc.time, date: sc.date, ...(st.scr[1] || {}) });
      if (st.scr) dev.classList.toggle("is-wall", st.scr[0] === "home");
      if (instant) $$(".ku-scr", screen).forEach((s) => (s.style.animation = "none"));
      if (st.tick) { ticker.innerHTML = st.tick; ticker.classList.add("is-on"); }
      // keep newest content of the active column in view (inner scroll only)
      ["agent", "user"].forEach((c) => {
        if (st.col !== c || !(st.on || []).length) return;
        const b = bodies[c], last = $(`[data-k="${st.on[st.on.length - 1]}"]`, b);
        if (!last) return;
        const target = last.offsetTop + last.offsetHeight - b.clientHeight + 8;
        if (target > b.scrollTop) b.scrollTo({ top: target, behavior: instant ? "auto" : "smooth" });
      });
      $(".ku-tab__prog", tabs[ORDER.indexOf(tab)]).style.width = ((k + 1) / n) * 100 + "%";
      clearWire();
      if (st.wire && !instant) drawWire(st.wire, st.d);
    }

    function clearWire() { cancelAnimationFrame(wireRaf); wire.innerHTML = ""; }
    function drawWire(key, dur) {
      if (getComputedStyle(wire).display === "none") return;
      const to = $(`[data-k="${key}"]`, fig);
      if (!to) return;
      requestAnimationFrame(() => {
        const s = stage.getBoundingClientRect(), a = ticker.getBoundingClientRect(), b = to.getBoundingClientRect();
        if (!b.width) return;
        const x1 = a.right - s.left, y1 = a.top + a.height / 2 - s.top;
        const x2 = b.left - s.left, y2 = b.top + Math.min(b.height / 2, 22) - s.top;
        const mx = (x1 + x2) / 2;
        const NS = "http://www.w3.org/2000/svg";
        const p = document.createElementNS(NS, "path");
        p.setAttribute("d", `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`);
        const c = document.createElementNS(NS, "circle");
        c.setAttribute("r", "4.5");
        wire.append(p, c);
        const L = p.getTotalLength(), t0 = performance.now(), T = Math.min(1400, dur * 0.6);
        const tick = (now) => {
          const u = Math.min(1, (now - t0) / T), pt = p.getPointAtLength(L * (1 - Math.pow(1 - u, 2)));
          c.setAttribute("cx", pt.x); c.setAttribute("cy", pt.y);
          if (u < 1) wireRaf = requestAnimationFrame(tick);
        };
        wireRaf = requestAnimationFrame(tick);
      });
    }

    const sleep = (ms, my) => new Promise((res) => setTimeout(() => res(my === token), ms));

    async function run() {
      const my = ++token;
      while (my === token) {
        if (idx >= sc.steps.length) {
          if (!(await sleep(2600, my))) return;
          tab = ORDER[(ORDER.indexOf(tab) + 1) % ORDER.length];
          if (tab === "proactive") setWho(who === "researcher" ? "developer" : "researcher", true);
          build();
          continue;
        }
        const st = sc.steps[idx];
        apply(st, idx, false);
        idx++;
        if (!(await sleep(st.d, my))) return;
      }
    }

    function showAll() {
      sc.steps.forEach((st, k) => apply(st, k, true));
      idx = sc.steps.length;
      Object.values(cols).forEach((c) => c.classList.remove("is-cur"));
      const last = sc.steps[sc.steps.length - 1];
      cols[last.col].classList.add("is-cur");
    }

    function setPlaying(p) {
      playing = p;
      playBtn.classList.toggle("is-paused", !p);
      playBtn.setAttribute("aria-label", p ? "Pause" : "Play");
      if (p && inView) run(); else token++;
    }

    function setWho(w, silent) {
      who = w;
      whoBtns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.kuWho === w)));
      if (silent) return;
    }

    function restart() {
      token++;
      build();
      if (RM) { showAll(); return; }
      if (playing && inView) run();
      else if (!playing) apply(sc.steps[0], 0, true), (idx = 1);
    }

    tabs.forEach((t) => t.addEventListener("click", () => { tab = t.dataset.kuTab; if (!RM) playing = true, playBtn.classList.remove("is-paused"); restart(); }));
    tabs.forEach((t, i) => t.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const j = (i + (e.key === "ArrowRight" ? 1 : 2)) % 3;
      tabs[j].focus(); tabs[j].click();
    }));
    whoBtns.forEach((b) => b.addEventListener("click", () => { setWho(b.dataset.kuWho); if (!RM) playing = true, playBtn.classList.remove("is-paused"); restart(); }));
    playBtn.addEventListener("click", () => {
      if (RM) return;
      if (!playing && idx >= sc.steps.length) { build(); }
      setPlaying(!playing);
    });
    replayBtn.addEventListener("click", () => { if (!RM) playing = true, playBtn.classList.remove("is-paused"); restart(); });
    if (RM) { playBtn.hidden = true; }

    build();
    if (RM) { showAll(); inView = true; return; }
    if ("IntersectionObserver" in window) {
      new IntersectionObserver((es) => {
        const vis = es[0].isIntersecting;
        if (vis === inView) return;
        inView = vis;
        if (vis && playing) { started = true; run(); }
        else token++;
      }, { threshold: 0.25 }).observe(fig);
    } else { inView = true; run(); }
    window.addEventListener("resize", () => clearWire());
  }

  /* ================================================================ leaderboard */
  const tbody = $("[data-ku-lb]");
  if (tbody) initLeaderboard(tbody);

  function initLeaderboard(tbody) {
    const typeSel = $("[data-ku-type]");
    const cats = { general: $('[data-ku-cat="general"]'), personalized: $('[data-ku-cat="personalized"]'), proactive: $('[data-ku-cat="proactive"]') };
    const heads = $$(".ku-sort");
    const CAT = ["general", "personalized", "proactive"];
    const FAM = { general: "gen", personalized: "per", proactive: "pro" };
    const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    let rows = [], sort = { key: "overall", dir: "desc" };

    const checked = () => CAT.filter((c) => cats[c].checked);
    const allOn = () => checked().length === 3;
    const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);
    const fmt = (v) => (v === null || v === undefined || Number.isNaN(v) ? "–" : Number(v).toFixed(1));
    const fmtDate = (d) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d || ""); return m ? `${MONTHS[+m[2] - 1]} ${+m[3]}, ${m[1]}` : esc(d || ""); };

    // task-weighted score over the selected families (equals `overall` when all three are on)
    function overallOf(r) {
      if (allOn()) return r.overall;
      let s = 0, n = 0;
      checked().forEach((c) => {
        const v = r[c], t = r[c + "_tasks"];
        if (v === null || v === undefined || !t) return;
        s += v * t; n += t;
      });
      return n ? s / n : null;
    }

    function syncChecks() {
      const on = checked();
      CAT.forEach((c) => (cats[c].disabled = on.length === 1 && cats[c].checked));
    }

    function onCatChange() {
      syncChecks();
      const on = checked();
      if (on.length === 1) sort = { key: on[0], dir: "desc" };
      else if (CAT.includes(sort.key)) sort = { key: "overall", dir: "desc" };
      render();
    }

    function render() {
      const on = checked(), showOverall = on.length > 1;
      heads.forEach((h) => {
        const k = h.dataset.sort;
        h.hidden = k === "overall" ? !showOverall : !cats[k].checked;
        if (k === sort.key) h.setAttribute("aria-sort", sort.dir === "desc" ? "descending" : "ascending");
        else h.removeAttribute("aria-sort");
      });
      const data = rows.filter((r) => (typeSel.value === "all" || r.model_type === typeSel.value) && on.some((c) => r[c] !== null && r[c] !== undefined));
      const val = (r) => (sort.key === "overall" ? overallOf(r) : r[sort.key]);
      data.sort((a, b) => {
        const av = val(a) ?? -1, bv = val(b) ?? -1;
        return sort.dir === "desc" ? bv - av : av - bv;
      });
      if (!data.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="ku-lb__msg">No models match these filters.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map((r, i) => {
        const rank = i + 1;
        const agentic = r.model_type === "Agentic Framework";
        const name = r.link && r.link !== "#" ? `<a href="${esc(/^https?:\/\//.test(r.link) ? r.link : "https://" + r.link)}" target="_blank" rel="noopener">${esc(r.model)}</a>` : esc(r.model);
        const cell = (v, fam, extra = "") => {
          const w = v === null || v === undefined ? 0 : Math.max(0, Math.min(100, v));
          return `<td class="ku-sc ku-sc--${fam}${extra}"><span class="ku-sc__v">${fmt(v)}</span><span class="ku-sc__bar"><i style="width:${w}%"></i></span></td>`;
        };
        return `<tr>
          <td><span class="ku-rank${rank === 1 ? " ku-rank--1" : ""}">${rank}</span></td>
          <td><span class="ku-badge ${agentic ? "ku-badge--agentic" : "ku-badge--e2e"}">${agentic ? "Agentic" : "End-to-End"}</span></td>
          <td class="ku-model"><b>${name}</b><span>${esc(r.organization || "")}</span><span>${fmtDate(r.date)}</span></td>
          ${showOverall ? cell(overallOf(r), "overall", " ku-sc--overall") : ""}
          ${CAT.filter((c) => cats[c].checked).map((c) => cell(r[c], FAM[c])).join("")}
        </tr>`;
      }).join("");
    }

    heads.forEach((h) => $("button", h).addEventListener("click", () => {
      const k = h.dataset.sort;
      sort = sort.key === k ? { key: k, dir: sort.dir === "desc" ? "asc" : "desc" } : { key: k, dir: "desc" };
      render();
    }));
    typeSel.addEventListener("change", render);
    CAT.forEach((c) => cats[c].addEventListener("change", onCatChange));
    $("[data-ku-clear]").addEventListener("click", () => {
      typeSel.value = "all";
      CAT.forEach((c) => (cats[c].checked = true));
      sort = { key: "overall", dir: "desc" };
      syncChecks(); render();
    });

    fetch("leaderboard.json")
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then((d) => { rows = d.results || []; syncChecks(); render(); })
      .catch(() => { tbody.innerHTML = `<tr><td colspan="7" class="ku-lb__msg">Could not load leaderboard.json.</td></tr>`; });
  }
})();

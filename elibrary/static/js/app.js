const state = {
  books: [],
  query: "",
  type: "ALL",
  letter: "ALL",
  sort: "title",
};

const $ = (sel) => document.querySelector(sel);

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.hidden = true), 2400);
}

function fmtSize(bytes) {
  if (bytes > 1048576) return (bytes / 1048576).toFixed(1) + " MB";
  if (bytes > 1024) return Math.round(bytes / 1024) + " KB";
  return bytes + " B";
}

function shortTitle(t) {
  return t.length > 46 ? t.slice(0, 45) + "…" : t;
}

function fallbackColors(title) {
  const palette = [
    ["#3a2f78", "#171339"],
    ["#7c4a2d", "#2c160d"],
    ["#1f6f5b", "#0b2b23"],
    ["#41708f", "#122c3a"],
    ["#7a3f63", "#2c1220"],
    ["#5a5f33", "#1e2110"],
  ];
  let h = 0;
  for (const ch of title) h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return palette[h % palette.length];
}

function cardHTML(b) {
  const color = fallbackColors(b.title);
  const initial = [...b.title].find((c) => /[a-zA-Z\u0900-\u097F]/.test(c)) || "📖";
  const cover =
    b.cover && b.filetype !== "epub" && b.filetype !== "txt"
      ? `<img src="/covers/${b.cover}" alt="${b.title}" loading="lazy" onerror="this.remove()">`
      : `<div class="cover-fallback" style="--a1:${color[0]};--a2:${color[1]}">${b.filetype === "txt" ? "📝" : b.filetype === "epub" ? "📱" : initial}</div>`;
  const pages =
    b.filetype === "pdf" && b.pages ? `<span>${b.pages} पृ.</span>` : `<span>—</span>`;
  return `
    <article class="card" data-id="${b.id}" role="button" tabindex="0" aria-label="${b.title}"
      title="पढ़ें: ${b.title}">
      <div class="card-cover">${cover}</div>
      <div class="card-body">
        <div class="card-title">${shortTitle(b.title)}</div>
        <div class="card-meta">
          <span class="badge ${b.filetype}">${b.filetype}</span>
          ${pages}
          <span>${fmtSize(b.size)}</span>
        </div>
      </div>
    </article>`;
}

function render() {
  const grid = $("#grid");
  const empty = $("#empty");
  $("#skeleton").hidden = true;
  const q = state.query.trim().toLowerCase();
  let list = state.books.filter((b) => {
    if (state.type !== "ALL" && b.filetype !== state.type) return false;
    const first = [...(b.title.trim() || "?")][0];
    if (state.letter !== "ALL") {
      const grp = DEVANAGARI_GROUPS.find(g => g.letters.includes(state.letter));
      if (!grp || (first || "?") !== state.letter && !grp.letters.includes(first)) return false;
    }
    if (q && !b.title.toLowerCase().includes(q)) return false;
    return true;
  });
  list = [...list].sort((a, b) => {
    if (state.sort === "size") return b.size - a.size;
    if (state.sort === "pages") return (b.pages || 0) - (a.pages || 0);
    return String(a.title).localeCompare(String(b.title), "hi");
  });
  grid.innerHTML = list.map(cardHTML).join("");
  empty.hidden = list.length > 0;
  $("#countText").textContent =
    list.length === state.books.length
      ? `${state.books.length} उपन्यास उपलब्ध`
      : `${state.books.length} में से ${list.length} उपन्यास`;
  grid.querySelectorAll(".card").forEach((el) => {
    const open = () => {
      toast("रेडर खुल रहा है…");
      location.href = `/app/reader.html?id=${el.dataset.id}`;
    };
    el.addEventListener("click", open);
    el.addEventListener("keydown", (e) => e.key === "Enter" && open());
  });
}

const DEVANAGARI_GROUPS = [
  { label: "अ-आ", letters: ["अ", "आ"] },
  { label: "इ-उ", letters: ["इ", "उ"] },
  { label: "ए-ऑ", letters: ["ए", "ऎ", "ऐ", "ओ", "औ", "ऑ"] },
  { label: "क-ग", letters: ["क", "ख", "ग"] },
  { label: "च-छ", letters: ["च", "छ"] },
  { label: "ज-ज", letters: ["ज", "झ"] },
  { label: "ट-त", letters: ["ट", "ठ", "ड", "ढ", "त", "थ", "द", "ध"] },
  { label: "न-फ", letters: ["न", "प", "फ"] },
  { label: "ब-भ", letters: ["ब", "भ"] },
  { label: "म-य", letters: ["म", "य"] },
  { label: "र-ल", letters: ["र", "ल"] },
  { label: "व-व", letters: ["व"] },
  { label: "श-स", letters: ["श", "ष", "स"] },
  { label: "ह", letters: ["ह"] },
];

function buildChips() {
  const typeRow = $("#typeChips");
  const letterRow = $("#letterChips");
  const types = ["ALL", ...new Set(state.books.map((b) => b.filetype))];
  typeRow.innerHTML = types
    .map(
      (t) =>
        `<button class="chip ${state.type === t ? "on" : ""}" data-k="type" data-v="${t}">${t === "ALL" ? "सभी" : t.toUpperCase()}</button>`
    )
    .join("");
  const booksWithDevanagari = state.books.filter((b) => {
    const first = [...(b.title.trim() || "?")][0];
    return /[\u0900-\u097F]/.test(first || "");
  });
  const letterRow2 = DEVANAGARI_GROUPS.filter(g =>
    g.letters.some(l => booksWithDevanagari.some(b => [...(b.title.trim() || "?")][0] === l))
  );
  const currentGroup = DEVANAGARI_GROUPS.find(g => g.letters.includes(state.letter));
  letterRow.innerHTML = `<button class="chip ${state.letter === "ALL" ? "on" : ""}" data-k="letter" data-v="ALL">अ-ह</button>` +
    letterRow2
      .map(
        (g) =>
          `<button class="chip ${currentGroup === g ? "on" : ""}" data-k="letter" data-v="${g.letters[0]}">${g.label}</button>`
      )
      .join("");
  document.querySelectorAll(".chip").forEach((ch) =>
    ch.addEventListener("click", () => {
      if (ch.dataset.k === "letter") {
        const v = ch.dataset.v;
        if (v === "ALL") {
          state.letter = "ALL";
        } else {
          const grp = DEVANAGARI_GROUPS.find(g => g.letters.includes(v));
          if (grp) state.letter = grp.letters[0];
        }
      } else {
        state[ch.dataset.k] = ch.dataset.v;
      }
      buildChips();
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    })
  );
}

async function load() {
  try {
    const res = await fetch("/api/novels");
    if (!res.ok) throw new Error(res.status);
    state.books = await res.json();
  } catch (err) {
    $("#skeleton").hidden = true;
    $("#empty").hidden = false;
    document.querySelector("#empty p").textContent = "सर्वर से संपर्क नहीं — /api/novels विफल";
    console.error(err);
    return;
  }
  buildChips();
  render();
}

function initTheme() {
  const saved = localStorage.getItem("eli_theme") || "dark";
  document.documentElement.dataset.theme = saved;
  $("#themeToggle").textContent = saved === "dark" ? "☀️" : "🌙";
  $("#themeToggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("eli_theme", next);
    $("#themeToggle").textContent = next === "dark" ? "☀️" : "🌙";
  });
}

$("#searchInput").addEventListener("input", (e) => {
  state.query = e.target.value;
  clearTimeout(state._t);
  state._t = setTimeout(render, 140);
});
$("#sortSel").addEventListener("change", (e) => {
  state.sort = e.target.value;
  render();
});

initTheme();
load();
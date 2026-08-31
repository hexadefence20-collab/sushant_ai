import * as pdfjsLib from "/vendor/pdf.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/vendor/pdf.worker.mjs";

const params = new URLSearchParams(location.search);
const bookId = params.get("id");
const $ = (s) => document.querySelector(s);

let book = null;
let sType = null;
let streamUrl = null;
let current = 1;
let pages = 1;
let pdfDoc = null;
let scale = 1.2;
let renderTask = null;

const PROGRESS_KEY = "eli_progress_";

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(t._h);
  t._h = setTimeout(() => (t.hidden = true), 2200);
}

function guard() {
  document.addEventListener("contextmenu", (e) => e.preventDefault());
  document.addEventListener("selectstart", (e) => e.preventDefault());
  document.addEventListener("dragstart", (e) => {
    if (e.target.closest("#pdfCanvas")) e.preventDefault();
  });
  window.addEventListener("keydown", (e) => {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && ["s", "p", "u"].includes(e.key.toLowerCase())) e.preventDefault();
    if (e.key === "F12") e.preventDefault();
  });
  window.addEventListener("beforeprint", (e) => e.preventDefault());
  window.addEventListener("print", (e) => e.preventDefault());
}

function watermarkCanvas(canvas) {
  try {
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    if (w < 50 || h < 50) return;
    ctx.save();
    ctx.globalAlpha = 0.05;
    const light = document.documentElement.dataset.theme === "light";
    ctx.fillStyle = light ? "#000" : "#fff";
    ctx.font = `${Math.max(18, w / 30)}px sans-serif`;
    ctx.rotate(-Math.PI / 6);
    for (let x = -h; x < w; x += w / 3.4) {
      for (let y = 0; y < h + w; y += h / 5) {
        ctx.fillText("Sushant Kumar eLibrary", x, y);
      }
    }
    ctx.restore();
  } catch (_) {}
}

function saveProgress() {
  try {
    localStorage.setItem(PROGRESS_KEY + bookId, JSON.stringify({ page: current, at: Date.now() }));
  } catch (_) {}
}

function loadProgress() {
  try {
    const raw = localStorage.getItem(PROGRESS_KEY + bookId);
    return raw ? JSON.parse(raw).page : 0;
  } catch (_) {
    return 0;
  }
}

function setProgressBar() {
  const pct = sType === "pdf" ? (current / Math.max(1, pages)) * 100 : 0;
  $("#progressFill").style.width = pct.toFixed(1) + "%";
}

function setPageInfo() {
  if (sType === "pdf") {
    $("#pageInfo").textContent = `पृष्ठ ${current} / ${pages}`;
  } else if (sType === "epub") {
    $("#pageInfo").textContent = "ई-पुस्तक";
  } else {
    $("#pageInfo").textContent = "";
  }
  if (sType === "pdf") {
    $("#pageInput").value = current;
    $("#pageSlider").value = current;
  }
}

function setNavTargets() {
  $("#navPrev").disabled = current <= 1;
  $("#navNext").disabled = current >= pages;
  $("#nextBtn").style.opacity = current >= pages ? ".35" : "1";
  $("#prevBtn").style.opacity = current <= 1 ? ".35" : "1";
}

function busy(active) {
  document.body.dataset.busy = active ? "1" : "0";
}

async function renderPdfPage() {
  if (!pdfDoc) return;
  if (current < 1 || current > pages) return;
  const canvas = $("#pdfCanvas");
  const ctx = canvas.getContext("2d", { alpha: false });
  if (renderTask) {
    renderTask.cancel();
    renderTask = null;
  }
  busy(true);
  const page = await pdfDoc.getPage(current);
  const vp = page.getViewport({ scale });
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.floor(vp.width * dpr);
  canvas.height = Math.floor(vp.height * dpr);
  const out = page.getViewport({ scale: scale * dpr });
  const task = page.render({ canvasContext: ctx, viewport: out, background: "#ffffff" });
  renderTask = task;
  try {
    await task;
  } finally {
    renderTask = null;
  }
  canvas.style.width = canvas.width / dpr + "px";
  canvas.style.height = canvas.height / dpr + "px";
  watermarkCanvas(canvas);
  setPageInfo();
  setProgressBar();
  setNavTargets();
  saveProgress();
  try {
    page.cleanup();
  } catch (_) {}
  busy(false);
}

async function initPdf() {
  const canvas = document.createElement("canvas");
  canvas.id = "pdfCanvas";
  $("#stage").appendChild(canvas);
  document.querySelector(".reader-main").classList.add("has-pager");
  pdfDoc = await pdfjsLib.getDocument({ url: streamUrl, useSystemFonts: true, disableAutoFetch: false }).promise;
  pages = pdfDoc.numPages;
  $("#rMeta").textContent = `${pages} पृष्ठ · ${book.filetype.toUpperCase()} · केवल पढ़ने के लिए`;
  const saved = loadProgress();
  current = saved > 1 && saved <= pages ? saved : 1;
  if (saved > 1 && saved <= pages) {
    toast(`पढ़ाई पृष्ठ ${saved} से जारी रखें`);
  }
  syncPager();
  await renderPdfPage();
}

function initTxt() {
  const art = document.createElement("article");
  art.className = "reader-article";
  $("#stage").appendChild(art);
  document.querySelector(".reader-main").classList.remove("has-pager");
  $("#pageInfo").textContent = "";
  $("#progressFill").style.width = "0%";
  $("#readerNav").hidden = true;
  fetch(streamUrl)
    .then((r) => {
      if (!r.ok) throw new Error();
      return r.text();
    })
    .then((txt) => {
      art.textContent = txt;
      $("#rMeta").textContent = `${tidySize(book.size)} · टेक्स्ट · केवल पढ़ने के लिए`;
    })
    .catch(() => toast("पाठ लोड नहीं हुआ"));
}

function tidySize(bytes) {
  return bytes > 1048576 ? (bytes / 1048576).toFixed(1) + " MB" : Math.round(bytes / 1024) + " KB";
}

function syncPager() {
  $("#readerNav").hidden = false;
  $("#pageSlider").min = 1;
  $("#pageSlider").max = pages;
  $("#pageSlider").value = current;
  $("#pageInput").min = 1;
  $("#pageInput").max = pages;
  $("#pageInput").value = current;
  setNavTargets();
}

function goToPage(n, silent) {
  if (sType !== "pdf" || !pdfDoc) return;
  n = Math.max(1, Math.min(pages, n | 0));
  if (n === current) return;
  current = n;
  $("#pageInfo").textContent = `पृष्ठ ${n} / ${pages}`;
  $("#pageInput").value = n;
  $("#pageSlider").value = n;
  renderPdfPage().then(() => {
    if (!silent) toast(`पृष्ठ ${n} खुल गया`);
  });
}

function openPagesModal() {
  const modal = $("#pagesModal");
  const grid = $("#pagesGrid");
  $("#modalRange").textContent =
    `गोदान · कुल ${pages} पृष्ठ · केवल पढ़ने के लिए`;
  grid.innerHTML = "";
  const frag = document.createDocumentFragment();
  for (let i = 1; i <= pages; i++) {
    const cell = document.createElement("button");
    cell.className = "page-cell" + (i === current ? " cur" : "");
    cell.textContent = i;
    cell.addEventListener("click", () => {
      goToPage(i);
      modal.hidden = true;
    });
    frag.appendChild(cell);
  }
  grid.appendChild(frag);
  modal.hidden = false;
  const search = $("#modalSearch");
  search.value = "";
  search.focus();
  grid.scrollTop = 0;
}

async function initEpub() {
  const ePub = window.ePub;
  if (!ePub) {
    toast("EPUB पाठक उपलब्ध नहीं");
    return;
  }
  const holder = document.createElement("div");
  holder.id = "epubView";
  $("#stage").appendChild(holder);
  document.querySelector(".reader-main").classList.add("has-pager");
  const bookEpub = ePub(streamUrl, { openAs: "epub", spread: "none" });
  const rendition = bookEpub.renderTo(holder, { width: "100%", height: "100%", spread: "none", flow: "paginated" });

  rendition.display().then(() => {
    $("#rMeta").textContent = `ई-पुस्तक · केवल पढ़ने के लिए`;
  });
  rendition.on("rendered", () => {
    setPageInfo();
    setProgressBar();
  });
  window._eliEpub = {
    goForward: () => rendition.next().catch(() => {}),
    goBack: () => rendition.prev().catch(() => {}),
  };
  current = 0;
}

async function boot() {
  guard();
  if (!bookId) {
    location.href = "/app";
    return;
  }
  try {
    const detail = await (await fetch(`/api/novels/${bookId}`)).json();
    const ticket = await (await fetch(`/api/read/${bookId}/ticket`, { method: "POST" })).json();
    book = detail;
    sType = detail.filetype;
    streamUrl = `/api/read/${bookId}/stream?tk=${encodeURIComponent(ticket.stream)}`;
    document.title = `${detail.title} — Sushant Kumar eLibrary`;
    $("#rTitle").textContent = detail.title;
    if (sType === "pdf") await initPdf();
    else if (sType === "txt") initTxt();
    else if (sType === "epub") await initEpub();
    else toast("इस फ़ाइल प्रकार के लिए रेडर नहीं है");
  } catch (err) {
    console.error(err);
    $("#rTitle").textContent = "पुस्तक खोलने में समस्या — दोबारा कोशिश करें";
    toast("पुस्तक लोड नहीं हुई");
  }
}

function bindEvents() {
  $("#backBtn").addEventListener("click", () => (location.href = "/app"));
  $("#zoomIn").addEventListener("click", () => {
    if (sType !== "pdf" || !pdfDoc) return;
    scale = Math.min(4, +(scale * 1.2).toFixed(2));
    $("#rZoom").textContent = Math.round(scale * 100) + "%";
    renderPdfPage();
  });
  $("#zoomOut").addEventListener("click", () => {
    if (sType !== "pdf" || !pdfDoc) return;
    scale = Math.max(0.4, +(scale / 1.2).toFixed(2));
    $("#rZoom").textContent = Math.round(scale * 100) + "%";
    renderPdfPage();
  });
  $("#themeBtn").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("eli_theme", next);
    $("#themeBtn").textContent = next === "dark" ? "🌙" : "☀️";
    if (sType === "pdf" && pdfDoc) renderPdfPage();
  });
  $("#fullBtn").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen().catch(() => {});
  });
  $("#prevBtn").addEventListener("click", () => {
    if (sType === "pdf") goToPage(current - 1, true);
    else if (sType === "epub" && window._eliEpub) window._eliEpub.goBack();
  });
  $("#nextBtn").addEventListener("click", () => {
    if (sType === "pdf") goToPage(current + 1, true);
    else if (sType === "epub" && window._eliEpub) window._eliEpub.goForward();
  });
  $("#navPrev").addEventListener("click", () => {
    if (sType === "pdf") goToPage(current - 1, true);
    else if (sType === "epub" && window._eliEpub) window._eliEpub.goBack();
  });
  $("#navNext").addEventListener("click", () => {
    if (sType === "pdf") goToPage(current + 1, true);
    else if (sType === "epub" && window._eliEpub) window._eliEpub.goForward();
  });
  $("#pageSlider").addEventListener("input", (e) => {
    const n = +e.target.value;
    $("#pageInput").value = n;
    $("#pageInfo").textContent = `पृष्ठ ${n} / ${pages}`;
  });
  $("#pageSlider").addEventListener("change", (e) => goToPage(+e.target.value, true));
  $("#pageInput").addEventListener("change", (e) => goToPage(+e.target.value));
  $("#gotoBtn").addEventListener("click", () => goToPage(+$("#pageInput").value));
  $("#pageInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") goToPage(+e.target.value);
  });
  $("#pagesBtn").addEventListener("click", openPagesModal);
  $("#pageInfo").addEventListener("click", openPagesModal);
  $("#modalClose").addEventListener("click", () => ($("#pagesModal").hidden = true));
  $("#modalSearch").addEventListener("input", (e) => {
    const n = +e.target.value;
    if (!n) return;
    [...$("#pagesGrid").querySelectorAll(".page-cell")].forEach((c) => {
      if (+c.textContent === n) c.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  });
  window.addEventListener("keydown", (e) => {
    if (e.target.matches("input,textarea")) return;
    if (sType === "pdf") {
      if (e.key === "ArrowRight") {
        e.preventDefault();
        goToPage(current + 1, true);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        goToPage(current - 1, true);
      }
    }
    if (e.key === "Escape" && !$("#pagesModal").hidden) $("#pagesModal").hidden = true;
    if (e.key === "Escape" && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if ((e.key === "g" || e.key === "G") && !e.ctrlKey && !e.metaKey) {
      openPagesModal();
    }
  });
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (sType === "pdf" && pdfDoc) renderPdfPage();
    }, 180);
  });
}

function initTheme() {
  const saved = localStorage.getItem("eli_theme") || "dark";
  document.documentElement.dataset.theme = saved;
  $("#themeBtn").textContent = saved === "dark" ? "🌙" : "☀️";
}

initTheme();
bindEvents();
boot();
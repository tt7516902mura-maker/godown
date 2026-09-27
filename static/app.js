const TRANSLATIONS = {
  ja: {
    tagline: "リンクを渡すと、荷物を受け取って梱包します",
    status_idle: "待機中",
    status_running: "受け取り中",
    status_done: "受け取り完了",
    status_error: "失敗",
    password_toggle: "ロック解除コードあり",
    password_placeholder: "パスワード",
    check_button: "内容を確認",
    checking: "内容を確認中...",
    start_button: "受け取り開始",
    download_button: "ダウンロード！",
    select_all: "全部選ぶ",
    selected_summary: "{count}個選択中 ({size})",
    manifest_received: "受け付けました...",
    err_no_connection: "サーバーに接続できませんでした。",
    err_start_failed: "開始に失敗しました",
    err_check_failed: "内容の確認に失敗しました",
    err_no_selection: "ファイルを1つ以上選んでください",
    err_generic: "エラーが発生しました。上の記録を確認してください。",
    err_lost_connection: "サーバーとの通信が不安定です。再接続しています...",
    err_gave_up: "サーバーに接続できませんでした。時間をおいて試してください。",
  },
  en: {
    tagline: "Give it a link — it fetches the goods and packs them up.",
    status_idle: "Idle",
    status_running: "Receiving",
    status_done: "Delivered",
    status_error: "Failed",
    password_toggle: "Has an unlock code",
    password_placeholder: "Password",
    check_button: "Check contents",
    checking: "Checking contents...",
    start_button: "Start pickup",
    download_button: "Download!",
    select_all: "Select all",
    selected_summary: "{count} selected ({size})",
    manifest_received: "Received...",
    err_no_connection: "Couldn't connect to the server.",
    err_start_failed: "Failed to start",
    err_check_failed: "Failed to check contents",
    err_no_selection: "Select at least one file",
    err_generic: "Something went wrong. Check the log above.",
    err_lost_connection: "Connection is unstable. Reconnecting...",
    err_gave_up: "Couldn't reach the server. Please try again later.",
  },
};

const LANG_STORAGE_KEY = "godown_lang";

const ICONS = {
  image:
    '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="16" rx="1" stroke="currentColor" stroke-width="1.4"/><circle cx="8.5" cy="9.5" r="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M21 16l-5.5-5.5L4 21" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  video:
    '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="5" width="14" height="14" rx="1" stroke="currentColor" stroke-width="1.4"/><path d="M17 9.5L21 7v10l-4-2.5" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  audio:
    '<svg viewBox="0 0 24 24" fill="none"><path d="M9 18V6l10-2v12" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><circle cx="6.5" cy="18" r="2.5" stroke="currentColor" stroke-width="1.4"/><circle cx="16.5" cy="16" r="2.5" stroke="currentColor" stroke-width="1.4"/></svg>',
  archive:
    '<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="16" height="16" rx="1" stroke="currentColor" stroke-width="1.4"/><path d="M9 4v16M12 8h2M12 12h2M12 16h2" stroke="currentColor" stroke-width="1.4"/></svg>',
  document:
    '<svg viewBox="0 0 24 24" fill="none"><path d="M6 3h9l4 4v14H6z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M14 3v5h5" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M9 13h6M9 17h6" stroke="currentColor" stroke-width="1.4"/></svg>',
  generic:
    '<svg viewBox="0 0 24 24" fill="none"><path d="M6 3h9l4 4v14H6z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M14 3v5h5" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
};

function iconKeyFor(mimetype, name) {
  const mime = (mimetype || "").toLowerCase();
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  if (mime === "application/pdf" || mime.startsWith("text/")) return "document";
  if (/zip|rar|7z|tar|gzip/.test(mime)) return "archive";

  const ext = (name.split(".").pop() || "").toLowerCase();
  if (["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"].includes(ext)) return "image";
  if (["mp4", "mkv", "mov", "avi", "webm"].includes(ext)) return "video";
  if (["mp3", "wav", "flac", "m4a", "ogg"].includes(ext)) return "audio";
  if (["pdf", "txt", "doc", "docx"].includes(ext)) return "document";
  if (["zip", "rar", "7z", "tar", "gz"].includes(ext)) return "archive";
  return "generic";
}

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "0 KB";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

const checkForm = document.getElementById("checkForm");
const usePasswordEl = document.getElementById("usePassword");
const passwordEl = document.getElementById("password");
const urlEl = document.getElementById("url");
const checkBtn = document.getElementById("checkBtn");
const statusChip = document.getElementById("statusChip");
const fileListSection = document.getElementById("fileListSection");
const fileListEl = document.getElementById("fileList");
const selectAllEl = document.getElementById("selectAll");
const selectionSummaryEl = document.getElementById("selectionSummary");
const startBtn = document.getElementById("startBtn");
const zipNameEl = document.getElementById("zipName");
const manifest = document.getElementById("manifest");
const manifestList = document.getElementById("manifestList");
const resultSection = document.getElementById("resultSection");
const langToggle = document.getElementById("langToggle");

let currentLang = "ja";
let lastKnownStatusState = "idle";
let currentListing = null; // { listing_id, files: [{id, name, size, mimetype, has_thumbnail, rel_dir}] }
const selectedIds = new Set();

function detectInitialLang() {
  try {
    const saved = localStorage.getItem(LANG_STORAGE_KEY);
    if (saved === "ja" || saved === "en") return saved;
  } catch (e) {
    /* localStorageが使えない環境でも致命的にしない */
  }
  return navigator.language && navigator.language.toLowerCase().startsWith("en") ? "en" : "ja";
}

function tr(key) {
  return (TRANSLATIONS[currentLang] && TRANSLATIONS[currentLang][key]) || TRANSLATIONS.ja[key] || key;
}

function applyTranslations() {
  document.documentElement.lang = currentLang;
  langToggle.textContent = currentLang === "ja" ? "EN" : "JA";

  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = tr(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = tr(el.dataset.i18nPlaceholder);
  });

  setStatus(lastKnownStatusState);
  updateSelectionSummary();
}

function setLang(lang) {
  currentLang = lang === "en" ? "en" : "ja";
  try {
    localStorage.setItem(LANG_STORAGE_KEY, currentLang);
  } catch (e) {
    /* 保存できなくても致命的にしない */
  }
  applyTranslations();
}

langToggle.addEventListener("click", () => {
  setLang(currentLang === "ja" ? "en" : "ja");
});

usePasswordEl.addEventListener("change", () => {
  passwordEl.classList.toggle("hidden", !usePasswordEl.checked);
});

function setStatus(state) {
  lastKnownStatusState = state;
  statusChip.dataset.state = state;
  const key = { idle: "status_idle", running: "status_running", done: "status_done", error: "status_error" }[state];
  statusChip.textContent = tr(key);
}

function renderManifest(lines) {
  manifestList.innerHTML = "";
  lines.forEach((line) => {
    const li = document.createElement("li");
    li.textContent = line;
    manifestList.appendChild(li);
  });
  manifest.scrollTop = manifest.scrollHeight;
}

async function parseJsonSafe(res) {
  try {
    return await res.json();
  } catch (e) {
    return null;
  }
}

function showFatalError(message) {
  setStatus("error");
  resultSection.classList.remove("hidden");
  resultSection.className = "stamp error";
  resultSection.textContent = message;
  startBtn.disabled = false;
  checkBtn.disabled = false;
}

// ---------------- ステップ1: 内容の確認(ファイル一覧の取得) ----------------

function renderFileList(files) {
  fileListEl.innerHTML = "";
  selectedIds.clear();

  files.forEach((file) => {
    selectedIds.add(file.id);

    const li = document.createElement("li");
    li.className = "file-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = true;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedIds.add(file.id);
      } else {
        selectedIds.delete(file.id);
      }
      syncSelectAllState(files.length);
      updateSelectionSummary();
    });

    const thumbWrap = document.createElement("div");
    thumbWrap.className = "file-thumb";
    const iconKey = iconKeyFor(file.mimetype, file.name);

    if (file.has_thumbnail) {
      const img = document.createElement("img");
      img.src = `/api/thumbnail/${currentListing.listing_id}/${file.id}`;
      img.alt = "";
      img.loading = "lazy";
      img.addEventListener("error", () => {
        thumbWrap.innerHTML = ICONS[iconKey];
      });
      thumbWrap.appendChild(img);
    } else {
      thumbWrap.innerHTML = ICONS[iconKey];
    }

    const meta = document.createElement("div");
    meta.className = "file-meta";
    const nameEl = document.createElement("div");
    nameEl.className = "file-name";
    nameEl.textContent = file.rel_dir ? `${file.rel_dir}/${file.name}` : file.name;
    const sizeEl = document.createElement("div");
    sizeEl.className = "file-size";
    sizeEl.textContent = formatBytes(file.size);
    meta.appendChild(nameEl);
    meta.appendChild(sizeEl);

    li.appendChild(checkbox);
    li.appendChild(thumbWrap);
    li.appendChild(meta);
    fileListEl.appendChild(li);
  });

  syncSelectAllState(files.length);
  updateSelectionSummary();
  fileListSection.classList.remove("hidden");
}

function syncSelectAllState(totalCount) {
  selectAllEl.checked = selectedIds.size === totalCount;
  selectAllEl.indeterminate = selectedIds.size > 0 && selectedIds.size < totalCount;
}

function updateSelectionSummary() {
  if (!currentListing) return;
  const totalSize = currentListing.files
    .filter((f) => selectedIds.has(f.id))
    .reduce((sum, f) => sum + (f.size || 0), 0);
  selectionSummaryEl.textContent = tr("selected_summary")
    .replace("{count}", String(selectedIds.size))
    .replace("{size}", formatBytes(totalSize));
  startBtn.disabled = selectedIds.size === 0;
}

selectAllEl.addEventListener("change", () => {
  if (!currentListing) return;
  const checkboxes = fileListEl.querySelectorAll("input[type=checkbox]");
  if (selectAllEl.checked) {
    currentListing.files.forEach((f) => selectedIds.add(f.id));
    checkboxes.forEach((cb) => {
      cb.checked = true;
    });
  } else {
    selectedIds.clear();
    checkboxes.forEach((cb) => {
      cb.checked = false;
    });
  }
  updateSelectionSummary();
});

checkForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  const url = urlEl.value.trim();
  if (!url) {
    urlEl.focus();
    return;
  }

  checkBtn.disabled = true;
  fileListSection.classList.add("hidden");
  resultSection.classList.add("hidden");
  manifest.classList.add("hidden");
  setStatus("running");
  statusChip.textContent = tr("checking");

  const body = {
    url,
    password: usePasswordEl.checked ? passwordEl.value : null,
    lang: currentLang,
  };

  let res;
  try {
    res = await fetch("/api/list", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (e) {
    checkBtn.disabled = false;
    showFatalError(tr("err_no_connection"));
    return;
  }

  const data = await parseJsonSafe(res);
  checkBtn.disabled = false;

  if (!res.ok || !data) {
    showFatalError((data && data.error) || tr("err_check_failed"));
    return;
  }

  setStatus("idle");
  currentListing = data;
  zipNameEl.value = data.content_id || "";
  renderFileList(data.files);
});

// ---------------- ステップ2: 選択したファイルのダウンロード ----------------

async function pollStatus(jobId, failCount = 0) {
  let res;
  try {
    res = await fetch(`/api/status/${jobId}`);
  } catch (e) {
    if (failCount < 6) {
      renderManifest([tr("err_lost_connection")]);
      setTimeout(() => pollStatus(jobId, failCount + 1), 1500);
      return;
    }
    showFatalError(tr("err_gave_up"));
    return;
  }

  const job = await parseJsonSafe(res);
  if (!res.ok || !job || job.error) {
    if (failCount < 6) {
      setTimeout(() => pollStatus(jobId, failCount + 1), 1500);
      return;
    }
    showFatalError(tr("err_gave_up"));
    return;
  }

  renderManifest(job.log || []);

  if (job.status === "running") {
    setTimeout(() => pollStatus(jobId, 0), 800);
    return;
  }

  startBtn.disabled = false;
  resultSection.classList.remove("hidden");

  if (job.status === "done") {
    setStatus("done");
    resultSection.className = "stamp ok";
    resultSection.innerHTML = "";
    const link = document.createElement("a");
    link.href = `/download/${jobId}?lang=${currentLang}`;
    link.className = "download-link";
    link.textContent = tr("download_button");
    resultSection.appendChild(link);
  } else {
    setStatus("error");
    resultSection.className = "stamp error";
    resultSection.textContent = tr("err_generic");
  }
}

startBtn.addEventListener("click", async () => {
  if (!currentListing || selectedIds.size === 0) {
    showFatalError(tr("err_no_selection"));
    return;
  }

  startBtn.disabled = true;
  setStatus("running");
  manifest.classList.remove("hidden");
  resultSection.classList.add("hidden");
  renderManifest([tr("manifest_received")]);

  const body = {
    listing_id: currentListing.listing_id,
    selected_ids: Array.from(selectedIds),
    zip_name: zipNameEl.value.trim(),
    lang: currentLang,
  };

  let res;
  try {
    res = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (e) {
    showFatalError(tr("err_no_connection"));
    return;
  }

  const data = await parseJsonSafe(res);

  if (!res.ok || !data) {
    showFatalError((data && data.error) || tr("err_start_failed"));
    return;
  }

  if (!data.job_id) {
    showFatalError(tr("err_start_failed"));
    return;
  }

  pollStatus(data.job_id);
});

setLang(detectInitialLang());
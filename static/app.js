const TRANSLATIONS = {
  ja: {
    tagline: "リンクを渡すと、荷物を受け取って梱包します",
    status_idle: "待機中",
    status_running: "受け取り中",
    status_done: "受け取り完了",
    status_error: "失敗",
    password_toggle: "ロック解除コードあり",
    password_placeholder: "パスワード",
    start_button: "受け取り開始",
    download_button: "ダウンロード！",
    manifest_received: "受け付けました...",
    err_no_connection: "サーバーに接続できませんでした。",
    err_start_failed: "開始に失敗しました",
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
    start_button: "Start pickup",
    download_button: "Download!",
    manifest_received: "Received...",
    err_no_connection: "Couldn't connect to the server.",
    err_start_failed: "Failed to start",
    err_generic: "Something went wrong. Check the log above.",
    err_lost_connection: "Connection is unstable. Reconnecting...",
    err_gave_up: "Couldn't reach the server. Please try again later.",
  },
};

const LANG_STORAGE_KEY = "godown_lang";

const form = document.getElementById("intakeForm");
const usePasswordEl = document.getElementById("usePassword");
const passwordEl = document.getElementById("password");
const urlEl = document.getElementById("url");
const startBtn = document.getElementById("startBtn");
const statusChip = document.getElementById("statusChip");
const manifest = document.getElementById("manifest");
const manifestList = document.getElementById("manifestList");
const resultSection = document.getElementById("resultSection");
const langToggle = document.getElementById("langToggle");

let currentLang = "ja";
let lastKnownStatusState = "idle";

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

  // ステータスチップは状態に応じたラベルで出し直す(進行中に切り替えられても文言がずれないように)
  setStatus(lastKnownStatusState);
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
}

async function pollStatus(jobId, failCount = 0) {
  let res;
  try {
    res = await fetch(`/api/status/${jobId}`);
  } catch (e) {
    // ネットワーク断・Renderのコールドスタート直後などは少しリトライしてから諦める
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const url = urlEl.value.trim();
  if (!url) {
    urlEl.focus();
    return;
  }

  startBtn.disabled = true;
  setStatus("running");
  manifest.classList.remove("hidden");
  resultSection.classList.add("hidden");
  renderManifest([tr("manifest_received")]);

  const body = {
    url,
    password: usePasswordEl.checked ? passwordEl.value : null,
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
    const message = (data && data.error) || tr("err_start_failed");
    showFatalError(message);
    return;
  }

  if (!data.job_id) {
    showFatalError(tr("err_start_failed"));
    return;
  }

  pollStatus(data.job_id);
});

setLang(detectInitialLang());

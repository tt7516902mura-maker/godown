const form = document.getElementById("intakeForm");
const usePasswordEl = document.getElementById("usePassword");
const passwordEl = document.getElementById("password");
const urlEl = document.getElementById("url");
const startBtn = document.getElementById("startBtn");
const statusChip = document.getElementById("statusChip");
const manifest = document.getElementById("manifest");
const manifestList = document.getElementById("manifestList");
const resultSection = document.getElementById("resultSection");

usePasswordEl.addEventListener("change", () => {
  passwordEl.classList.toggle("hidden", !usePasswordEl.checked);
});

function setStatus(state, label) {
  statusChip.dataset.state = state;
  statusChip.textContent = label;
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

async function pollStatus(jobId) {
  const res = await fetch(`/api/status/${jobId}`);
  const job = await res.json();

  renderManifest(job.log);

  if (job.status === "running") {
    setTimeout(() => pollStatus(jobId), 800);
    return;
  }

  startBtn.disabled = false;
  resultSection.classList.remove("hidden");

  if (job.status === "done") {
    setStatus("done", "受け取り完了");
    resultSection.className = "stamp ok";
    resultSection.innerHTML = "";
    const link = document.createElement("a");
    link.href = `/download/${jobId}`;
    link.className = "download-link";
    link.textContent = "ZIPをダウンロード";
    resultSection.appendChild(link);
  } else {
    setStatus("error", "失敗");
    resultSection.className = "stamp error";
    resultSection.textContent = "エラーが発生しました。上の記録を確認してください。";
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
  setStatus("running", "受け取り中");
  manifest.classList.remove("hidden");
  resultSection.classList.add("hidden");
  renderManifest(["受け付けました..."]);

  const body = {
    url,
    password: usePasswordEl.checked ? passwordEl.value : null,
  };

  let res;
  try {
    res = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (e) {
    setStatus("error", "失敗");
    renderManifest(["サーバーに接続できませんでした。"]);
    startBtn.disabled = false;
    return;
  }

  if (!res.ok) {
    const err = await res.json();
    setStatus("error", "失敗");
    renderManifest([err.error || "開始に失敗しました"]);
    startBtn.disabled = false;
    return;
  }

  const { job_id } = await res.json();
  pollStatus(job_id);
});

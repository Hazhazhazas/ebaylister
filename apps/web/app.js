// ====== CONFIG (set these) ======
const API_BASE = "https://YOUR-CLOUD-RUN-URL"; // e.g. https://upload-api-xxxxx.a.run.app
const APP_TOKEN = "CHANGE_ME_LONG_RANDOM";     // must match apps/api APP_TOKEN env var
// ================================

const fileInput = document.getElementById("fileInput");
const clearBtn = document.getElementById("clearBtn");
const uploadBtn = document.getElementById("uploadBtn");
const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");

let items = []; // { id, file, previewUrl, blobForUpload }

function setStatus(msg) {
  statusEl.textContent = msg;
}

function uid() {
  return crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random());
}

// Compress to ~1600px longest edge, JPEG quality ~0.85
async function compressImage(file) {
  const img = await fileToImage(file);

  const maxEdge = 1600;
  let { width, height } = img;

  const scale = Math.min(1, maxEdge / Math.max(width, height));
  width = Math.round(width * scale);
  height = Math.round(height * scale);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;

  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, width, height);

  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", 0.85)
  );

  if (!blob) throw new Error("Compression failed");
  return blob;
}

function fileToImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = reject;
    img.src = url;
  });
}

function render() {
  grid.innerHTML = "";

  items.forEach((it, idx) => {
    const card = document.createElement("div");
    card.className = "card";
    card.draggable = true;
    card.dataset.id = it.id;

    const badge = document.createElement("div");
    badge.className = "badge";
    badge.textContent = `${idx + 1}`;

    const img = document.createElement("img");
    img.src = it.previewUrl;

    // tap to delete
    card.addEventListener("click", () => {
      items = items.filter(x => x.id !== it.id);
      URL.revokeObjectURL(it.previewUrl);
      render();
    });

    // drag reorder
    card.addEventListener("dragstart", (e) => {
      e.dataTransfer.setData("text/plain", it.id);
    });
    card.addEventListener("dragover", (e) => e.preventDefault());
    card.addEventListener("drop", (e) => {
      e.preventDefault();
      const fromId = e.dataTransfer.getData("text/plain");
      const toId = it.id;
      reorder(fromId, toId);
      render();
    });

    card.appendChild(img);
    card.appendChild(badge);
    grid.appendChild(card);
  });

  setStatus(`Selected: ${items.length}/20`);
}

function reorder(fromId, toId) {
  const fromIndex = items.findIndex(x => x.id === fromId);
  const toIndex = items.findIndex(x => x.id === toId);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return;
  const [moved] = items.splice(fromIndex, 1);
  items.splice(toIndex, 0, moved);
}

fileInput.addEventListener("change", async (e) => {
  const files = Array.from(e.target.files || []);
  if (!files.length) return;

  for (const f of files) {
    if (items.length >= 20) break;
    const id = uid();
    const previewUrl = URL.createObjectURL(f);
    items.push({ id, file: f, previewUrl, blobForUpload: null });
  }
  fileInput.value = "";
  render();
});

clearBtn.addEventListener("click", () => {
  items.forEach(it => URL.revokeObjectURL(it.previewUrl));
  items = [];
  render();
});

async function uploadAll() {
  if (items.length < 1) throw new Error("No images selected");

  setStatus("Compressing images...");
  for (const it of items) {
    it.blobForUpload = await compressImage(it.file);
  }

  const sessionId = `session-${Date.now()}`;
  const form = new FormData();
  form.append("sessionId", sessionId);

  // preserve order
  items.forEach((it, i) => {
    const name = `photo-${String(i + 1).padStart(2, "0")}.jpg`;
    form.append("files", it.blobForUpload, name);
  });

  setStatus("Uploading to server...");
  const up = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    headers: { "x-app-token": APP_TOKEN },
    body: form
  });

  const upJson = await up.json();
  if (!up.ok) throw new Error(`Upload failed: ${JSON.stringify(upJson)}`);

  const urls = upJson.urls;
  if (!Array.isArray(urls) || urls.length < 1) throw new Error("No URLs returned");

  setStatus("Calling n8n to create listing...");
  const cr = await fetch(`${API_BASE}/create-listing`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-app-token": APP_TOKEN
    },
    body: JSON.stringify({ sessionId, imageUrls: urls })
  });

  const crJson = await cr.json();
  if (!cr.ok) throw new Error(`Create listing failed: ${JSON.stringify(crJson)}`);

  setStatus("Done!\n\n" + JSON.stringify(crJson, null, 2));
}

uploadBtn.addEventListener("click", async () => {
  try {
    uploadBtn.disabled = true;
    await uploadAll();
  } catch (e) {
    setStatus("Error:\n" + (e?.message || String(e)));
  } finally {
    uploadBtn.disabled = false;
  }
});

render();

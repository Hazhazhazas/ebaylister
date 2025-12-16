import express from "express";
import Busboy from "busboy";
import { Storage } from "@google-cloud/storage";
import fetch from "node-fetch";

const app = express();
const PORT = process.env.PORT || 8080;

const GCS_BUCKET = process.env.GCS_BUCKET;           // e.g. "my-ebay-photos"
const N8N_WEBHOOK_URL = process.env.N8N_WEBHOOK_URL; // your n8n webhook
const APP_TOKEN = process.env.APP_TOKEN;             // shared secret (single user)

if (!GCS_BUCKET || !N8N_WEBHOOK_URL || !APP_TOKEN) {
  console.warn("Missing env vars: GCS_BUCKET, N8N_WEBHOOK_URL, APP_TOKEN");
}

const storage = new Storage();

function requireAuth(req, res, next) {
  const token = req.get("x-app-token");
  if (!token || token !== APP_TOKEN) return res.status(401).json({ error: "Unauthorized" });
  next();
}

app.get("/health", (_req, res) => res.json({ ok: true }));

/**
 * POST /upload
 * multipart/form-data:
 *  - sessionId: string
 *  - files: up to 20 images
 * Returns: { sessionId, urls: [publicUrl...] }
 */
app.post("/upload", requireAuth, (req, res) => {
  const bb = Busboy({
    headers: req.headers,
    limits: { files: 20, fileSize: 12 * 1024 * 1024 } // 12MB each
  });

  let sessionId = null;
  const urls = [];
  const uploads = [];

  const bucket = storage.bucket(GCS_BUCKET);

  bb.on("field", (name, val) => {
    if (name === "sessionId") sessionId = val;
  });

  bb.on("file", (_name, file, info) => {
    const { filename, mimeType } = info;

    if (!["image/jpeg", "image/png", "image/webp"].includes(mimeType)) {
      file.resume();
      return;
    }

    const safeSession = (sessionId || `session-${Date.now()}`).replace(/[^a-zA-Z0-9_-]/g, "");
    const objectName = `${safeSession}/${Date.now()}-${Math.random().toString(16).slice(2)}-${filename}`
      .replace(/[^\w\-./]/g, "");

    const gcsFile = bucket.file(objectName);

    const p = new Promise((resolve, reject) => {
      const stream = gcsFile.createWriteStream({
        resumable: false,
        metadata: { contentType: mimeType }
      });

      file.pipe(stream);

      stream.on("finish", async () => {
        try {
          // Works if bucket allows public reads (or if uniform access + IAM allUsers objectViewer).
          await gcsFile.makePublic().catch(() => {});
          urls.push(`https://storage.googleapis.com/${GCS_BUCKET}/${objectName}`);
          resolve();
        } catch (e) {
          reject(e);
        }
      });

      stream.on("error", reject);
      file.on("limit", () => reject(new Error("File too large (12MB limit)")));
    });

    uploads.push(p);
  });

  bb.on("close", async () => {
    try {
      await Promise.all(uploads);
      res.json({ sessionId: sessionId || `session-${Date.now()}`, urls });
    } catch (err) {
      res.status(500).json({ error: "Upload failed", details: String(err?.message || err) });
    }
  });

  req.pipe(bb);
});

app.use(express.json({ limit: "1mb" }));

/**
 * POST /create-listing
 * JSON: { sessionId, imageUrls: [...] }
 * Forwards to n8n; returns n8n response.
 */
app.post("/create-listing", requireAuth, async (req, res) => {
  const { sessionId, imageUrls } = req.body || {};
  if (!sessionId || !Array.isArray(imageUrls) || imageUrls.length < 1) {
    return res.status(400).json({ error: "Missing sessionId or imageUrls" });
  }
  if (imageUrls.length > 20) return res.status(400).json({ error: "Max 20 images" });

  try {
    const r = await fetch(N8N_WEBHOOK_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sessionId, imageUrls, marketplace: "EBAY_GB" })
    });

    const text = await r.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }

    if (!r.ok) {
      return res.status(502).json({ error: "n8n webhook failed", status: r.status, data });
    }

    res.json({ ok: true, data });
  } catch (err) {
    res.status(500).json({ error: "Failed to call n8n", details: String(err?.message || err) });
  }
});

app.listen(PORT, () => console.log(`API listening on :${PORT}`));

(() => {
  const healthStatus = document.getElementById("health-status");
  const healthLabel = document.getElementById("health-label");
  const versionLabel = document.getElementById("version-label");
  const dropzoneHint = document.getElementById("dropzone-hint");
  const form = document.getElementById("upload-form");
  const fileInput = document.getElementById("file-input");
  const fileName = document.getElementById("file-name");
  const dropzone = document.getElementById("dropzone");
  const uploadBtn = document.getElementById("upload-btn");
  const uploadNote = document.getElementById("upload-note");
  const customerInput = document.getElementById("customer-id");
  const workspace = document.getElementById("workspace");
  const workspaceCustomer = document.getElementById("workspace-customer");
  const txnBody = document.getElementById("txn-body");
  const txnMeta = document.getElementById("txn-meta");
  const profileGrid = document.getElementById("profile-grid");
  const featuresGrid = document.getElementById("features-grid");

  let activeCustomer = customerInput.value.trim() || "demo";
  let maxUploadMb = 50;

  function setNote(message, kind) {
    uploadNote.textContent = message;
    uploadNote.classList.remove("is-error", "is-ok");
    if (kind) uploadNote.classList.add(kind);
  }

  function money(value) {
    if (value === null || value === undefined || value === "") return "—";
    const n = Number(value);
    if (Number.isNaN(n)) return String(value);
    return n.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function fmtDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  function formatMetric(value) {
    if (value === null || value === undefined) return "—";
    if (typeof value === "number") {
      return Number.isInteger(value) ? String(value) : value.toFixed(3);
    }
    if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function renderMetrics(target, data, keys) {
    target.innerHTML = "";
    const entries = keys
      ? keys.map((k) => [k, data[k]])
      : Object.entries(data || {});
    for (const [key, value] of entries) {
      if (key === "customer_id") continue;
      if (key === "expected_cashflow") continue;
      const wrap = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = key.replaceAll("_", " ");
      dd.textContent = formatMetric(value);
      wrap.append(dt, dd);
      target.append(wrap);
    }
  }

  function formatMb(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return null;
    return Number.isInteger(n) ? String(n) : n.toFixed(1);
  }

  async function checkHealth() {
    try {
      const resp = await fetch("/health");
      const body = await resp.json();
      if (!resp.ok) throw new Error("unhealthy");
      healthStatus.classList.add("is-ok");
      healthStatus.classList.remove("is-bad");
      healthLabel.textContent = "online";
      versionLabel.textContent = `v${body.version}`;
      const mbLabel = formatMb(body.max_upload_mb);
      if (mbLabel) {
        maxUploadMb = Number(body.max_upload_mb);
        if (dropzoneHint) {
          dropzoneHint.textContent = `CSV, XLSX, or PDF · max ${mbLabel} MB`;
        }
      }
    } catch {
      healthStatus.classList.add("is-bad");
      healthStatus.classList.remove("is-ok");
      healthLabel.textContent = "offline";
    }
  }

  function renderTransactions(payload) {
    const rows = payload.transactions || [];
    txnBody.innerHTML = "";
    txnMeta.textContent =
      rows.length === 0
        ? "No transactions for this customer."
        : `${payload.count} transaction${payload.count === 1 ? "" : "s"} for ${activeCustomer}`;

    for (const row of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${fmtDate(row.date)}</td>
        <td>${row.merchant || "—"}</td>
        <td>${row.description || "—"}</td>
        <td class="num">${money(row.debit)}</td>
        <td class="num">${money(row.credit)}</td>
        <td class="category">${row.category || "—"}</td>
      `;
      txnBody.append(tr);
    }
  }

  async function loadWorkspace(customerId) {
    activeCustomer = customerId;
    workspace.hidden = false;
    if (workspaceCustomer) {
      workspaceCustomer.textContent = `Customer ${customerId}`;
    }

    const txnResp = await fetch(
      `/transactions?customer_id=${encodeURIComponent(customerId)}&limit=200`
    );
    if (txnResp.ok) {
      renderTransactions(await txnResp.json());
    }

    const profileResp = await fetch(`/profile/${encodeURIComponent(customerId)}`);
    if (profileResp.ok) {
      const profile = await profileResp.json();
      renderMetrics(profileGrid, profile, [
        "income",
        "income_stability",
        "monthly_spend",
        "monthly_saving",
        "savings_ratio",
        "investment_ratio",
        "emi_ratio",
        "debt_ratio",
        "preferred_merchants",
        "preferred_payment_modes",
      ]);
    } else {
      profileGrid.innerHTML = "<div><dt>status</dt><dd>No profile yet</dd></div>";
    }

    const featResp = await fetch(`/features/${encodeURIComponent(customerId)}`);
    if (featResp.ok) {
      const feat = await featResp.json();
      renderMetrics(featuresGrid, feat.features || {});
    } else {
      featuresGrid.innerHTML = "<div><dt>status</dt><dd>No features yet</dd></div>";
    }
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    fileName.textContent = file ? file.name : "";
  });

  ["dragenter", "dragover"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add("is-drag");
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove("is-drag");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer && e.dataTransfer.files;
    if (files && files.length) {
      fileInput.files = files;
      fileName.textContent = files[0].name;
    }
  });

  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      const panel = tab.dataset.panel;
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.toggle("is-active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      document.querySelectorAll(".panel").forEach((p) => {
        const active = p.id === `panel-${panel}`;
        p.classList.toggle("is-active", active);
        p.hidden = !active;
      });
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const customerId = customerInput.value.trim();
    const file = fileInput.files && fileInput.files[0];
    if (!customerId || !file) {
      setNote("Choose a customer ID and a statement file.", "is-error");
      return;
    }

    const limitBytes = maxUploadMb * 1024 * 1024;
    if (file.size > limitBytes) {
      const mbLabel = formatMb(maxUploadMb) || String(maxUploadMb);
      setNote(`Upload exceeds limit of ${mbLabel} MB`, "is-error");
      return;
    }

    const body = new FormData();
    body.append("customer_id", customerId);
    body.append("file", file);

    uploadBtn.disabled = true;
    setNote("Ingesting…");

    try {
      const resp = await fetch("/statements", { method: "POST", body });
      const payload = await resp.json();
      if (!resp.ok && resp.status !== 202) {
        const detail =
          typeof payload.detail === "string"
            ? payload.detail
            : payload.detail
              ? JSON.stringify(payload.detail)
              : "Upload failed";
        throw new Error(detail);
      }

      if (resp.status === 202) {
        setNote(payload.note || "Accepted for offline OCR.", "is-ok");
      } else {
        setNote(
          `Processed ${payload.transactions_ingested} transaction(s).`,
          "is-ok"
        );
        await loadWorkspace(customerId);
        workspace.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      setNote(err.message || "Upload failed", "is-error");
    } finally {
      uploadBtn.disabled = false;
    }
  });

  checkHealth();
})();

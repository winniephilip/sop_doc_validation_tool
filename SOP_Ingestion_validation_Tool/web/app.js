/* SOP Ingestion Validation Tool — frontend  (v4) */

const API = "";  // same origin; set to "http://localhost:8000" when opening file:// directly

// ── Utility: safe getElementById ──────────────────────────────────────────────
function el(id) {
  const node = document.getElementById(id);
  if (!node) console.warn("Missing DOM element:", id);
  return node;
}

// ── Tesseract status check ────────────────────────────────────────────────────
let ocrChecked = false;
async function checkOcrStatus() {
  if (ocrChecked) return;
  ocrChecked = true;
  const indicator = el("ocr-status-indicator");
  if (!indicator) return;
  try {
    const res  = await fetch(`${API}/ocr-status`);
    const data = await res.json();
    if (data.available) {
      indicator.textContent = `✔ Tesseract ${data.version} ready`;
      indicator.className = "ocr-ok";
    } else {
      indicator.textContent = `✘ Tesseract not found — ${data.error}`;
      indicator.className = "ocr-fail";
    }
  } catch (err) {
    indicator.textContent = "✘ Could not reach server — is start.bat running?";
    indicator.className = "ocr-fail";
  }
}

// ── Mode switching ────────────────────────────────────────────────────────────
document.querySelectorAll(".mode-btn").forEach(function(btn) {
  btn.addEventListener("click", function() {
    var mode = btn.dataset.mode;
    document.querySelectorAll(".mode-btn").forEach(function(b) { b.classList.remove("active"); });
    document.querySelectorAll(".mode-panel").forEach(function(p) { p.classList.remove("active"); });
    btn.classList.add("active");
    var panel = document.getElementById("panel-" + mode);
    if (panel) panel.classList.add("active");
    if (mode === "doc-vs-screenshot") checkOcrStatus();
    hideResults();
  });
});

function hideResults() {
  var s = el("summary-banner"); if (s) s.classList.add("hidden");
  var t = el("tab-bar");        if (t) t.classList.add("hidden");
  document.querySelectorAll(".tab-content").forEach(function(n) { n.classList.add("hidden"); });
}

// ── File name display ─────────────────────────────────────────────────────────
(function() {
  var inputs = [
    ["orig-file",      "orig-name",    null,              null],
    ["new-file",       "new-name",     null,              null],
    ["web-doc-file",   "web-doc-name", null,              null],
    ["ss-doc-file",    "ss-doc-name",  null,              null],
    ["ss-img-file",    "ss-img-name",  "ss-preview-wrap", "ss-preview"],
    ["html-doc-file",  "html-doc-name",null,              null],
    ["html-html-file", "html-html-name",null,             null],
    ["batch-csv-file", "batch-csv-name",null,             null],
  ];
  inputs.forEach(function(row) {
    var inp = document.getElementById(row[0]);
    if (!inp) return;
    inp.addEventListener("change", function() {
      var f = inp.files[0];
      var nameEl = document.getElementById(row[1]);
      if (nameEl) nameEl.textContent = f ? f.name : (row[0] === "ss-img-file" ? "PNG, JPG, WEBP, BMP, TIFF" : "No file selected");
      if (row[2] && row[3]) {
        var wrap = document.getElementById(row[2]);
        var img  = document.getElementById(row[3]);
        if (wrap && img) {
          if (f) { img.src = URL.createObjectURL(f); wrap.classList.remove("hidden"); }
          else   { wrap.classList.add("hidden"); }
        }
      }
    });
  });
}());

// ── Button handlers (called via onclick= in HTML) ─────────────────────────────

window.handleDocCompare = async function() {
  var origFile = document.getElementById("orig-file");
  var newFile  = document.getElementById("new-file");
  var btn      = document.getElementById("compare-btn");
  var bar      = document.getElementById("status-bar");

  if (!origFile || !origFile.files[0]) { setStatus(bar, "Please select the original document.", true); return; }
  if (!newFile  || !newFile.files[0])  { setStatus(bar, "Please select the new version document.", true); return; }

  setStatus(bar, "Uploading and parsing documents…");
  if (btn) btn.disabled = true;

  var fd = new FormData();
  fd.append("original",    origFile.files[0]);
  fd.append("new_version", newFile.files[0]);

  try {
    var data = await postForm(API + "/compare", fd);
    setStatus(bar, "");
    renderReport(data, "doc-vs-doc");
  } catch(e) {
    setStatus(bar, "Error: " + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.handleWebCompare = async function() {
  var docFile = document.getElementById("web-doc-file");
  var urlInp  = document.getElementById("web-url");
  var btn     = document.getElementById("web-compare-btn");
  var bar     = document.getElementById("web-status-bar");

  if (!docFile || !docFile.files[0])               { setStatus(bar, "Please select a document.", true); return; }
  if (!urlInp  || !urlInp.value.trim().startsWith("http")) { setStatus(bar, "Please enter a valid URL starting with http.", true); return; }

  var url = urlInp.value.trim();
  setStatus(bar, "Fetching webpage and comparing…");
  if (btn) btn.disabled = true;

  var fd = new FormData();
  fd.append("document", docFile.files[0]);
  fd.append("url",      url);

  try {
    var data = await postForm(API + "/compare-web", fd);
    setStatus(bar, "");
    renderReport(data, "doc-vs-web");
  } catch(e) {
    setStatus(bar, "Error: " + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.handleSsCompare = async function() {
  console.log("[SS] handleSsCompare called");

  var docFile = document.getElementById("ss-doc-file");
  var imgFile = document.getElementById("ss-img-file");
  var btn     = document.getElementById("ss-compare-btn");
  var bar     = document.getElementById("ss-status-bar");

  console.log("[SS] docFile:", docFile, "files:", docFile && docFile.files.length);
  console.log("[SS] imgFile:", imgFile, "files:", imgFile && imgFile.files.length);

  if (!docFile || !docFile.files[0]) { setStatus(bar, "Please select the original document first.", true); return; }
  if (!imgFile || !imgFile.files[0]) { setStatus(bar, "Please select a screenshot image first.",    true); return; }

  setStatus(bar, "Running OCR on screenshot and comparing…");
  if (btn) btn.disabled = true;

  var fd = new FormData();
  fd.append("document",   docFile.files[0]);
  fd.append("screenshot", imgFile.files[0]);

  console.log("[SS] posting to /compare-screenshot");

  try {
    var data = await postForm(API + "/compare-screenshot", fd);
    console.log("[SS] response received, score:", data.score);
    setStatus(bar, "");
    renderReport(data, "doc-vs-screenshot");
  } catch(e) {
    console.error("[SS] error:", e);
    setStatus(bar, "Error: " + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.handleHtmlCompare = async function() {
  console.log("[HTML] handleHtmlCompare called");

  var docFile  = document.getElementById("html-doc-file");
  var htmlFile = document.getElementById("html-html-file");
  var pathInp  = document.getElementById("html-local-path");
  var btn      = document.getElementById("html-compare-btn");
  var bar      = document.getElementById("html-status-bar");

  if (!docFile || !docFile.files[0]) {
    setStatus(bar, "Please select the original document.", true); return;
  }
  var hasUpload = htmlFile && htmlFile.files[0];
  var hasPath   = pathInp  && pathInp.value.trim().length > 0;
  if (!hasUpload && !hasPath) {
    setStatus(bar, "Please upload an HTML file or enter the local file path.", true); return;
  }

  setStatus(bar, "Parsing HTML and comparing…");
  if (btn) btn.disabled = true;

  var fd = new FormData();
  fd.append("document", docFile.files[0]);
  if (hasUpload) fd.append("html_file", htmlFile.files[0]);
  if (hasPath)   fd.append("html_path", pathInp.value.trim());

  console.log("[HTML] posting to /compare-html, hasUpload:", !!hasUpload, "hasPath:", !!hasPath);

  try {
    var data = await postForm(API + "/compare-html", fd);
    console.log("[HTML] response received, score:", data.score);
    setStatus(bar, "");
    renderReport(data, "doc-vs-html");
  } catch(e) {
    console.error("[HTML] error:", e);
    setStatus(bar, "Error: " + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
};

window.handleBatchCompare = async function() {
  var csvFile = document.getElementById("batch-csv-file");
  var btn     = document.getElementById("batch-compare-btn");
  var bar     = document.getElementById("batch-status-bar");
  var results = document.getElementById("batch-results-container");

  if (!csvFile || !csvFile.files[0]) { setStatus(bar, "Please select a CSV file.", true); return; }

  setStatus(bar, "Running batch comparison…");
  if (btn) btn.disabled = true;
  if (results) results.innerHTML = "";

  var fd = new FormData();
  fd.append("csv_file", csvFile.files[0]);

  try {
    var data = await postForm(API + "/batch-compare-html", fd);
    setStatus(bar, "Batch complete — " + data.length + " row(s) processed.");
    if (results) results.innerHTML = renderBatchResults(data);
  } catch(e) {
    setStatus(bar, "Error: " + e.message, true);
  } finally {
    if (btn) btn.disabled = false;
  }
};

function renderBatchResults(rows) {
  if (!rows || !rows.length) return "<p style='color:#718096;margin-top:12px'>No rows processed.</p>";

  var statusColours = {
    MATCH:    "chip-MATCH",
    MISMATCH: "chip-MISMATCH",
    MISSING:  "chip-MISSING",
    ADDED:    "chip-ADDED",
    ERROR:    "chip-MISMATCH",
  };

  var rowsHtml = rows.map(function(r) {
    var badge = '<span class="count-chip ' + (statusColours[r.status] || "chip-MISMATCH") + '">' + esc(r.status) + '</span>';
    var pct   = r.score != null ? Math.round(r.score * 100) + "%" : "—";
    var jsonOut  = r.json_output  ? '<span class="batch-path">' + esc(r.json_output)  + '</span>' : '—';
    var htmlOut  = r.html_output  ? '<span class="batch-path">' + esc(r.html_output)  + '</span>' : '—';
    var errCell  = r.error        ? '<span style="color:#742a2a;font-size:.8rem">' + esc(r.error) + '</span>' : '';
    return "<tr>" +
      "<td>" + esc(r.file || ("Row " + r.row)) + "</td>" +
      "<td>" + badge + "</td>" +
      "<td style='text-align:center'>" + pct + "</td>" +
      "<td>" + jsonOut + "</td>" +
      "<td>" + htmlOut + "</td>" +
      "<td>" + errCell + "</td>" +
      "</tr>";
  }).join("");

  return '<table class="diff-table batch-table" style="margin-top:16px">' +
    '<thead><tr>' +
    '<th>File</th><th>Status</th><th>Score</th>' +
    '<th>JSON Output</th><th>HTML Output</th><th>Error</th>' +
    '</tr></thead>' +
    '<tbody>' + rowsHtml + '</tbody>' +
    '</table>';
}

// ── Shared fetch helper ───────────────────────────────────────────────────────
async function postForm(endpoint, formData) {
  var res = await fetch(endpoint, { method: "POST", body: formData });
  if (!res.ok) {
    var err = await res.json().catch(function() { return { detail: res.statusText }; });
    throw new Error(err.detail || JSON.stringify(err));
  }
  return res.json();
}

function setStatus(statusEl, msg, isError) {
  if (!statusEl) { if (msg) showToast(msg); return; }
  statusEl.textContent = msg;
  statusEl.className = "status-bar" + (isError ? " error" : "");
  if (isError && msg) showToast(msg);
}

function showToast(msg) {
  var toast  = document.getElementById("error-toast");
  var toastMsg = document.getElementById("error-toast-msg");
  if (!toast || !toastMsg) { alert(msg); return; }
  toastMsg.textContent = msg;
  toast.classList.remove("hidden");
  setTimeout(function() { toast.classList.add("hidden"); }, 8000);
}

// ── Tab switching ─────────────────────────────────────────────────────────────
var tabBar = document.getElementById("tab-bar");
if (tabBar) {
  tabBar.addEventListener("click", function(e) {
    var btn = e.target.closest(".tab");
    if (!btn) return;
    document.querySelectorAll(".tab").forEach(function(t) { t.classList.remove("active"); });
    document.querySelectorAll(".tab-content").forEach(function(t) { t.classList.add("hidden"); });
    btn.classList.add("active");
    var target = document.getElementById("tab-" + btn.dataset.tab);
    if (target) target.classList.remove("hidden");
  });
}

// ── Render ────────────────────────────────────────────────────────────────────
function renderReport(data, mode) {
  renderSummary(data, mode);
  renderFieldTable(data.field_results, data.warnings_result);
  renderSections(data.section_results, mode);
  renderRaw(data.original_parsed, data.new_parsed);

  var lbl = document.getElementById("raw-left-label");
  var rbl = document.getElementById("raw-right-label");
  if (lbl) lbl.textContent = mode === "doc-vs-doc" ? "Original Parsed" : "Document Parsed";
  if (rbl) rbl.textContent = mode === "doc-vs-web"        ? "Webpage Parsed"
                           : mode === "doc-vs-screenshot" ? "Screenshot OCR Parsed"
                           : mode === "doc-vs-html"       ? "HTML File Parsed"
                           : "New Version Parsed";

  var sb = document.getElementById("summary-banner"); if (sb) sb.classList.remove("hidden");
  var tb = document.getElementById("tab-bar");        if (tb) tb.classList.remove("hidden");

  document.querySelectorAll(".tab").forEach(function(t) { t.classList.toggle("active", t.dataset.tab === "fields"); });
  document.querySelectorAll(".tab-content").forEach(function(t) { t.classList.add("hidden"); });
  var tf = document.getElementById("tab-fields"); if (tf) tf.classList.remove("hidden");
}

function renderSummary(data, mode) {
  var pct = Math.round((data.score || 0) * 100);
  var sv = document.getElementById("score-value");
  if (sv) { sv.textContent = pct + "%"; sv.style.color = pct >= 90 ? "#22543d" : pct >= 70 ? "#744210" : "#742a2a"; }

  var sc = document.getElementById("summary-counts");
  if (sc) sc.innerHTML = Object.entries(data.summary || {}).map(function(entry) {
    return '<span class="count-chip chip-' + entry[0] + '">' + entry[1] + ' ' + entry[0] + '</span>';
  }).join("");

  var status = data.overall_status || "MISMATCH";
  var ob = document.getElementById("overall-badge");
  if (ob) { ob.textContent = status; ob.className = "overall-badge badge-" + status; }

  var ml = document.getElementById("compare-mode-label");
  if (ml) ml.innerHTML = mode === "doc-vs-web"
    ? '<span class="mode-tag web">&#127760; Doc vs Webpage</span>'
    : mode === "doc-vs-screenshot"
    ? '<span class="mode-tag img">&#128247; Doc vs Screenshot</span>'
    : mode === "doc-vs-html"
    ? '<span class="mode-tag html">&#128196; Doc vs HTML File</span>'
    : '<span class="mode-tag doc">&#128196; Doc vs Doc</span>';
}

function renderFieldTable(fields, warningsResult) {
  var rows = [].concat(fields || []);
  if (warningsResult) rows.push(warningsResult);
  var tbody = document.getElementById("field-tbody");
  if (!tbody) return;
  tbody.innerHTML = rows.map(function(r) {
    var sim = r.similarity != null ? simBar(r.similarity) : "—";
    return "<tr><td><strong>" + esc(r.field) + "</strong></td>" +
      "<td><span class=\"status-badge status-" + r.status + "\">" + r.status + "</span></td>" +
      "<td>" + esc(formatVal(r.original_value)) + "</td>" +
      "<td>" + esc(formatVal(r.new_value)) + "</td>" +
      "<td>" + sim + "</td></tr>";
  }).join("");
}

// ── Word-level inline diff ────────────────────────────────────────────────────
function tokenize(text) {
  // Split into word+punctuation tokens and whitespace tokens
  return text.split(/(\s+)/).filter(function(t) { return t.length > 0; });
}

function wordLCS(a, b) {
  // O(mn) LCS — capped at 300 tokens per side for performance
  var m = a.length, n = b.length;
  var dp = [];
  for (var i = 0; i <= m; i++) { dp[i] = new Array(n + 1).fill(0); }
  for (var i = 1; i <= m; i++)
    for (var j = 1; j <= n; j++)
      dp[i][j] = a[i-1] === b[j-1] ? dp[i-1][j-1] + 1 : Math.max(dp[i-1][j], dp[i][j-1]);
  var ops = [], i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i-1] === b[j-1]) { ops.push({ t: '=', v: a[i-1] }); i--; j--; }
    else if (j > 0 && (i === 0 || dp[i][j-1] >= dp[i-1][j])) { ops.push({ t: '+', v: b[j-1] }); j--; }
    else { ops.push({ t: '-', v: a[i-1] }); i--; }
  }
  return ops.reverse();
}

function inlineDiff(origText, newText) {
  var tokA = tokenize(origText || "");
  var tokB = tokenize(newText  || "");
  // Fall back to plain text for very large sections
  if (tokA.length > 1000 || tokB.length > 1000) {
    return { origHtml: esc(origText), newHtml: esc(newText) };
  }
  var ops = wordLCS(tokA, tokB);
  var origHtml = "", newHtml = "";
  ops.forEach(function(op) {
    if (op.t === '=') { origHtml += esc(op.v); newHtml += esc(op.v); }
    else if (op.t === '-') { origHtml += '<span class="hl-del">' + esc(op.v) + '</span>'; }
    else                   { newHtml  += '<span class="hl-add">' + esc(op.v) + '</span>'; }
  });
  return { origHtml: origHtml, newHtml: newHtml };
}

function renderSections(sections, mode) {
  var div = document.getElementById("sections-container");
  if (!div) return;
  if (!sections || !sections.length) { div.innerHTML = "<p style='color:#718096'>No sections found.</p>"; return; }
  var leftLbl  = mode === "doc-vs-doc" ? "Original" : "Document";
  var rightLbl = mode === "doc-vs-web"        ? "Webpage"
               : mode === "doc-vs-screenshot" ? "Screenshot"
               : mode === "doc-vs-html"       ? "HTML File"
               : "New Version";
  div.innerHTML = sections.map(function(s) {
    var sim = s.similarity != null ? simBar(s.similarity) : "";
    var origHtml, newHtml;
    if ((s.status === "MISMATCH" || (s.status === "MATCH" && s.similarity != null && s.similarity < 1.0)) && s.original_content && s.new_content) {
      var d = inlineDiff(s.original_content, s.new_content);
      origHtml = d.origHtml;
      newHtml  = d.newHtml;
    } else {
      origHtml = esc(s.original_content || "(not present)");
      newHtml  = esc(s.new_content      || "(not present)");
    }
    return '<div class="section-card">' +
      '<div class="section-header" onclick="toggleSection(this)">' +
        '<span class="status-badge status-' + s.status + '">' + s.status + '</span>' +
        '<span class="section-title">' + esc(s.title) + '</span>' + sim +
        '<span>&#9660;</span></div>' +
      '<div class="section-body"><div class="section-split">' +
        '<div class="section-col"><h4>' + leftLbl  + '</h4><p>' + origHtml + '</p></div>' +
        '<div class="section-col"><h4>' + rightLbl + '</h4><p>' + newHtml  + '</p></div>' +
      '</div></div>';
  }).join("");
}

window.toggleSection = function(header) {
  var body = header.nextElementSibling;
  body.classList.toggle("open");
  var arrow = header.querySelector("span:last-child");
  if (arrow) arrow.textContent = body.classList.contains("open") ? "▲" : "▼";
};

function renderDiff(lines) {
  return lines.map(function(line) {
    var cls = line.startsWith("+") ? "add" : line.startsWith("-") ? "del" : "ctx";
    return '<div class="' + cls + '">' + esc(line) + '</div>';
  }).join("");
}

function renderRaw(orig, newDoc) {
  var ro = document.getElementById("raw-orig"); if (ro) ro.textContent = JSON.stringify(orig,   null, 2);
  var rn = document.getElementById("raw-new");  if (rn) rn.textContent = JSON.stringify(newDoc, null, 2);
}

// ── Utilities ─────────────────────────────────────────────────────────────────
function esc(s) {
  if (s == null) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function formatVal(v) {
  if (v == null) return "";
  if (Array.isArray(v)) return v.join(", ");
  return String(v).slice(0, 200);
}
function simBar(ratio) {
  var pct  = Math.round(ratio * 100);
  var fill = ratio >= 0.8 ? "fill-high" : ratio >= 0.5 ? "fill-medium" : "fill-low";
  return '<div class="sim-bar-wrap"><div class="sim-bar"><div class="sim-fill ' + fill + '" style="width:' + pct + '%"></div></div>' +
    '<span style="font-size:.75rem;color:#718096">' + pct + '%</span></div>';
}

console.log("[SOP Tool] app.js v4 loaded");

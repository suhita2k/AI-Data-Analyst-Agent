
let DATASET_ID = null;

// DOM elements
const fileInput = document.getElementById("fileInput");
const dropzone = document.getElementById("dropzone");
const metaPanel = document.getElementById("metaPanel");
const metaSummary = document.getElementById("metaSummary");
const columnsGrid = document.getElementById("columnsGrid");
const qaPanel = document.getElementById("qaPanel");
const questionInput = document.getElementById("question");
const askBtn = document.getElementById("askBtn");
const answerDiv = document.getElementById("answer");
const chartDiv = document.getElementById("chart");
const previewDiv = document.getElementById("preview");
const downloadReportBtn = document.getElementById("downloadReport");
const downloadPngBtn = document.getElementById("downloadPng");
const startBtn = document.getElementById("startBtn");

// Start button opens file dialog
if (startBtn && fileInput) {
    startBtn.addEventListener("click", () => fileInput.click());
}

if (dropzone && fileInput) {
    // Click to open file dialog
    dropzone.addEventListener("click", () => fileInput.click());

    // Drag & drop
    dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "#60a5fa";
    });

    dropzone.addEventListener("dragleave", () => {
        dropzone.style.borderColor = "";
    });

    dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.style.borderColor = "";
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            handleUpload();
        }
    });

    fileInput.addEventListener("change", handleUpload);
}

// -------------------------
// File upload
// -------------------------

async function handleUpload() {
    const file = fileInput.files[0];
    if (!file) return;

    const form = new FormData();
    form.append("file", file);

    dropzone.querySelector("p").innerText = "Uploading...";

    try {
        const resp = await fetch("/api/upload", {
            method: "POST",
            body: form,
        });

        const data = await resp.json();
        if (!resp.ok) {
            throw new Error(data.error || "Upload failed");
        }

        DATASET_ID = data.dataset_id;
        renderMeta(data.meta);

        dropzone.querySelector("p").innerText =
            "Upload complete! Ask a question below.";
        qaPanel.hidden = false;
    } catch (e) {
        console.error(e);
        dropzone.querySelector("p").innerText = `Error: ${e.message}`;
    }
}

// -------------------------
// Render dataset summary
// -------------------------

function renderMeta(meta) {
    if (!metaPanel) return;

    metaPanel.hidden = false;

    const quickTrend =
        meta.summary && meta.summary.quick_trend
            ? meta.summary.quick_trend
            : "—";

    metaSummary.innerHTML = `
        <b>Rows:</b> ${meta.rows} • <b>Columns:</b> ${meta.cols}<br/>
        <b>Quick trend:</b> ${quickTrend}
    `;

    columnsGrid.innerHTML = "";
    (meta.columns || []).forEach((c) => {
        const type = meta.logical_types ? meta.logical_types[c] : "";
        const div = document.createElement("div");
        div.className = "card";
        div.innerHTML = `<b>${c}</b><br/><small>${type}</small>`;
        columnsGrid.appendChild(div);
    });
}

// -------------------------
// Ask a question
// -------------------------

if (askBtn && questionInput) {
    askBtn.addEventListener("click", askQuestion);
    questionInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            askQuestion();
        }
    });
}

async function askQuestion() {
    const q = questionInput.value.trim();
    if (!q) return;

    if (!DATASET_ID) {
        alert("Upload a dataset first.");
        return;
    }

    answerDiv.innerText = "Thinking...";
    previewDiv.innerText = "";

    try {
        const resp = await fetch("/api/ask", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                dataset_id: DATASET_ID,
                question: q,
            }),
        });

        const data = await resp.json();
        if (!resp.ok) {
            throw new Error(data.error || "Ask failed");
        }

        answerDiv.innerText = data.answer || "(No insight returned)";

        if (data.figure && chartDiv) {
            Plotly.newPlot(chartDiv, data.figure.data, data.figure.layout, {
                responsive: true,
            });
        }

        if (Array.isArray(data.agg_preview) && data.agg_preview.length > 0) {
            previewDiv.innerText = `Preview rows: ${data.agg_preview.length}`;
        } else {
            previewDiv.innerText = "";
        }
    } catch (e) {
        console.error(e);
        answerDiv.innerText = "Error: " + e.message;
    }
}

// -------------------------
// Download report
// -------------------------

if (downloadReportBtn) {
    downloadReportBtn.addEventListener("click", () => {
        if (!DATASET_ID) {
            alert("Upload a dataset first.");
            return;
        }
        window.location.href = `/api/report/${DATASET_ID}`;
    });
}

// -------------------------
// Download chart as PNG
// -------------------------

if (downloadPngBtn && chartDiv) {
    downloadPngBtn.addEventListener("click", async () => {
        if (!chartDiv || !chartDiv.data) {
            alert("No chart available to download.");
            return;
        }
        try {
            const dataUrl = await Plotly.toImage(chartDiv, {
                format: "png",
                height: 600,
                width: 1000,
            });
            const a = document.createElement("a");
            a.href = dataUrl;
            a.download = "chart.png";
            document.body.appendChild(a);
            a.click();
            a.remove();
        } catch (e) {
            console.error(e);
            alert("Could not download chart as PNG.");
        }
    });
}
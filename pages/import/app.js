const bridge = window.AstrBotPluginPage;

const statsEl = document.getElementById("stats");
const pendingCountEl = document.getElementById("pending-count");
const importedCountEl = document.getElementById("imported-count");
const refreshBtn = document.getElementById("refreshBtn");
const uploadForm = document.getElementById("uploadForm");
const csvFileInput = document.getElementById("csvFileInput");
const uploadBtn = document.getElementById("uploadBtn");
const uploadMessageEl = document.getElementById("uploadMessage");
const previewContainerEl = document.getElementById("previewContainer");
const confirmContainerEl = document.getElementById("confirmContainer");
const confirmBtn = document.getElementById("confirmBtn");
const confirmMessageEl = document.getElementById("confirmMessage");

let pageContext = null;
let uploadedData = null;

function showMessage(element, text, type = "ok") {
  element.textContent = text;
  element.className = `message ${type}`;
}

function escapeText(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    switch (char) {
      case "&":
        return "&amp;";
      case "<":
        return "&lt;";
      case ">":
        return "&gt;";
      case '"':
        return "&quot;";
      case "'":
        return "&#39;";
      default:
        return char;
    }
  });
}

function renderPreview(data) {
  if (!data || !data.tasks || !Array.isArray(data.tasks)) {
    previewContainerEl.innerHTML = "<p>无预览数据</p>";
    return;
  }

  const tasks = data.tasks;
  const categories = [...new Set(tasks.map(task => task.category))];

  let html = `
    <div class="preview-summary">
      <p>共解析到 <strong>${tasks.length}</strong> 条任务，包含 <strong>${categories.length}</strong> 个分类</p>
      <div class="categories">
        ${categories.map(cat => `<span class="category-tag">${escapeText(cat)}</span>`).join("")}
      </div>
    </div>
    <div class="tasks-table">
      <table>
        <thead>
          <tr>
            <th>分类</th>
            <th>任务</th>
            <th>积分</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          ${tasks.map(task => `
            <tr>
              <td>${escapeText(task.category)}</td>
              <td>${escapeText(task.title)}</td>
              <td>${task.points}</td>
              <td>${task.enabled ? "启用" : "禁用"}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;

  previewContainerEl.innerHTML = html;
}

async function uploadCSV(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    showMessage(uploadMessageEl, "正在上传文件...", "info");
    uploadBtn.disabled = true;

    const response = await fetch("/astrbot_plugin_blindbox/csv/upload", {
      method: "POST",
      body: formData,
    });

    const result = await response.json();

    if (result.success) {
      uploadedData = result.data;
      renderPreview(uploadedData);
      confirmBtn.disabled = false;
      showMessage(uploadMessageEl, "文件上传成功，请检查预览后确认导入", "ok");
    } else {
      showMessage(uploadMessageEl, result.message || "上传失败", "error");
    }
  } catch (error) {
    console.error("Upload error:", error);
    showMessage(uploadMessageEl, "上传过程中发生错误", "error");
  } finally {
    uploadBtn.disabled = false;
  }
}

async function confirmImport() {
  if (!uploadedData) {
    showMessage(confirmMessageEl, "没有可导入的数据", "error");
    return;
  }

  try {
    showMessage(confirmMessageEl, "正在导入数据...", "info");
    confirmBtn.disabled = true;

    const response = await fetch("/astrbot_plugin_blindbox/csv/import", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ data: uploadedData }),
    });

    const result = await response.json();

    if (result.success) {
      showMessage(confirmMessageEl, result.message || "导入成功", "ok");
      uploadedData = null;
      previewContainerEl.innerHTML = "<p>请先上传 CSV 文件查看预览</p>";
      confirmBtn.disabled = true;
      csvFileInput.value = "";
      await refreshStats();
    } else {
      showMessage(confirmMessageEl, result.message || "导入失败", "error");
      confirmBtn.disabled = false;
    }
  } catch (error) {
    console.error("Import error:", error);
    showMessage(confirmMessageEl, "导入过程中发生错误", "error");
    confirmBtn.disabled = false;
  }
}

async function refreshStats() {
  try {
    const response = await fetch("/astrbot_plugin_blindbox/tasks/stats");
    const result = await response.json();

    if (result.success) {
      pendingCountEl.textContent = result.data.pending || 0;
      importedCountEl.textContent = result.data.imported || 0;
    }
  } catch (error) {
    console.error("Failed to refresh stats:", error);
  }
}

// Event listeners
refreshBtn.addEventListener("click", refreshStats);

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = csvFileInput.files[0];
  if (!file) {
    showMessage(uploadMessageEl, "请选择一个 CSV 文件", "error");
    return;
  }

  if (!file.name.toLowerCase().endsWith(".csv")) {
    showMessage(uploadMessageEl, "只支持 CSV 文件", "error");
    return;
  }

  await uploadCSV(file);
});

confirmBtn.addEventListener("click", confirmImport);

// Initialize
document.addEventListener("DOMContentLoaded", async () => {
  await refreshStats();
});
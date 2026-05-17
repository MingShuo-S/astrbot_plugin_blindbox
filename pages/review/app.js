const bridge = window.AstrBotPluginPage;

const statsEl = document.getElementById("stats");
const messageEl = document.getElementById("message");
const refreshBtn = document.getElementById("refreshBtn");
const exportAllBtn = document.getElementById("exportAllBtn");
const exportApprovedBtn = document.getElementById("exportApprovedBtn");
const filterSelect = document.getElementById("filterSelect");
const recordsContainer = document.getElementById("reviews-container");
const manualCreateForm = document.getElementById("manualCreateForm");
const submitterQQInput = manualCreateForm?.querySelector('input[name="submitter_qq"]');
const autoGroupNoInput = document.getElementById("autoGroupNo");
const taskSelector = document.getElementById("taskSelector");
const taskCategoryInput = document.getElementById("taskCategory");
const taskTitleInput = document.getElementById("taskTitle");
const taskPointsInput = document.getElementById("taskPoints");
const imageFilesInput = document.getElementById("imageFiles");
const imagePreviewContainer = document.getElementById("imagePreview");

let pageContext = null;
let reviewRecords = [];
let availableTasks = [];
let selectedImageFiles = [];

async function getBridge() {
  if (window.AstrBotPluginPage) {
    return window.AstrBotPluginPage;
  }

  for (let index = 0; index < 40; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 50));
    if (window.AstrBotPluginPage) {
      return window.AstrBotPluginPage;
    }
  }

  throw new Error("AstrBot 插件页 bridge 尚未就绪");
}

function showMessage(text, type = "ok") {
  messageEl.textContent = text;
  messageEl.className = `message ${type}`;
}

function normalizeApiResponse(payload) {
  if (payload && typeof payload === "object" && "success" in payload) {
    return payload;
  }
  return { success: true, message: "操作成功", data: payload };
}

function escapeHtml(text) {
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return String(text ?? "").replace(/[&<>"']/g, (char) => map[char]);
}

function formatDate(value) {
  return value ? String(value) : "未知时间";
}

function getStatusMeta(status) {
  const normalized = String(status || "pending").toLowerCase();
  if (normalized === "approved") {
    return { label: "已通过", className: "status status--approved" };
  }
  if (normalized === "rejected") {
    return { label: "已拒绝", className: "status status--rejected" };
  }
  return { label: "未审核", className: "status status--pending" };
}

function getTaskSnapshot(record) {
  return record && typeof record.task_snapshot === "object" ? record.task_snapshot : {};
}

function getAttachmentItems(record) {
  const attachments = Array.isArray(record.attachments) ? record.attachments : [];
  if (attachments.length > 0) {
    return attachments;
  }

  const remoteUrls = Array.isArray(record.image_urls) ? record.image_urls : [];
  const localNames = Array.isArray(record.local_images) ? record.local_images : [];

  return [
    ...remoteUrls.map((url) => ({ url, name: url, type: "remote" })),
    ...localNames.map((name) => ({ url: "", name, type: "local" })),
  ];
}

function renderAttachments(record) {
  const items = getAttachmentItems(record);
  if (!items.length) {
    return "";
  }

  return `
    <div class="attachments">
      <div class="section-title">提交图片</div>
      <div class="attachments-grid">
        ${items
          .map((item, index) => {
            if (item.url) {
              // 使用onclick打开图片，避免sandbox限制
              return `
                <div class="attachment-card attachment-card--link" onclick="window.open('${escapeHtml(item.url)}', '_blank')" style="cursor: pointer;">
                  <img src="${escapeHtml(item.url)}" alt="提交图片 ${index + 1}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
                  <div class="attachment-placeholder" style="display: none;">加载失败</div>
                  <span>${escapeHtml(item.name || "图片")}</span>
                </div>
              `;
            }

            // 本地图片显示提示
            return `
              <div class="attachment-card attachment-card--missing">
                <div class="attachment-placeholder">图片已保存到服务器<br/><small>请在管理页面查看</small></div>
                <span>${escapeHtml(item.name || "本地图片")}</span>
              </div>
            `;
          })
          .join("")}
      </div>
    </div>
  `;
}

function renderStats(data) {
  const counts = reviewRecords.reduce(
    (accumulator, record) => {
      const status = String(record.review_status || "pending").toLowerCase();
      accumulator.total += 1;
      accumulator[status] = (accumulator[status] || 0) + 1;
      accumulator.groups.add(String(record.group_no || ""));
      return accumulator;
    },
    { total: 0, pending: 0, approved: 0, rejected: 0, groups: new Set() },
  );

  const items = [
    { value: String(counts.total), label: "提交总数" },
    { value: String(counts.pending || 0), label: "未审核" },
    { value: String(counts.approved || 0), label: "已通过" },
    { value: String(counts.rejected || 0), label: "已拒绝" },
    { value: String(counts.groups.size), label: "涉及小组" },
  ];

  statsEl.innerHTML = items
    .map(
      (item) => `
        <div class="stat-item">
          <strong>${escapeHtml(item.value)}</strong>
          <span>${escapeHtml(item.label)}</span>
        </div>
      `,
    )
    .join("");
}

function renderRecordCard(record) {
  const task = getTaskSnapshot(record);
  const statusMeta = getStatusMeta(record.review_status);
  const taskTitle = task.title || "暂无任务";
  const taskCategory = task.category || "未知分类";
  const taskPoints = Number(task.points || 0);
  const approvedPoints = Number(record.awarded_points || 0);
  const materialsText = String(record.materials_text || "").trim();
  const reviewReason = String(record.review_reason || "").trim();
  const reviewMeta = [
    record.reviewer ? `审核人：${escapeHtml(record.reviewer)}` : "",
    record.reviewed_at ? `审核时间：${escapeHtml(record.reviewed_at)}` : "",
  ].filter(Boolean).join(" ｜ ");

  return `
    <article class="review-card">
      <header class="review-card__header">
        <div class="review-card__group">
          <div class="group-tag">${escapeHtml(record.group_no)}</div>
          <div>
            <h3>${escapeHtml(record.group_name || "未命名小组")}</h3>
            <div class="subtle">提交编号：${escapeHtml(record.submission_id || "")}</div>
          </div>
        </div>
        <div class="status-wrap">
          <span class="${statusMeta.className}">${statusMeta.label}</span>
          <span class="points-pill">${taskPoints} 分</span>
        </div>
      </header>

      <div class="review-card__body">
        <div class="info-grid">
          <div class="info-box">
            <div class="section-title">任务信息</div>
            <div class="task-line">${escapeHtml(taskCategory)} · ${escapeHtml(taskTitle)}</div>
            <div class="subtle">提交时间：${escapeHtml(formatDate(record.submitted_at))}</div>
          </div>
          <div class="info-box">
            <div class="section-title">审核结果</div>
            <div class="task-line">${escapeHtml(record.review_status || "pending")}</div>
            <div class="subtle">${reviewMeta || "尚无审核记录"}</div>
          </div>
        </div>

        <div class="info-box">
          <div class="section-title">提交文字</div>
          <pre class="materials-content">${escapeHtml(materialsText || "（无文字提交）")}</pre>
        </div>

        ${renderAttachments(record)}

        <div class="review-footnote">
          <span>提交人：${escapeHtml(record.submitter_qq || "")}</span>
          <span>本次发放：${approvedPoints} 分</span>
          <span>状态备注：${escapeHtml(reviewReason || "无")}</span>
        </div>
      </div>

      <footer class="review-card__actions">
        ${
          String(record.review_status || "pending").toLowerCase() === "pending"
            ? `
              <button class="btn btn--primary" data-action="approve" data-submission-id="${escapeHtml(record.submission_id || "")}" data-group-no="${escapeHtml(record.group_no || "")}">通过</button>
              <button class="btn btn--danger" data-action="reject" data-submission-id="${escapeHtml(record.submission_id || "")}" data-group-no="${escapeHtml(record.group_no || "")}">拒绝</button>
            `
            : `
              <button class="btn btn--ghost" data-action="reset" data-submission-id="${escapeHtml(record.submission_id || "")}" data-group-no="${escapeHtml(record.group_no || "")}">取消审核状态</button>
            `
        }
        <button class="btn btn--danger" data-action="delete" data-submission-id="${escapeHtml(record.submission_id || "")}" data-group-no="${escapeHtml(record.group_no || "")}" style="background: linear-gradient(135deg, #8b0000, #a52a2a);">删除记录</button>
      </footer>
    </article>
  `;
}

function renderRecords() {
  if (!reviewRecords.length) {
    recordsContainer.innerHTML = '<div class="empty-state">暂无提交记录</div>';
    return;
  }

  recordsContainer.innerHTML = reviewRecords.map((record) => renderRecordCard(record)).join("");

  recordsContainer.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action || "";
      const submissionId = button.dataset.submissionId || "";
      const groupNo = button.dataset.groupNo || "";
      if (!submissionId) {
        return;
      }

      if (action === "approve") {
        await updateReview(submissionId, "approved", groupNo);
      } else if (action === "reject") {
        await updateReview(submissionId, "rejected", groupNo);
      } else if (action === "reset") {
        await updateReview(submissionId, "pending", groupNo);
      } else if (action === "delete") {
        await deleteSubmission(submissionId, groupNo);
      }
    });
  });
}

function parseTokenList(raw) {
  return String(raw || "")
    .split(/[\s,，;；\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

// 根据QQ号自动匹配小组
async function findGroupByQQ(qq) {
  if (!qq || !bridge) return null;
  
  try {
    const payload = await bridge.apiGet("state");
    const result = normalizeApiResponse(payload);
    if (!result.success) return null;
    
    const state = result.data || {};
    const groups = state.groups || {};
    
    for (const [groupNo, groupData] of Object.entries(groups)) {
      const members = Array.isArray(groupData.members) ? groupData.members : [];
      if (members.includes(String(qq))) {
        return { group_no: groupNo, group_name: groupData.group_name || "" };
      }
    }
  } catch (error) {
    console.error("查找小组失败:", error);
  }
  
  return null;
}

// 加载可用任务列表
async function loadAvailableTasks() {
  try {
    console.log("开始加载任务列表...");
    const payload = await bridge.apiGet("tasks/stats");
    console.log("API返回数据:", payload);
    
    const result = normalizeApiResponse(payload);
    console.log("处理后的结果:", result);
    
    if (!result.success) {
      console.error("获取任务列表失败:", result.message || result.error);
      return [];
    }
    
    const data = result.data || {};
    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    console.log(`成功加载 ${tasks.length} 个任务`);
    
    return tasks;
  } catch (error) {
    console.error("加载任务列表失败:", error);
    showMessage(`加载任务列表失败：${error.message}`, "error");
    return [];
  }
}

// 更新任务选择器
function updateTaskSelector(tasks) {
  if (!taskSelector) {
    console.error("任务选择器元素未找到");
    return;
  }
  
  console.log(`更新任务选择器，共 ${tasks.length} 个任务`);
  
  taskSelector.innerHTML = '<option value="">-- 从当前任务中选择 --</option>';
  
  tasks.forEach((task, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = `${task.category || "未分类"} - ${task.title || "未命名"} (${task.points || 0}分)`;
    option.dataset.category = task.category || "";
    option.dataset.title = task.title || "";
    option.dataset.points = task.points || 0;
    taskSelector.appendChild(option);
  });
  
  console.log("任务选择器更新完成");
}

// 处理任务选择变化
function handleTaskSelection(event) {
  const selectedIndex = event.target.value;
  if (!selectedIndex && selectedIndex !== "0") {
    taskCategoryInput.value = "";
    taskTitleInput.value = "";
    taskPointsInput.value = "";
    return;
  }
  
  const task = availableTasks[parseInt(selectedIndex)];
  if (task) {
    taskCategoryInput.value = task.category || "";
    taskTitleInput.value = task.title || "";
    taskPointsInput.value = task.points || 0;
  }
}

// 处理图片文件选择
function handleImageFileSelect(event) {
  const files = Array.from(event.target.files || []);
  selectedImageFiles = [...selectedImageFiles, ...files];
  renderImagePreview();
}

// 渲染图片预览
function renderImagePreview() {
  if (!imagePreviewContainer) return;
  
  imagePreviewContainer.innerHTML = "";
  
  selectedImageFiles.forEach((file, index) => {
    const previewItem = document.createElement("div");
    previewItem.className = "image-preview-item";
    
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.alt = file.name;
    
    const removeBtn = document.createElement("button");
    removeBtn.className = "image-preview-remove";
    removeBtn.type = "button";
    removeBtn.textContent = "×";
    removeBtn.onclick = () => {
      selectedImageFiles.splice(index, 1);
      renderImagePreview();
    };
    
    previewItem.appendChild(img);
    previewItem.appendChild(removeBtn);
    imagePreviewContainer.appendChild(previewItem);
  });
}

// 上传图片到服务器
async function uploadImages(files) {
  if (!files || files.length === 0) return [];
  
  const uploadedUrls = [];
  
  for (const file of files) {
    try {
      // 使用FormData上传文件
      const formData = new FormData();
      formData.append("file", file);
      
      const result = await bridge.apiPost("review/upload-image", formData);
      const normalized = normalizeApiResponse(result);
      
      if (normalized.success && normalized.data?.url) {
        uploadedUrls.push(normalized.data.url);
      } else {
        console.warn(`图片上传失败: ${file.name}`);
      }
    } catch (error) {
      console.error(`上传图片出错: ${file.name}`, error);
    }
  }
  
  return uploadedUrls;
}

// 删除提交记录
async function deleteSubmission(submissionId, groupNo) {
  // 使用自定义确认对话框（避免sandbox的allow-modals限制）
  const confirmed = await showCustomConfirm(`确定要删除提交记录 ${submissionId} 吗？此操作不可恢复！`);
  if (!confirmed) return;
  
  setLoading(true);
  try {
    const payload = await bridge.apiPost("review/delete", {
      submission_id: submissionId,
      group_no: groupNo,
    });
    const result = normalizeApiResponse(payload);
    
    if (!result.success) {
      throw new Error(result.message || result.error || "删除失败");
    }
    
    showMessage(`已删除提交记录 ${submissionId}`, "ok");
    await loadRecords();
  } catch (error) {
    console.error("Error deleting submission:", error);
    showMessage(`删除出错：${error.message}`, "error");
  } finally {
    setLoading(false);
  }
}

function setLoading(isLoading) {
  refreshBtn.disabled = isLoading;
  filterSelect.disabled = isLoading;
  exportAllBtn.disabled = isLoading;
  exportApprovedBtn.disabled = isLoading;
}

async function loadRecords() {
  setLoading(true);
  try {
    const payload = await bridge.apiGet("review/records", {
      status: filterSelect.value,
      with_preview: "0",
    });
    const result = normalizeApiResponse(payload);

    if (!result.success) {
      throw new Error(result.message || result.error || "加载失败");
    }

    const data = result.data || {};
    reviewRecords = Array.isArray(data.records) ? data.records : [];
    renderStats(data);
    renderRecords();
    showMessage(`已加载 ${reviewRecords.length} 条提交记录`, "ok");
  } catch (error) {
    console.error("Error loading review records:", error);
    showMessage(`加载出错：${error.message}`, "error");
    recordsContainer.innerHTML = '<div class="empty-state empty-state--error">加载失败，请检查后端接口是否可用。</div>';
  } finally {
    setLoading(false);
  }
}

async function updateReview(submissionId, verdict, groupNo) {
  const actionLabel = verdict === "approved" ? "通过" : verdict === "rejected" ? "拒绝" : "取消审核状态";
  
  // 使用自定义确认对话框而不是window.confirm（避免sandbox限制）
  const confirmed = await showCustomConfirm(`确定要对提交 ${submissionId} 执行「${actionLabel}」吗？`);
  if (!confirmed) {
    return;
  }

  setLoading(true);
  try {
    const payload = await bridge.apiPost("review/update", {
      submission_id: submissionId,
      verdict,
      group_no: groupNo || "",
      reviewer: pageContext?.displayName || pageContext?.pluginName || "admin",
      review_reason:
        verdict === "pending" ? "审核状态已取消" : verdict === "approved" ? "后台审核通过" : "后台审核拒绝",
    });
    const result = normalizeApiResponse(payload);

    if (!result.success) {
      throw new Error(result.message || result.error || "更新失败");
    }

    const awardedPoints = result.data?.awarded_points ?? result.awarded_points ?? 0;
    showMessage(`已${actionLabel}提交 ${submissionId}，积分变更：${awardedPoints} 分`, "ok");
    await loadRecords();
  } catch (error) {
    console.error("Error updating review:", error);
    showMessage(`操作出错：${error.message}`, "error");
  } finally {
    setLoading(false);
  }
}

// 自定义确认对话框（避免sandbox的allow-modals限制）
function showCustomConfirm(message) {
  return new Promise((resolve) => {
    // 创建模态框
    const modal = document.createElement("div");
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
    `;
    
    const dialog = document.createElement("div");
    dialog.style.cssText = `
      background: white;
      padding: 24px;
      border-radius: 16px;
      max-width: 400px;
      width: 90%;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
    `;
    
    dialog.innerHTML = `
      <div style="margin-bottom: 20px; font-size: 16px; color: #172033;">${message}</div>
      <div style="display: flex; gap: 12px; justify-content: flex-end;">
        <button id="confirmCancel" style="padding: 10px 20px; border-radius: 8px; border: 1px solid #dce5ef; background: white; cursor: pointer;">取消</button>
        <button id="confirmOk" style="padding: 10px 20px; border-radius: 8px; border: none; background: linear-gradient(135deg, #1f7a4f, #1891a3); color: white; cursor: pointer;">确定</button>
      </div>
    `;
    
    modal.appendChild(dialog);
    document.body.appendChild(modal);
    
    const cleanup = () => {
      document.body.removeChild(modal);
    };
    
    document.getElementById("confirmCancel").onclick = () => {
      cleanup();
      resolve(false);
    };
    
    document.getElementById("confirmOk").onclick = () => {
      cleanup();
      resolve(true);
    };
    
    // 点击背景关闭
    modal.onclick = (e) => {
      if (e.target === modal) {
        cleanup();
        resolve(false);
      }
    };
  });
}

async function createManualRecord(formData) {
  setLoading(true);
  try {
    // 先上传图片
    let imageUrls = [];
    if (selectedImageFiles.length > 0) {
      showMessage("正在上传图片...", "ok");
      imageUrls = await uploadImages(selectedImageFiles);
      if (imageUrls.length === 0) {
        throw new Error("图片上传失败");
      }
      showMessage(`成功上传 ${imageUrls.length} 张图片`, "ok");
    }
    
    const payload = {
      group_no: String(formData.get("group_no") || "").trim(),
      submitter_qq: String(formData.get("submitter_qq") || "").trim(),
      materials_text: String(formData.get("materials_text") || "").trim(),
      task_category: String(formData.get("task_category") || "").trim(),
      task_title: String(formData.get("task_title") || "").trim(),
      task_points: String(formData.get("task_points") || "").trim(),
      review_status: String(formData.get("review_status") || "pending").trim(),
      image_urls: imageUrls,
      review_reason: String(formData.get("review_reason") || "").trim(),
      reviewer: pageContext?.displayName || pageContext?.pluginName || "admin",
    };

    const payloadResult = await bridge.apiPost("review/create", payload);
    const result = normalizeApiResponse(payloadResult);
    if (!result.success) {
      throw new Error(result.message || result.error || "新增失败");
    }

    showMessage(`已新增提交记录 ${result.data?.submission?.submission_id || ""}`, "ok");
    manualCreateForm.reset();
    selectedImageFiles = [];
    renderImagePreview();
    autoGroupNoInput.value = "";
    await loadRecords();
  } catch (error) {
    console.error("Error creating manual record:", error);
    showMessage(`新增出错：${error.message}`, "error");
  } finally {
    setLoading(false);
  }
}

async function exportCsv(status) {
  setLoading(true);
  try {
    const filename = status === "approved" ? "blindbox_review_approved.csv" : "blindbox_review_all.csv";
    if (typeof bridge.download === "function") {
      await bridge.download("review/export-csv", { status }, filename);
      showMessage(`已开始导出 ${status === "approved" ? "通过" : "全部"} 提交 CSV`, "ok");
      return;
    }

    const payload = await bridge.apiGet("review/export-csv", { status });
    const result = normalizeApiResponse(payload);
    if (!result.success) {
      throw new Error(result.message || result.error || "导出失败");
    }

    const csvText = typeof result === "string" ? result : result.data?.csv || result.csv || "";
    if (!csvText) {
      throw new Error("导出结果为空");
    }

    const blob = new Blob(["\ufeff" + csvText], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
    showMessage(`已导出 ${status === "approved" ? "通过" : "全部"} 提交 CSV`, "ok");
  } catch (error) {
    console.error("Error exporting CSV:", error);
    showMessage(`导出出错：${error.message}`, "error");
  } finally {
    setLoading(false);
  }
}

function bindEvents() {
  refreshBtn.addEventListener("click", () => loadRecords());
  filterSelect.addEventListener("change", () => loadRecords());
  exportAllBtn.addEventListener("click", () => exportCsv("all"));
  exportApprovedBtn.addEventListener("click", () => exportCsv("approved"));
  
  // QQ号输入时自动匹配小组
  if (submitterQQInput) {
    let debounceTimer = null;
    submitterQQInput.addEventListener("input", (event) => {
      clearTimeout(debounceTimer);
      const qq = event.target.value.trim();
      
      debounceTimer = setTimeout(async () => {
        if (qq) {
          const group = await findGroupByQQ(qq);
          if (group) {
            autoGroupNoInput.value = `${group.group_no} (${group.group_name})`;
            autoGroupNoInput.dataset.groupNo = group.group_no;
          } else {
            autoGroupNoInput.value = "未找到对应小组";
            autoGroupNoInput.dataset.groupNo = "";
          }
        } else {
          autoGroupNoInput.value = "";
          autoGroupNoInput.dataset.groupNo = "";
        }
      }, 500);
    });
  }
  
  // 任务选择器变化
  if (taskSelector) {
    taskSelector.addEventListener("change", handleTaskSelection);
  }
  
  // 图片文件选择
  if (imageFilesInput) {
    imageFilesInput.addEventListener("change", handleImageFileSelect);
  }
  
  if (manualCreateForm) {
    manualCreateForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      
      // 使用自动匹配的小组号
      const groupNo = autoGroupNoInput.dataset.groupNo || "";
      if (!groupNo) {
        showMessage("请先输入有效的提交人QQ号以自动匹配小组", "error");
        return;
      }
      
      const formData = new FormData(manualCreateForm);
      formData.set("group_no", groupNo);
      await createManualRecord(formData);
    });
  }
}

async function init() {
  try {
    const bridgeApi = await getBridge();
    pageContext = await bridgeApi.ready();
    
    // 加载可用任务列表
    availableTasks = await loadAvailableTasks();
    updateTaskSelector(availableTasks);
    
    bindEvents();
    await loadRecords();
  } catch (error) {
    console.error("Could not initialize review page:", error);
    showMessage(`初始化失败：${error.message}`, "error");
    recordsContainer.innerHTML = '<div class="empty-state empty-state--error">页面初始化失败，请检查 AstrBot 插件页 bridge 是否可用。</div>';
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

window.confirmReview = updateReview;
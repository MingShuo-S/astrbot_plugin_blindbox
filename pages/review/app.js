const bridge = window.AstrBotPluginPage;

const statsEl = document.getElementById("stats");
const messageEl = document.getElementById("message");
const refreshBtn = document.getElementById("refreshBtn");
const exportAllBtn = document.getElementById("exportAllBtn");
const exportApprovedBtn = document.getElementById("exportApprovedBtn");
const filterSelect = document.getElementById("filterSelect");
const recordsContainer = document.getElementById("reviews-container");

let pageContext = null;
let reviewRecords = [];

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
          .map((item) => {
            if (item.url) {
              return `
                <a class="attachment-card" href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">
                  <img src="${escapeHtml(item.url)}" alt="提交图片" loading="lazy" />
                  <span>${escapeHtml(item.name || "图片")}</span>
                </a>
              `;
            }

            return `
              <div class="attachment-card attachment-card--missing">
                <div class="attachment-placeholder">图片已保存到服务器</div>
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
      }
    });
  });
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
      with_preview: "1",
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
  const confirmed = window.confirm(`确定要对提交 ${submissionId} 执行「${actionLabel}」吗？`);
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
}

async function init() {
  try {
    pageContext = await bridge.ready();
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
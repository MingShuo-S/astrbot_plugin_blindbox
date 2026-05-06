const bridge = window.AstrBotPluginPage;
const statsEl = document.getElementById("stats");
const messageEl = document.getElementById("message");
const refreshBtn = document.getElementById("refreshBtn");
const reviewsContainer = document.getElementById("reviews-container");

let pageContext = null;
let pendingReviews = [];

function showMessage(text, type = "ok") {
  messageEl.textContent = text;
  messageEl.className = `message ${type}`;
}

function formatImages(imageUrls) {
  if (!imageUrls || imageUrls.length === 0) {
    return "";
  }
  return imageUrls
    .map((url) => `<img src="${escapeHtml(url)}" alt="提交图片" class="submission-image" />`)
    .join("");
}

function escapeHtml(text) {
  const map = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  };
  return String(text).replace(/[&<>"']/g, (char) => map[char]);
}

function renderReviewCard(review) {
  const taskTitle = review.task_snapshot?.title || "暂无任务";
  const taskCategory = review.task_snapshot?.category || "未知类型";
  const taskPoints = review.task_snapshot?.points || 0;
  const submittedAt = review.submitted_at || "未知时间";

  const imageHtml = formatImages(review.image_urls);
  const materialsHtml = `<pre class="materials-content">${escapeHtml(
    review.materials_text
  )}</pre>`;

  return `
    <div class="review-card">
      <div class="review-header">
        <div class="review-info">
          <div class="review-badge group-no">${escapeHtml(review.group_no)}</div>
          <h3>${escapeHtml(review.group_name)}</h3>
          <span class="submission-id">ID: ${escapeHtml(review.submission_id)}</span>
        </div>
        <div class="task-info">
          <span class="task-category">${escapeHtml(taskCategory)}</span>
          <span class="task-title">${escapeHtml(taskTitle)}</span>
          <span class="task-points">${taskPoints}分</span>
        </div>
      </div>

      <div class="submission-details">
        <div class="submitted-by">
          <strong>提交人：</strong> ${escapeHtml(review.submitter_qq)}
          <span class="submitted-at">（${submittedAt}）</span>
        </div>

        <div class="materials-section">
          <strong>提交内容：</strong>
          ${materialsHtml}
        </div>

        ${imageHtml ? `<div class="images-section"><strong>附件图片：</strong><div class="images-grid">${imageHtml}</div></div>` : ""}
      </div>

      <div class="review-actions">
        <button class="btn btn-approve" onclick="confirmReview('${escapeHtml(
          review.submission_id
        )}', 'approved')">
          ✓ 通过
        </button>
        <button class="btn btn-reject" onclick="confirmReview('${escapeHtml(
          review.submission_id
        )}', 'rejected')">
          ✗ 拒绝
        </button>
      </div>
    </div>
  `;
}

function renderReviews() {
  if (pendingReviews.length === 0) {
    reviewsContainer.innerHTML = '<div class="empty-state">暂无待审核的提交</div>';
    return;
  }

  reviewsContainer.innerHTML = pendingReviews.map((review) => renderReviewCard(review)).join("");
}

function updateStats() {
  if (pendingReviews.length === 0) {
    statsEl.innerHTML = '<div class="stat-item"><span class="stat-value">0</span><span class="stat-label">待审核</span></div>';
  } else {
    const byGroup = {};
    pendingReviews.forEach((review) => {
      byGroup[review.group_no] = (byGroup[review.group_no] || 0) + 1;
    });

    const items = [
      { value: String(pendingReviews.length), label: "待审核总数" },
      { value: String(Object.keys(byGroup).length), label: "涉及小组数" },
    ];

    statsEl.innerHTML = items
      .map(
        (item) =>
          `<div class="stat-item"><span class="stat-value">${item.value}</span><span class="stat-label">${item.label}</span></div>`
      )
      .join("");
  }
}

async function loadPendingReviews() {
  try {
    const baseUrl = pageContext?.base_url || "";
    const response = await fetch(`${baseUrl}/api/pending-reviews`);
    const json = await response.json();

    if (json.success) {
      pendingReviews = json.data || [];
      renderReviews();
      updateStats();
      showMessage("已加载待审核列表", "ok");
    } else {
      showMessage(`加载失败：${json.error}`, "error");
    }
  } catch (error) {
    console.error("Error loading reviews:", error);
    showMessage(`加载出错：${error.message}`, "error");
  }
}

async function confirmReview(submissionId, verdict) {
  if (!confirm(`确定要 ${verdict === "approved" ? "通过" : "拒绝"} 这条提交吗？`)) {
    return;
  }

  try {
    const baseUrl = pageContext?.base_url || "";
    const response = await fetch(`${baseUrl}/api/confirm-review`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        submission_id: submissionId,
        verdict: verdict,
      }),
    });

    const json = await response.json();

    if (json.success) {
      showMessage(
        `✓ 已 ${verdict === "approved" ? "通过" : "拒绝"} 提交 ${submissionId}，已发放 ${json.awarded_points || 0} 积分`,
        "ok"
      );
      // 重新加载列表
      await loadPendingReviews();
    } else {
      showMessage(`确认失败：${json.error}`, "error");
    }
  } catch (error) {
    console.error("Error confirming review:", error);
    showMessage(`确认出错：${error.message}`, "error");
  }
}

async function init() {
  try {
    pageContext = bridge.getContext?.();
  } catch (error) {
    console.warn("Could not get page context:", error);
  }

  refreshBtn.addEventListener("click", loadPendingReviews);
  await loadPendingReviews();
}

document.addEventListener("DOMContentLoaded", init);

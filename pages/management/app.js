const bridge = window.AstrBotPluginPage;
const groupsEl = document.getElementById("groups");
const statsEl = document.getElementById("stats");
const messageEl = document.getElementById("message");
const statusBadge = document.getElementById("statusBadge");
const refreshBtn = document.getElementById("refreshBtn");
const createForm = document.getElementById("createForm");
const exportAllBtn = document.getElementById("exportAllBtn");
const importFileInput = document.getElementById("importFileInput");

let pageContext = null;
let state = null;

function showMessage(text, type = "ok") {
  messageEl.textContent = text;
  messageEl.className = `message ${type}`;
}

function setStatus(text, type = "ok") {
  statusBadge.textContent = text;
  statusBadge.className = `badge ${type}`;
}

function parseQqList(raw) {
  return raw
    .split(/[\s,，;；\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function summarizeState(data) {
  const groups = Object.keys(data.groups || {}).length;
  const members = Object.values(data.groups || {}).reduce((count, group) => {
    const list = Array.isArray(group.members) ? group.members.length : 0;
    return count + list;
  }, 0);
  const draws = Object.keys(data.draws || {}).length;
  const requested = Object.values(data.groups || {}).filter((group) => group.dissolve_requested).length;

  return [
    { value: String(groups), label: "小组总数" },
    { value: String(members), label: "成员总数" },
    { value: String(draws), label: "本周已抽" },
    { value: String(requested), label: "申请解散" },
  ];
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

function renderStats(data) {
  statsEl.innerHTML = summarizeState(data)
    .map(
      (item) => `
        <div class="stat">
          <strong>${escapeText(item.value)}</strong>
          <span>${escapeText(item.label)}</span>
        </div>
      `,
    )
    .join("");
}

function groupDrawText(groupNo, data) {
  const draw = data.draws?.[groupNo];
  if (!draw) {
    return "本周还没有抽取任务。";
  }

  return `本周任务：${draw.category} - ${draw.title} ｜ ${draw.points} 分 ｜ ${draw.week}`;
}

function renderMemberOptions(members, selectedValue) {
  if (!members.length) {
    return '<option value="">暂无成员</option>';
  }

  return members
    .map(
      (member) =>
        `<option value="${escapeText(member)}"${member === selectedValue ? " selected" : ""}>${escapeText(member)}</option>`,
    )
    .join("");
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function renderGroups(data) {
  const groups = data.groups || {};
  const entries = Object.values(groups);

  if (!entries.length) {
    groupsEl.innerHTML = `
      <div class="group-card">
        <div class="group-name">暂无小组</div>
        <div class="group-meta">可以先在左上角创建一个小组。</div>
      </div>
    `;
    return;
  }

  groupsEl.innerHTML = entries
    .sort((left, right) => String(left.group_no).localeCompare(String(right.group_no), "zh-Hans-CN", { numeric: true }))
    .map((group) => {
      const members = Array.isArray(group.members) ? group.members : [];
      const leader = group.leader_qq || members[0] || "未设置";
      const requestBadge = group.dissolve_requested ? '<span class="group-badge warn">已申请解散</span>' : "";
      const membersText = members.length ? members.join("、") : "无";
      const transferDisabled = members.length ? "" : "disabled";
      const transferOptions = renderMemberOptions(members, leader);
      const dissolveAction = group.dissolve_requested
        ? '<button class="secondary" data-action="cancel-dissolve">取消解散申请</button>'
        : '<button class="secondary" data-action="request-dissolve">申请解散</button>';

      return `
        <article class="group-card" data-group-no="${escapeText(group.group_no)}">
          <div class="group-top">
            <div>
              <h3 class="group-name">${escapeText(group.group_name)} </h3>
              <div class="group-meta">序号：${escapeText(group.group_no)} ｜ 组长：${escapeText(leader)} ｜ 成员数：${members.length}</div>
            </div>
            ${requestBadge}
          </div>

          <div class="group-members"><strong>成员：</strong>${escapeText(membersText)}</div>
          <div class="group-draw"><strong>任务：</strong>${escapeText(groupDrawText(group.group_no, data))}</div>

          <div class="inline-form">
            <input data-add-input placeholder="添加成员 QQ，用逗号分隔" />
            <button class="ghost" data-action="add">添加</button>
          </div>

          <div class="inline-form">
            <input data-remove-input placeholder="移除成员 QQ，用逗号分隔" />
            <button class="ghost" data-action="remove">移除</button>
          </div>

          <div class="group-actions">
            <div class="inline-form inline-form--wide">
              <select data-transfer-select>
                ${transferOptions}
              </select>
              <button class="ghost" data-action="transfer" ${transferDisabled}>转让组长</button>
            </div>
            <button class="secondary" data-action="redraw">重抽本周任务</button>
            <button class="secondary" data-action="export">导出记录</button>
            ${dissolveAction}
            <button class="danger" data-action="dissolve">直接解散</button>
          </div>
        </article>
      `;
    })
    .join("");

  groupsEl.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const card = button.closest("[data-group-no]");
      if (!card) {
        return;
      }

      const groupNo = card.dataset.groupNo;
      const action = button.dataset.action;
      const addInput = card.querySelector("[data-add-input]");
      const removeInput = card.querySelector("[data-remove-input]");
      const transferSelect = card.querySelector("[data-transfer-select]");

      try {
        if (action === "add") {
          const qqList = parseQqList(addInput.value || "");
          await callApi("group/add", { group_no: groupNo, qq_list: qqList });
          addInput.value = "";
        } else if (action === "remove") {
          const qqList = parseQqList(removeInput.value || "");
          await callApi("group/remove", { group_no: groupNo, qq_list: qqList });
          removeInput.value = "";
        } else if (action === "redraw") {
          console.debug("redraw clicked", groupNo);
          showMessage(`正在为小组 ${groupNo} 重抽...`, "ok");
          await callApi("group/redraw", { group_no: groupNo, force_redraw: true });
        } else if (action === "request-dissolve") {
          await callApi("group/request-dissolve", { group_no: groupNo });
        } else if (action === "cancel-dissolve") {
          await callApi("group/cancel-dissolve", { group_no: groupNo });
        } else if (action === "transfer") {
          const newLeaderQq = String(transferSelect.value || "").trim();
          await callApi("group/transfer-leader", { group_no: groupNo, new_leader_qq: newLeaderQq });
        } else if (action === "export") {
          const result = await callApi("group/export-submissions", { group_no: groupNo });
          downloadJson(`blindbox-group-${groupNo}-submissions.json`, result);
        } else if (action === "dissolve") {
          console.debug("dissolve clicked", groupNo);
          const confirmed = await showConfirm(`确认解散小组 ${groupNo} 吗？`);
          if (!confirmed) {
            return;
          }
          showMessage(`正在解散小组 ${groupNo}...`, "warn");
          await callApi("group/dissolve", { group_no: groupNo });
        }
        await loadState();
      } catch (error) {
        showMessage(error.message || String(error), "err");
      }
    });
  });
}

// 全部导出
if (exportAllBtn) {
  exportAllBtn.addEventListener("click", async () => {
    try {
      setStatus("导出中", "warn");
      // Dashboard bridge provides download via apiGet
      const resp = await bridge.apiGet("group/export-submissions-all-csv");
      // 如果返回的是对象（bridge 可能封装为 { success, data }），尝试用文件下载方法
      if (resp && typeof resp === "object" && resp.csv) {
        const blob = new Blob(["\ufeff" + resp.csv], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = resp.filename || `blindbox_all_groups_${Date.now()}.csv`;
        a.click();
        URL.revokeObjectURL(url);
      } else if (typeof resp === "string") {
        const blob = new Blob(["\ufeff" + resp], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `blindbox_all_groups_${Date.now()}.csv`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        showMessage("导出失败：返回格式未知。", "err");
      }
    } catch (err) {
      showMessage(err.message || String(err), "err");
    } finally {
      setStatus("在线", "ok");
    }
  });
}

// 全部导入（CSV 文本），前端读取文件并以文本形式 POST 到后端处理
if (importFileInput) {
  importFileInput.addEventListener("change", async (ev) => {
    const file = ev.target.files && ev.target.files[0];
    if (!file) return;
    if (!confirm(`确认导入文件：${file.name} ? 这将覆盖对应小组的提交记录。`)) return;
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const text = String(reader.result || "");
        setStatus("导入中", "warn");
        await callApi("group/import-submissions-all-csv", { csv: text });
        await loadState();
        showMessage("导入完成", "ok");
      } catch (err) {
        showMessage(err.message || String(err), "err");
      } finally {
        setStatus("在线", "ok");
      }
    };
    if (file.name.endsWith(".xlsx")) {
      showMessage("不支持直接解析 .xlsx，请另存为 CSV 并重试。", "err");
      return;
    }
    reader.readAsText(file, "utf-8");
  });
}

function normalizeApiResponse(payload) {
  if (payload && typeof payload === "object" && "success" in payload) {
    return payload;
  }
  return { success: true, message: "操作成功", data: payload };
}

// 自定义确认对话框，返回 Promise<boolean>
function showConfirm(message) {
  return new Promise((resolve) => {
    let modal = document.getElementById("confirmModal");
    let textEl = document.getElementById("confirmModalText");
    const okBtn = document.getElementById("confirmOkBtn");
    const cancelBtn = document.getElementById("confirmCancelBtn");
    if (!modal || !textEl || !okBtn || !cancelBtn) {
      // 回退为同步 confirm（仅在允许时）
      try {
        resolve(window.confirm(message));
      } catch (e) {
        resolve(false);
      }
      return;
    }

    textEl.textContent = message;
    modal.style.display = "flex";

    function cleanup() {
      modal.style.display = "none";
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
    }

    function onOk() {
      cleanup();
      resolve(true);
    }

    function onCancel() {
      cleanup();
      resolve(false);
    }

    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
  });
}

async function callApi(endpoint, body) {
  const payload = await bridge.apiPost(endpoint, body);
  const result = normalizeApiResponse(payload);
  if (!result.success) {
    throw new Error(result.message || "请求失败");
  }
  if (result.message) {
    showMessage(result.message, "ok");
  }
  return result.data ?? result;
}

async function loadState() {
  setStatus("加载中", "warn");
  const payload = await bridge.apiGet("state");
  const result = normalizeApiResponse(payload);
  if (!result.success) {
    throw new Error(result.message || "无法加载数据");
  }

  state = result.data;
  renderStats(state);
  renderGroups(state);
  setStatus("在线", "ok");
}

createForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const formData = new FormData(createForm);
    const qqList = parseQqList(String(formData.get("qq_list") || ""));
    await callApi("group/create", {
      group_no: String(formData.get("group_no") || "").trim(),
      group_name: String(formData.get("group_name") || "").trim(),
      qq_list: qqList,
    });
    createForm.reset();
    await loadState();
  } catch (error) {
    showMessage(error.message || String(error), "err");
  }
});

refreshBtn.addEventListener("click", async () => {
  try {
    await loadState();
  } catch (error) {
    showMessage(error.message || String(error), "err");
  }
});

(async () => {
  try {
    pageContext = await bridge.ready();
    showMessage(`已连接到 ${pageContext.displayName || pageContext.pluginName}`, "ok");
    await loadState();
  } catch (error) {
    setStatus("离线", "warn");
    showMessage(error.message || String(error), "err");
  }
})();

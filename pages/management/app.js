const bridge = window.AstrBotPluginPage;
const groupsEl = document.getElementById("groups");
const statsEl = document.getElementById("stats");
const messageEl = document.getElementById("message");
const statusBadge = document.getElementById("statusBadge");
const refreshBtn = document.getElementById("refreshBtn");
const debugStateBtn = document.getElementById("debugStateBtn");
const healthCheckBtn = document.getElementById("healthCheckBtn");
const createForm = document.getElementById("createForm");
const exportAllBtn = document.getElementById("exportAllBtn");
const debugStateOutput = document.getElementById("debugStateOutput");

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
  const totalScore = Object.values(data.groups || {}).reduce((count, group) => {
    const score = Number(group.score_total || 0);
    return count + (Number.isFinite(score) ? score : 0);
  }, 0);
  const draws = Object.keys(data.draws || {}).length;
  const requested = Object.values(data.groups || {}).filter((group) => group.dissolve_requested).length;

  return [
    { value: String(groups), label: "小组总数" },
    { value: String(members), label: "成员总数" },
    { value: String(totalScore), label: "累计积分" },
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

function getActiveTasks(data) {
  return Array.isArray(data.tasks) ? data.tasks.filter((task) => task && task.enabled !== false) : [];
}

function findTaskIndex(tasks, draw) {
  if (!draw) {
    return -1;
  }

  return tasks.findIndex(
    (task) =>
      String(task.category || "") === String(draw.category || "") &&
      String(task.title || "") === String(draw.title || "") &&
      String(task.points || 0) === String(draw.points || 0),
  );
}

function renderTaskOptions(tasks, selectedIndex) {
  if (!tasks.length) {
    return '<option value="">暂无可选任务</option>';
  }

  return [
    '<option value="">-- 从任务列表中选择 --</option>',
    ...tasks.map(
      (task, index) =>
        `<option value="${index}"${index === selectedIndex ? " selected" : ""}>${escapeText(task.category || "未分类")} - ${escapeText(task.title || "未命名")}（${escapeText(task.points || 0)} 分）</option>`,
    ),
  ].join("");
}

function renderTaskOverview(data, groupNo) {
  const overview = data.task_overviews?.[groupNo];
  if (overview && typeof overview.summary_text === "string" && overview.summary_text.trim()) {
    return `<pre class="task-overview">${escapeText(overview.summary_text)}</pre>`;
  }

  const draw = data.draws?.[groupNo];
  if (!draw) {
    return '<div class="task-overview task-overview--empty">当前没有进行中的任务。</div>';
  }

  const lines = [
    "【当前盲盒任务】",
    "状态：信息尚未加载",
    `分类：${draw.category || ""}`,
    `任务：${draw.title || ""}`,
    `建议积分：${draw.points || 0} 分`,
    `抽取时间：${draw.drawn_at || "未知"}`,
    `截止时间：${draw.deadline || "未知"}`,
  ];
  return `<pre class="task-overview">${escapeText(lines.join("\n"))}</pre>`;
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
  const tasks = getActiveTasks(data);

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
      const scoreTotal = Number(group.score_total || 0);
      const draw = data.draws?.[group.group_no];
      const currentTaskIndex = findTaskIndex(tasks, draw);
      const hasActiveDraw = Boolean(draw);
      const requestBadge = group.dissolve_requested ? '<span class="group-badge warn">已申请解散</span>' : "";
      const membersText = members.length ? members.join("、") : "无";
      const transferDisabled = members.length ? "" : "disabled";
      const transferOptions = renderMemberOptions(members, leader);
      const taskOptions = renderTaskOptions(tasks, currentTaskIndex);
      const taskDisabled = hasActiveDraw ? "" : "disabled";
      const dissolveAction = group.dissolve_requested
        ? '<button class="secondary" data-action="cancel-dissolve">取消解散申请</button>'
        : '<button class="secondary" data-action="request-dissolve">申请解散</button>';

      return `
        <article class="group-card" data-group-no="${escapeText(group.group_no)}">
          <div class="group-top">
            <div>
              <h3 class="group-name">${escapeText(group.group_name)} </h3>
              <div class="group-meta">序号：${escapeText(group.group_no)} ｜ 组长：${escapeText(leader)} ｜ 成员数：${members.length}</div>
              <div class="group-score">当前积分：<strong>${escapeText(Number.isFinite(scoreTotal) ? scoreTotal : 0)}</strong></div>
            </div>
            ${requestBadge}
          </div>

          <div class="task-block">
            <div class="section-title">小组目前任务</div>
            ${renderTaskOverview(data, String(group.group_no))}
            <div class="inline-form inline-form--wide task-editor">
              <select data-task-select ${taskDisabled}>
                ${taskOptions}
              </select>
              <button class="ghost" data-action="task-update" ${taskDisabled}>更新当前任务</button>
            </div>
            <div class="hint">更新任务只会替换当前任务内容，不会改动抽取时间或截止时间；没有当前任务的小组不会自动分配。</div>
          </div>

          <div class="inline-form">
            <input data-score-input type="text" value="${escapeText(Number.isFinite(scoreTotal) ? scoreTotal : 0)}" placeholder="输入新积分或 +3 / -2" />
            <button class="ghost" data-action="score-save">保存积分</button>
          </div>

          <div class="inline-form">
            <input data-rename-input placeholder="输入新组名" />
            <button class="ghost" data-action="rename">改名</button>
          </div>

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
      const taskSelect = card.querySelector("[data-task-select]");
      const renameInput = card.querySelector("[data-rename-input]");
      const scoreInput = card.querySelector("[data-score-input]");

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
        } else if (action === "task-update") {
          const taskIndex = String(taskSelect.value || "").trim();
          if (!taskIndex && taskIndex !== "0") {
            throw new Error("请选择一个任务");
          }
          await callApi("group/update-current-task", { group_no: groupNo, task_index: taskIndex });
        } else if (action === "rename") {
          const newGroupName = String(renameInput.value || "").trim();
          if (!newGroupName) {
            throw new Error("新组名不能为空");
          }
          await callApi("group/rename", { group_no: groupNo, new_group_name: newGroupName });
          renameInput.value = "";
        } else if (action === "score-save") {
          const newScore = String(scoreInput.value || "").trim();
          if (!newScore) {
            throw new Error("积分不能为空");
          }
          await callApi("group/set-score", { group_no: groupNo, score_total: newScore });
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

function renderDebugState(payload) {
  if (!debugStateOutput) {
    return;
  }

  const rawState = payload?.raw_state;
  const normalizedState = payload?.normalized_state;
  const report = Array.isArray(payload?.report) ? payload.report : [];
  const groups = rawState && typeof rawState.groups === "object" ? Object.keys(rawState.groups).length : 0;
  const draws = rawState && typeof rawState.draws === "object" ? Object.keys(rawState.draws).length : 0;
  const tasks = Array.isArray(rawState?.tasks) ? rawState.tasks.length : 0;
  const warnings = report.filter((item) => item && item.level === "warn").length;
  const errors = report.filter((item) => item && item.level === "error").length;

  const lines = [
    `原始状态：小组 ${groups} 个，抽取 ${draws} 条，任务 ${tasks} 条`,
    `规范化状态：小组 ${Object.keys(normalizedState?.groups || {}).length} 个，抽取 ${Object.keys(normalizedState?.draws || {}).length} 条`,
    `告警：${warnings}，错误：${errors}`,
  ];

  if (report.length) {
    lines.push("", "诊断明细：");
    for (const item of report) {
      lines.push(`[${item.level || "info"}] ${item.message || ""}`);
    }
  }

  debugStateOutput.textContent = lines.join("\n");
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

// 导入功能已移至插件配置：请在插件配置中使用 `groups_json` / `tasks` 或 `tasks_csv_text` 来管理导入。

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

async function loadDebugState() {
  if (!debugStateOutput) {
    return;
  }

  debugStateOutput.textContent = "加载中...";
  try {
    const payload = await bridge.apiGet("debug/state");
    const result = normalizeApiResponse(payload);
    if (!result.success) {
      throw new Error(result.message || "无法加载诊断信息");
    }
    renderDebugState(result.data);
    showMessage("诊断信息已加载。", "ok");
  } catch (error) {
    debugStateOutput.textContent = error.message || String(error);
    showMessage(error.message || String(error), "err");
  }
}

async function checkBackendHealth() {
  if (!debugStateOutput) {
    return;
  }

  debugStateOutput.textContent = "检测中...";
  const checks = [
    ["state", {}],
    ["review/records", { with_preview: "0" }],
    ["debug/state", {}],
  ];
  const lines = [];

  for (const [endpoint, params] of checks) {
    try {
      const payload = await bridge.apiGet(endpoint, params);
      const result = normalizeApiResponse(payload);
      if (result.success) {
        const data = result.data;
        let extra = "";
        if (endpoint === "state") {
          extra = `groups=${Object.keys(data?.groups || {}).length}, draws=${Object.keys(data?.draws || {}).length}, tasks=${Array.isArray(data?.tasks) ? data.tasks.length : 0}`;
        } else if (endpoint === "review/records") {
          extra = `records=${data?.total ?? 0}, pending=${data?.pending_count ?? 0}`;
        } else if (endpoint === "debug/state") {
          extra = `report=${Array.isArray(data?.report) ? data.report.length : 0}`;
        }
        lines.push(`✅ ${endpoint} 可用 ${extra}`.trim());
      } else {
        lines.push(`⚠️ ${endpoint} 返回业务错误：${result.message || "未知错误"}`);
      }
    } catch (error) {
      lines.push(`❌ ${endpoint} 不可用：${error.message || String(error)}`);
    }
  }

  debugStateOutput.textContent = lines.join("\n");
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

if (debugStateBtn) {
  debugStateBtn.addEventListener("click", async () => {
    await loadDebugState();
  });
}

if (healthCheckBtn) {
  healthCheckBtn.addEventListener("click", async () => {
    await checkBackendHealth();
  });
}

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

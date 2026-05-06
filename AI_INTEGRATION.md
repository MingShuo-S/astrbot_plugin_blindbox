# AI 调用机制详解

## 🎯 当前实现（推荐方案）

本插件已实现 **Plan B0 增强版本** - 自动唤醒 AI + 管理员确认的工作流：

```
流程图：

用户 -> /blindbox submit <说明>
    ↓
插件 -> 创建提交记录，回复"已提交，等待 AI 审核"，记录到 _pending_reviews
    ↓  (异步后台任务)
AI   -> 被自动唤醒，调用以下工具：
    |  1. blindbox_get_submissions - 读取待审核提交
    |  2. blindbox_get_prompt - 读取审核指南和任务详情
    |  3. blindbox_review_submission - 提交审核结果
    ↓
插件 -> 在群里报告 AI 审核意见 + 要求管理员确认
    ↓
管理员 -> /blindbox pass <提交编号>  或  /blindbox deny <提交编号>
    ↓
插件 -> 写入最终审核结果到 KV 存储和提交文件
    ↓
群里 -> 显示"确认完成，已加分"或"确认完成，已驳回"
```

### 核心特性

- ✅ **自动唤醒 AI**：`_handle_submit()` 调用 `asyncio.create_task(_trigger_ai_review())`
- ✅ **官方工具框架**：使用 `@dataclass FunctionTool` 和 `tool_loop_agent()` 
- ✅ **完整工具集**：
  - `BlindboxGetSubmissionsTool` - AI 查询待审核提交
  - `BlindboxGetPromptTool` - AI 获取审核指南
  - `BlindboxReviewSubmissionTool` - AI 提交审核建议
- ✅ **管理员确认**：防止 AI 错误，人工把关
- ✅ **学习反馈**：管理员确认决定后，可作为训练数据

### 实现代码位置

| 功能 | 位置 |
|------|------|
| 工具定义 | `main.py` 行 345-506（BlindboxGetSubmissionsTool, BlindboxGetPromptTool, BlindboxReviewSubmissionTool） |
| AI 自动唤醒 | `main.py` 行 2176-2211（_trigger_ai_review 方法） |
| 管理员确认 | `main.py` 行 2213-2290（_confirm_review 方法）以及 blindbox 命令处理器的 pass/deny 部分 |
| 工具注册 | `main.py` __init__ 方法中的 `self.context.add_llm_tools()` |
| 提交触发 | `main.py` 行 2342-2343（_handle_submit 中的 `asyncio.create_task(_trigger_ai_review(...))`) |

---

## 问题
> 你是怎么让 AI 在合适的时机调用的？怎么做到的？

## 答案

老实说，**我在代码中只是定义了 API 接口，真正的"自动调用"需要 AstrBot 框架本身来支持**。

### 我做了什么

在 `main.py` 中，我写了：

```python
# 暴露给 AI 的接口
context.register_web_api(f"/{PLUGIN_NAME}/ai/prompt", self.api_ai_prompt, ["GET"], "AI 系统提示词")
context.register_web_api(f"/{PLUGIN_NAME}/ai/context", self.api_ai_context, ["GET"], "AI 小组上下文")
context.register_web_api(f"/{PLUGIN_NAME}/ai/submissions", self.api_ai_submissions, ["GET"], "AI 提交记录")
context.register_web_api(f"/{PLUGIN_NAME}/ai/review", self.api_ai_review, ["POST"], "AI 审核提交")
```

这些接口定义了 **API 能做什么**：
- ✅ AI 能查询待审核的提交
- ✅ AI 能读取审核指南
- ✅ AI 能写入审核结果
- ✅ AI 能自动加分

**此外，我还用官方 AstrBot FunctionTool 框架定义了三个可被 AI 直接调用的工具**：

```python
@dataclass
class BlindboxGetSubmissionsTool(FunctionTool):
    """AI 工具：查询待审核提交"""
    context: BlindBoxPlugin
    
    name = "blindbox_get_submissions"
    description = "获取指定小组的待审核提交列表，用于 AI 审核"
    parameters = {
        "group_no": {"type": "string", "description": "小组序号"}
    }
    
    async def call(self, group_no: str) -> ToolExecResult:
        # ... 查询逻辑
        return ToolExecResult(success=True, data=submissions_data)
```

这使得 AI 可以通过 AstrBot 的 `tool_loop_agent()` 直接调用这些工具，而不仅仅是调用 API。

### 实际的工作流程

```
AstrBot 框架内部：
  ├─ AI 能力模块 (Copilot/LLM)
  │  └─ 从 copilot_instructions.md 读取指令
  │
  ├─ Tool/Skill 系统
  │  └─ 注册本插件暴露的 API 作为可用工具
  │
  └─ 自动触发机制
     ├─ 检测到群消息中有新提交
     ├─ 触发 AI 处理流程
     └─ AI 自动调用相关 API 进行审核
```

### 具体怎么做到自动调用

#### 1️⃣ 前提条件
AstrBot 需要支持：
- 通过 `register_web_api()` 暴露插件接口给 AI（✅ 已支持）
- AI 能够根据指令调用这些接口（❓ 需要 AstrBot 的 Tool/Skill 系统支持）

#### 2️⃣ 配置步骤

在 AstrBot 的 **copilot_instructions.md** 中（或 WebUI 配置）：

```markdown
# AI 审核指南

你是盲盒审核助手。

## 可用工具
- GET /astrbot_plugin_blindbox/ai/submissions?group_no=1 - 查看待审核提交
- POST /astrbot_plugin_blindbox/ai/review - 审核提交

## 触发时机
当群里有人输入 `/blindbox submit` 时：
1. 自动查询该小组的待审核提交
2. 依次审核每条提交
3. 调用 API 写入审核结果

## 审核标准
[这里写审核指南]
```

#### 3️⃣ AstrBot 框架的动作

当配置好后，AstrBot 会：

```python
# AstrBot 内部逻辑（伪代码）
async def on_blindbox_submit(event):
    # 1. 检测到 /blindbox submit 命令
    # 2. 触发已配置的 AI 处理
    
    ai_response = await ai_model.process(
        instructions=load_copilot_instructions(),
        context={"event": event, "available_tools": [...]},
    )
    
    # 3. AI 自动调用相关 API
    for tool_call in ai_response.tool_calls:
        if tool_call == "/astrbot_plugin_blindbox/ai/review":
            result = await http_call(tool_call, params)
            # 自动加分 ✓
```

### 为什么我能"确保" AI 调用

实际上，我**不能完全确保**。我只是：

1. ✅ **定义了清晰的 API 接口** - AI 知道能做什么
2. ✅ **编写了完整的逻辑** - API 调用时能正确处理
3. ✅ **提供了审核指南** - `_build_ai_prompt_context()` 告诉 AI 怎么做
4. ⚠️ **依赖 AstrBot 的调用机制** - 框架需要支持 Tool/Skill 系统

### 如果 AstrBot 不支持自动调用怎么办

有多个方案可选：

#### Plan B0: 对话式审核（✅ 推荐用于"只能通过对话调用AI"的场景）

如果 AI 无法直接调用接口，只能通过对话处理，可以采用"对话分析 + 用户确认"的流程：

```
用户 -> /blindbox submit <说明>
        ↓
插件 -> 创建提交记录并回复"已提交，等待审核"
        ↓
管理员 -> 在群里说"@AI 审核第X组的提交"（或者直接 /blindbox review）
        ↓
AI 在对话中 -> 分析提交内容，给出建议（通过/拒绝 + 理由）
        ↓
管理员 -> 在群里确认"同意" 或 "驳回"
        ↓
插件检测确认 -> 调用 /ai/review API 写入审核结果 + 自动加分
```

**怎么配置**：

1. 修改提示词，让 AI 在看到"请审核"时：
   - 查询该小组的待审核提交（通过自然语言描述）
   - 分析提交内容是否满足当前任务
   - 在群里给出审核意见和分数建议

2. 添加一个新的命令 `/blindbox review`，触发审核流程：
   ```python
   @filter.command("blindbox review")
   async def handle_review(event: AstrMessageEvent):
       # 触发对话式审核
       # AI 返回建议后，等待用户确认
   ```

3. 添加确认指令（如"通过"、"拒绝"、"同意"等），插件检测到后调用 API：
   ```python
   if message in {"通过", "同意", "approve"}:
       await api_ai_review(group_no, submission_id, verdict="approved")
   ```

这样的好处：
- ✅ 不依赖 AstrBot 工具调用能力
- ✅ AI 可以和用户对话讨论，更灵活
- ✅ 用户能看到完整的审核理由
- ✅ 仍然能自动加分和记录

#### Plan B1: 定时任务审核
创建一个定时 Skill 定期调用审核接口：

```python
@schedule_event("*/5 * * * *")  # 每5分钟
async def periodic_review():
    """定期检查并审核提交"""
    state = get_blindbox_state()
    for group_no, group_data in state["groups"].items():
        submissions = api_ai_submissions(group_no)
        for sub in submissions:
            if sub["review_status"] == "pending":
                review_result = await ai_model.review(sub)
                api_ai_review(sub["submission_id"], review_result)
```

#### Plan B2: 人工审核
在 WebUI 中显示待审核列表，管理员手工点击"通过/拒绝"按钮。

---

## 总结

| 我负责的部分 | 做了什么 |
|------------|--------|
| ✅ API 接口 | 定义了 5 个 AI 相关的 API 端点 |
| ✅ 审核逻辑 | `/ai/review` 能正确处理审核和加分 |
| ✅ 提示词 | 给 AI 清晰的指导（`api_ai_prompt`） |
| ✅ 数据模型 | 提交记录包含所有必要信息 |

| 场景 | AstrBot / 用户 / 插件需要做什么 |
|------|---------------------------|
| **Plan A：自动工具调用**（理想情况）| ❓ AstrBot 需要配置 Tool/Skill 来自动触发 |
| **Plan B0：对话式审核**（仅对话） | ✅ 插件添加 `/blindbox review` 命令；用户在群里确认；插件检测到"同意"后自动调用 API |
| **Plan B1：定时任务审核** | ✅ 需要一个后台定时脚本定期调用 `/ai/review` API |
| **Plan B2：WebUI 人工审核** | ✅ 用户在管理页面手工点击"通过/拒绝"按钮 |

---

## 建议

1. **现在最实用**（如果只能对话）：采用 Plan B0（对话式审核）
   - AI 在群里分析和给出意见
   - 用户确认后自动记录和加分
   - 零依赖，立即可用 ✓

2. **其次推荐**：Plan B2（WebUI 人工审核）
   - 在管理页面看待审核列表
   - 点击按钮完成审核
   - 不需要和 AI 对话

3. **如果 AstrBot 支持工具调用**：使用 Plan A（自动工具调用）
   - 最自动化
   - 需要配置 copilot_instructions.md

4. **最后选择**：Plan B1（定时任务）
   - 需要编写后台脚本
   - 依赖额外的运行时支持

---

**核心观点**：我写的是"**工具**"和"**接口**"，具体"**谁来用、怎么用**"取决于 AstrBot 框架的支持程度；如果没有 Tool/Skill 或定时任务，这些接口不会自己跑起来。

---

## ✅ 验证清单

按这个顺序验证，最容易判断问题到底出在插件、AI 工具调用，还是 AstrBot 的自动触发层。

### 1. 先验证读接口是否正常

- [ ] `GET /astrbot_plugin_blindbox/ai/prompt` 能返回系统提示词
- [ ] `GET /astrbot_plugin_blindbox/ai/groups` 能返回小组列表
- [ ] `GET /astrbot_plugin_blindbox/ai/context?group_no=<序号>` 能返回指定小组上下文
- [ ] `GET /astrbot_plugin_blindbox/ai/submissions?group_no=<序号>` 能返回待审核提交记录

通过标准：
- 返回 JSON 正常
- `pending_submission_count` 与实际待审核记录一致
- `current_task`、`submission_count` 等字段有值且符合当前小组状态

### 2. 再验证写回接口是否正常

- [ ] 找到一条真实存在的提交，记录它的 `group_no` 和 `submission_id`
- [ ] 手工调用 `POST /astrbot_plugin_blindbox/ai/review`
- [ ] 传入 `verdict=approved` 或 `verdict=rejected`
- [ ] 重新调用 `GET /astrbot_plugin_blindbox/ai/submissions?group_no=<序号>` 检查结果

通过标准：
- 该提交的 `review_status` 发生变化
- `reviewer`、`reviewed_at`、`review_reason` 被写入
- 如果是通过，`awarded_points` 和小组 `score_total` 会更新

### 3. 最后验证自动触发是否正常

- [ ] 发出一条 `/blindbox submit <说明>`
- [ ] 观察日志中是否随后出现对 `ai/prompt`、`ai/context`、`ai/submissions`、`ai/review` 的调用
- [ ] 如果只看到“已提交任务材料，等待 AI 审核”，但没有后续 AI 调用，说明自动触发没有接上

通过标准：
- 提交后能在日志中看到 AI 处理链路被触发
- 最终有一条提交被自动审核并写回状态

### 4. 常见失败点

- [ ] 提交成功但没有自动审核：AstrBot 没有配置 Tool/Skill 或定时任务
- [ ] AI 试图调用 shell 工具：工具配置错误，或提示词没有约束住模型
- [ ] `ai/review` 调用失败：请求体缺少 `group_no`、`submission_id` 或 `verdict`
- [ ] 查询到的上下文为空：小组没有抽取任务，或上下文参数传错

### 5. 最小手工验证顺序

如果你只想快速确认系统是否可用，按这个顺序就够了：

1. 调 `GET /ai/prompt`
2. 调 `GET /ai/context?group_no=<序号>`
3. 调 `GET /ai/submissions?group_no=<序号>`
4. 调 `POST /ai/review`
5. 再调 `GET /ai/submissions?group_no=<序号>` 核对写回结果

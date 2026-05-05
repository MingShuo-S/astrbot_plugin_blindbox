# AI 调用机制详解

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

但是，**这些接口谁来调用、什么时候调用**，取决于 AstrBot 框架。

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

有两个 Plan B：

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

| AstrBot 框架负责的部分 | 需要做什么 |
|-------------------|--------|
| ❓ 调用触发 | 检测到提交时，激活 AI 处理 |
| ❓ Tool 系统 | 让 AI 知道有哪些 API 可用 |
| ❓ 指令配置 | 从 copilot_instructions.md 加载审核指南 |
| ❓ 自动执行 | AI 决定后自动调用相应的 API |

---

## 建议

1. **现在**：这个系统的 API 和审核逻辑已经准备好了，
    但自动触发仍然依赖 AstrBot 的 Tool/Skill 调用或定时任务
   - API 接口完整
   - 审核逻辑完善
   - 提示词清晰

2. **后续**：当 AstrBot 支持 Tool 调用，或你补上定时任务后：
   - 在 `copilot_instructions.md` 中添加我提供的配置
    - AI 可以按配置开始审核
   - 零代码改动 ✓

3. **暂时**：如果需要立即使用审核流程：
   - 用 Plan B1（定时任务）
   - 或 Plan B2（人工审核）
   - 都很简单

---

**核心观点**：我写的是"**工具**"和"**接口**"，具体"**谁来用、怎么用**"取决于 AstrBot 框架的支持程度；如果没有 Tool/Skill 或定时任务，这些接口不会自己跑起来。

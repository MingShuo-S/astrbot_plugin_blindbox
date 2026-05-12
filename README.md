# astrbot_plugin_blindbox

这是一个面向南京大学行知×开甲学习小组的 AstrBot「抽奖盲盒」插件，任务列表可以直接在 AstrBot WebUI 里编辑。

> **👉 新手看这里**：
> - [GUIDE.md](GUIDE.md) - 日常使用指南（非常容易理解）
> - [AI_INTEGRATION.md](AI_INTEGRATION.md) - 技术细节（给开发者看）

## 结构

- `main.py`: 插件入口，包含 `Star` 子类和抽取指令，任务内容从配置读取。
- `metadata.yaml`: 插件元数据，AstrBot 会依据它识别插件信息。
- `_conf_schema.json`: 插件配置 schema，任务列表与活动说明都可以在 WebUI 里直接修改。
- `pages/management/`: BlindBox 小组管理页，可以在 WebUI 里直接创建、添加、移除、解散小组，也可以转让组长。
- `requirements.txt`: 插件依赖占位文件。
- `skills/`: 可选的插件内置 Skills 目录。

## 指令

- `/blindbox`：随机抽取盲盒任务（显示 3 个选项，回复 1/2/3 选择）。
- `/blindbox <分类名称>`：按盲盒清单中的分类名称抽取任务。
- `/blindbox 全部`：从全部任务中随机抽取。
- `/blindbox group create <序号> <组名> [QQ号...]`：新建小组并可同时加入成员。
- `/blindbox group add <序号> <QQ号...>`：给已有小组继续添加成员。
- `/blindbox group remove <序号> <QQ号...>`：从小组移除成员。
- `/blindbox group transfer <序号> <新组长QQ>`：转让组长身份。
- `/blindbox group request-dissolve <序号>`：组长申请解散小组。
- `/blindbox group request-cancel <序号>`：组长取消解散申请。
- `/blindbox submit <任务说明>`：成员提交任务材料，等待 AI 审核。
- 在群里提交材料：仅通过命令 `/blindbox submit <任务说明>` 提交，命令会自动识别消息中的文字与图片并创建待审核记录。
- 在群里直接 @ 机器人不会触发提交。
- `/blindbox group info <序号>`：查看小组信息和本周抽到的任务。
- `/blindbox group list`：查看所有小组。
- `/blindbox me`：查询当前 QQ 号所属小组。
- `/blindbox redraw [分类]`：对当前成员所属小组重抽本周任务。

## 抽取流程（更新于 v0.7.0）

### 每周限制机制

**每小组每周只能抽取 1 次盲盒任务**。当满足以下任一条件时，才能抽取新任务：

1. **任务已完成**：提交的任务已经过 AI 审核（无论通过还是拒绝）
2. **任务已超期**：距离抽取时刻已超过 7 天

### 选择流程

1. 小组成员执行 `/blindbox` 命令
2. 机器人显示 **3 个任务选项**
3. 小组成员回复 `1`、`2` 或 `3` 来选择对应的任务
4. 机器人确认选择并记录该任务

### 任务时效性

- 每个任务从**选定时刻**开始有效期为 **7 天**
- 7 天内需要完成并提交
- 提交后等待 AI 审核
- 审核完成（通过或拒绝）后可以抽取下一个任务
- 7 天未提交也可以重新抽取

### 任务不重复

同一小组的每次抽取都会保证与上一次的任务不同，避免连续抽到相同的任务。

## 任务方向

插件内置了五类任务：以智增慧、以体强身、以德润心、以美立美、以劳励行。每个任务都会附带一个建议积分，用于后续兑换奖品或评优。

## 配置方式

在 AstrBot WebUI 的插件配置里，可以直接编辑 `任务列表`，对每条任务修改分类、内容、分值和启用状态，也可以修改活动说明文本。这样后续新增或调整盲盒内容时，不需要再手动上传插件文件。

## 小组规则

- 每个 QQ 号只能属于一个小组。
- 创建时的第一个 QQ 号默认是组长。
- 只有组长和本人才能对某个 QQ 号执行 add/remove。
- 组长可以把组长身份转让给同组成员。
- 组长可以在群内申请或取消解散；WebUI 管理页可以直接解散小组。
- WebUI 管理页支持从成员列表里转让组长。
- 每个小组每周只会保留一个盲盒任务。
- 如果本周已经选过任务且未完成，再次执行抽取会被拒绝；需要更换时使用 `/blindbox redraw`（强制重新抽取）。
- 当群消息到来时，插件会根据发送者 QQ 号自动识别所属小组并记录到日志。

## AI 接口

- `GET /astrbot_plugin_blindbox/ai/context?group_no=...`：返回某个小组的成员、累计积分、本周任务和提交状态。
- `GET /astrbot_plugin_blindbox/ai/groups`：返回所有小组的 AI 视图。
- `GET /astrbot_plugin_blindbox/ai/submissions?group_no=...`：读取某个小组的提交记录。
- `GET /astrbot_plugin_blindbox/ai/prompt`：返回给 AI 的系统提示词，包含插件功能说明和审核指南。
- `POST /astrbot_plugin_blindbox/ai/review`：写入 AI 审核结果，并在通过时自动加分。
- `POST /astrbot_plugin_blindbox/submit`：写入一条待审核提交记录，供 AI 后续处理。
- `POST /astrbot_plugin_blindbox/group/export-submissions`：导出某个小组的提交记录和上下文，方便核实。
- `POST /astrbot_plugin_blindbox/group/export-submissions-all-csv`：直接下载所有小组的提交记录 CSV，适合人工复核和表格整理，Excel 可直接打开。
- `GET /astrbot_plugin_blindbox/group/export-csv`：导出所有小组列表为 CSV 格式（序号、组名、组长、成员）。
- `POST /astrbot_plugin_blindbox/group/import-csv`：从 CSV 导入小组列表，可覆盖已有配置。

## 数据存储

当前插件主要保存两类数据：

1. **小组配置与抽取状态**：保存在 AstrBot 的 KV 状态里，包括 `groups`、`member_to_group`、`draws` 和 `pending_selections`
2. **小组提交/打卡记录**：按小组单独保存为 JSON 文件，路径是 `data/plugins/astrbot_plugin_blindbox/submissions/group_<序号>.json`

每条提交记录通常包含这些信息：

- 提交 ID
- 小组序号和小组名
- 提交人 QQ
- 提交文字材料
- 图片链接和图片元信息
- 提交来源
- 周次和任务快照
- 审核状态、审核意见、审核人、审核时间
- 已发放积分和是否已应用到小组积分

## 小组配置管理

### 导出和导入流程

1. **导出**：调用 `GET /astrbot_plugin_blindbox/group/export-csv`，会返回 CSV 文件内容
2. **本地修改**：下载 CSV 后在本地用 Excel / Google Sheets 修改
3. **导入**：调用 `POST /astrbot_plugin_blindbox/group/import-csv`，上传修改后的 CSV
4. **结果**：系统自动更新所有小组和成员映射

**CSV 格式**（示例）：
```
序号,组名,组长QQ,成员QQ列表
1,小组一,A001,"A001,A002,A003"
2,小组二,B001,"B001,B002,B003"
```

**注意**：
- 序号、组名、组长 QQ 为必填项
- 成员 QQ 列表用逗号分隔
- 组长 QQ 必须在成员列表中
- 导入时会覆盖同序号的小组
- 其他未在 CSV 中的小组保持不变

## AI 集成

本插件提供了完整的 AI 集成接口，Bot 可以：

1. **调用提示词 API** 获取系统上下文，了解插件功能和审核规则
2. **通过 API 读取待审核的提交记录**，每条记录都包含提交人、材料、任务快照等信息
3. **基于任务要求进行审核**，写入审核结果（通过/拒绝）和积分调整
4. **自动更新小组积分**，通过认可的提交自动加分

提交记录会同时保留文字说明、图片链接、提交人、关联任务快照和审核状态，方便后续由 AI 或人工复核。

## AI 审核的工作流程

### 如何实现自动审核

本插件已经提供了所有必要的 API 接口。要让 AI **自动调用这些接口进行审核**，需要在 AstrBot 的配置中设置审核 Skill 或 Tool。

**两种方式**：

#### 方式1：使用 AstrBot 内置的 AI 能力配置
- AstrBot 本身支持配置 AI 能力和 Tool 调用
- 可以通过 `copilot_instructions.md` 或在 WebUI 中配置 AI Tools，让 AI 知道如何调用这些接口
- 配置后，AI 会在检测到新提交时自动调用审核接口

#### 方式2：编写自定义 Skill（如果需要）
创建一个 `skills/auto_review.py`：

```python
@skill("自动审核提交")
async def auto_review_submissions(group_no: str):
    """定期检查待审核的提交，并调用 AI 进行审核"""
    # 获取待审核提交
    submissions = get_pending_submissions(group_no)
    
    for submission in submissions:
        # 调用 AI API 获取建议
        ai_review = await call_ai_review(submission)
        
        # 保存审核结果
        save_review_result(submission, ai_review)
```

### API 调用时序图

```
提交材料流程：
成员提交 → /blindbox submit (API) → 数据保存
         ↓
AI 检测 → 先用 GET /ai/context?sender_qq=... 或 GET /ai/groups 定位小组，再 GET /ai/submissions?group_no=... (查询待审核)
         ↓
AI 审核 → GET /ai/prompt (获取审核指南)
  → GET /ai/context?group_no=... (获取小组信息)
         ↓
审核决定 → POST /ai/review (写入审核结果)
         ↓
自动加分 → 小组积分更新 ✓
```

### 配置建议

**推荐配置 AI 提示词**（在 copilot_instructions.md）：

```
## BlindBox 插件审核指南

你需要定期审核学习小组的盲盒任务提交。

调用以下 API：
1. GET /astrbot_plugin_blindbox/group/export-csv - 查看小组列表
2. GET /astrbot_plugin_blindbox/ai/context?sender_qq=<QQ号> - 先定位小组
3. GET /astrbot_plugin_blindbox/ai/submissions?group_no=<序号> - 查看某组待审核提交
4. GET /astrbot_plugin_blindbox/ai/prompt - 获取完整的审核指南
5. POST /astrbot_plugin_blindbox/ai/review - 写入审核结果

审核步骤：
1. 查询待审核的提交记录
2. 根据提示词中的审核标准判断
3. 调用 AI review API 写入结果（通过/拒绝）
4. 系统自动更新积分
```

---

**注意**：本插件的 AI 部分需要 AstrBot 本身支持 Tool 调用或 AI 能力配置。如果 AstrBot 还不支持这些，可以：
- 暂时手工审核（通过 WebUI 或 API）
- 或者等待 AstrBot 升级支持该功能

## 使用

将整个目录放到 AstrBot 的 `data/plugins/astrbot_plugin_blindbox` 下，然后在 AstrBot WebUI 中重载插件即可。

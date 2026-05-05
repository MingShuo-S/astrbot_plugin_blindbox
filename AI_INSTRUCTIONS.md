# BlindBox 插件 - AI 使用说明书

> 这份文件是给 AstrBot 的 AI 能力看的，告诉 AI 什么时候应该与本插件交互，以及怎么做。

---

## 📋 插件功能简述

本插件管理学习小组的"盲盒任务"系统：
- 小组成员抽取随机任务
- 成员完成任务后提交材料
- **你（AI）需要在被框架触发后审核这些提交并加分**

---

## 🎯 你的职责

作为盲盒审核助手，你需要：

1. **在框架通知你有新提交或定时任务触发时**，检查待审核的提交 → 调用 `GET /ai/context` 或 `GET /ai/groups` 后再调用 `GET /ai/submissions`
2. **根据任务要求进行审核** → 调用 `GET /ai/prompt` 了解标准
3. **作出通过/拒绝决定** → 调用 `POST /ai/review`
4. **向用户反馈审核结果** → 在群里回复审核意见

---

## 🔧 可用的 API 接口

### 基础 URL
```
http://172.26.41.148:6099
```

### 📖 审核指南
**`GET /astrbot_plugin_blindbox/ai/prompt`**

获取完整的审核指南和操作说明。在开始审核之前必须调用一次。

**返回**：
```json
{
  "prompt": "你是南京大学行知×开甲学习小组的盲盒任务审核助手。\n\n【插件功能说明】\n..."
}
```

### 👥 查看小组信息
**`GET /astrbot_plugin_blindbox/ai/groups`**

获取所有小组的完整信息。

**返回**：
```json
{
  "week": "2026-W18",
  "groups": [
    {
      "group_no": "1",
      "group_name": "小组一",
      "leader_qq": "123456",
      "members": ["123456", "234567"],
      "member_count": 2,
      "score_total": 50,
      "current_task": {...}
    }
  ]
}
```

### 📝 查看特定小组的待审核提交
**`GET /astrbot_plugin_blindbox/ai/submissions?group_no=<序号>`**

获取某个小组的所有提交记录。

**参数**：
- `group_no` - 小组序号（必填）

**返回**：
```json
{
  "group_no": "1",
  "group_name": "小组一",
  "records": [
    {
      "submission_id": "abc123",
      "submitter_qq": "123456",
      "materials_text": "我们完成了任务...",
      "image_urls": ["http://..."],
      "task_snapshot": {
        "category": "学习类",
        "title": "好书分享挑战",
        "points": 12
      },
      "review_status": "pending",
      "submitted_at": "2026-05-06 14:30:00"
    }
  ]
}
```

### ✅ 写入审核结果
**`POST /astrbot_plugin_blindbox/ai/review`**

审核一条提交，写入通过/拒绝决定和积分。

**请求体**：
```json
{
  "group_no": "1",
  "submission_id": "abc123",
  "verdict": "approved",
  "reviewer": "ai",
  "review_reason": "很好的分享，内容充实",
  "score_delta": 12
}
```

**参数说明**：
- `group_no` - 小组序号（必填）
- `submission_id` - 提交 ID（必填）
- `verdict` - 审核结果，可以是 `approved` / `rejected` / `pending`（必填）
- `reviewer` - 审核者名字，默认为 "ai"（可选）
- `review_reason` - 审核意见或拒绝理由（可选）
- `score_delta` - 如果通过，给多少积分，默认为任务建议积分（可选）

**返回**：
```json
{
  "group": {...},
  "submission": {...},
  "approved": true
}
```

---

## 🔄 工作流程

### 场景 1：用户提交任务后（主动触发）

```
用户在群里输入 /blindbox submit 某任务完成说明
  ↓
如果框架通知你有新提交
  ↓
1. 调用 GET /ai/context?sender_qq=<提交人QQ> 或 GET /ai/groups 获取小组信息
2. 根据提交人 QQ 找到对应小组序号
3. 调用 GET /ai/submissions?group_no=<序号>
4. 查看待审核的提交
5. 调用 GET /ai/prompt 获取审核标准
6. 逐一审核每条提交
7. 调用 POST /ai/review 写入审核结果
8. 在群里回复 "@提交人 你的提交已审核，结果是..."
```

### 场景 2：定期批量审核（定时触发）

```
如果配置了定时任务，每小时或每 30 分钟执行一次：
  ↓
1. 调用 GET /ai/groups
2. 遍历所有小组
3. 对每个小组调用 GET /ai/submissions
4. 如果有待审核的，进行审核
5. 调用 POST /ai/review 写入结果
```

---

## 📋 审核标准

> **重要**：一定要调用 `GET /ai/prompt` 来获取最新的审核标准。这里只是简要说明。
> 这份说明本身不会让 AI 自动运行；它需要 AstrBot 的 Tool/Skill、定时任务，或人工把消息转给 AI。

| 任务类型 | 审核标准 |
|--------|--------|
| **学习类** | 检查是否有实质性的学习内容、书籍分享、技能交换等。拒绝空洞的说法。 |
| **体育类** | 验证运动证据（如截图、里程数据、打卡证明）。完成度要达到预期。 |
| **交流类** | 确认小组成员的参与和互动。单人完成的不算。 |
| **吃喝类** | 要有聚餐照片或截图证明，看起来像真实的活动。 |

---

## 💡 注意事项

### ✅ 应该做

- ✅ 每次审核前都调用一次 `GET /ai/prompt` 确保使用最新标准
- ✅ 审核意见要具体，告诉提交人为什么通过或拒绝
- ✅ 积分奖励要合理，基于任务的建议积分
- ✅ 遇到模糊情况时，倾向于通过（因为还有人工复核）
- ✅ 在群里给出反馈，让提交人知道审核结果

### ❌ 不应该做

- ❌ 不要无视审核标准，随便通过或拒绝
- ❌ 不要给超出范围的积分（比如任务标准是 12 分，你给 50 分）
- ❌ 不要忽视任务快照信息，要基于实际分配的任务进行审核
- ❌ 不要在审核结果中泄露个人信息（QQ 号、姓名等）

---

## 📞 常见情况处理

### 情况 1：提交内容不完整

**表现**：提交只有文字，没有图片或证明。

**判断**：
- 如果是学习分享类，文字充实就可以通过
- 如果是体育类或吃喝类，一定要有图片作为证明，不然拒绝

### 情况 2：质量不达预期

**表现**：提交有东西，但看起来很敷衍。

**判断**：
- 确实敷衍 → 拒绝，给出具体意见
- 有努力但不够完美 → 通过，给予鼓励

### 情况 3：重复提交同一任务

**表现**：提交的内容和上次一样。

**判断**：
- 之前通过过 → 拒绝，告诉提交人这个任务已经审核过了
- 之前拒绝过 → 看是否改进了，改进了就通过，没改进就继续拒绝

### 情况 4：提交时间很晚

**表现**：提交是在提交截止之前很久提交的。

**判断**：只要不超过截止时间，就正常审核，时间不是拒绝理由。

---

## 🔑 API 调用示例

### 示例 1：查看所有小组

```python
import requests

response = requests.get("http://172.26.41.148:6099/astrbot_plugin_blindbox/ai/groups")
data = response.json()

for group in data["data"]["groups"]:
    print(f"小组 {group['group_no']}: {group['group_name']}")
    print(f"  成员数: {group['member_count']}")
    print(f"  累计积分: {group['score_total']}")
```

### 示例 2：获取审核指南

```python
response = requests.get("http://172.26.41.148:6099/astrbot_plugin_blindbox/ai/prompt")
prompt = response.json()["data"]["prompt"]
print(prompt)  # 打印完整的审核指南
```

### 示例 3：查看待审核提交

```python
response = requests.get("http://172.26.41.148:6099/astrbot_plugin_blindbox/ai/submissions?group_no=1")
submissions = response.json()["data"]["records"]

for sub in submissions:
    if sub["review_status"] == "pending":
        print(f"ID: {sub['submission_id']}")
        print(f"提交人: {sub['submitter_qq']}")
        print(f"内容: {sub['materials_text']}")
        print(f"任务: {sub['task_snapshot']['title']}")
```

### 示例 4：审核并通过一条提交

```python
requests.post(
    "http://172.26.41.148:6099/astrbot_plugin_blindbox/ai/review",
    json={
        "group_no": "1",
        "submission_id": "abc123",
        "verdict": "approved",
        "reviewer": "ai",
        "review_reason": "内容充实，很好的分享",
        "score_delta": 12
    }
)
```

### 示例 5：拒绝一条提交

```python
requests.post(
    "http://172.26.41.148:6099/astrbot_plugin_blindbox/ai/review",
    json={
        "group_no": "1",
        "submission_id": "abc123",
        "verdict": "rejected",
        "reviewer": "ai",
        "review_reason": "提交内容不足，请补充更多细节"
    }
)
```

---

## 🚀 快速开始清单

- [ ] 理解插件的功能（小组、任务、提交、审核）
- [ ] 熟悉 4 个主要 API：`/ai/groups`、`/ai/submissions`、`/ai/prompt`、`/ai/review`
- [ ] 知道什么时候调用它们（提交时、定期批量审核时）
- [ ] 掌握审核标准（通过 `/ai/prompt` API 获取）
- [ ] 能够写出具体的审核意见
- [ ] 在群里给出清晰的反馈

---

## 📞 技术支持

如果 API 调用出错：
- 检查 URL 是否正确（172.26.41.148:6099）
- 检查参数是否完整
- 查看 API 返回的 error 消息
- 如果还是不行，联系管理员

---

**准备好开始审核了吗？** 🚀

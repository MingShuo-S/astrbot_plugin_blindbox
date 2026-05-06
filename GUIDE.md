# BlindBox 盲盒任务系统 - 使用指南

> 这份指南是给大家日常使用时看的，不涉及技术细节。

## 📱 参与者指南（小组成员）

### 1. 抽取任务

在群里输入命令即可抽取任务：

```
/blindbox
```

系统会随机给你一个任务。

**按分类抽取**（可选）：
- `/blindbox 学习` - 只要学习类任务
- `/blindbox 体育` - 只要体育类任务
- `/blindbox 交流` - 只要交流类任务
- `/blindbox 吃喝` - 只要吃喝类任务

**注意事项**：
- ⚠️ 同一周最多可以抽 **3 次**
- ⚠️ 每次抽到的任务都**不会重复**
- 📊 抽取时会显示 `(本批次第 X/3 次抽取)` 提示

### 2. 查看小组信息

```
/blindbox me
```

查看自己属于哪个小组，以及小组的详细信息。

### 3. 提交任务材料

完成任务后，在群里提交：

```
/blindbox submit 这是我的任务完成证明...
```

**可以包含**：
- 文字说明
- 图片（自动上传）
- 任何相关证明

**审核流程**：
1. 你提交材料 → 
2. AI 审核判断是否满足任务要求 → 
3. 通过则获得积分 ✓

---

## 👨‍💼 组长指南（小组长）

### 基本操作

**查看小组列表**：
```
/blindbox group list
```

**查看某个小组详情**：
```
/blindbox group info <序号>
```
比如：`/blindbox group info 1`

**添加成员**：
```
/blindbox group add <序号> <QQ号1> <QQ号2> ...
```
比如：`/blindbox group add 1 123456789 987654321`

**移除成员**：
```
/blindbox group remove <序号> <QQ号>
```

**转让组长**：
```
/blindbox group transfer <序号> <新组长QQ>
```

**重抽本周任务**（如果不满意）：
```
/blindbox redraw
```

---

## 🔧 管理员指南（配置小组名单）

### 场景
需要修改小组名单时（添加/移除/调整小组成员）。

### 方法：导出 → 修改 → 导入

#### 第一步：导出现有小组名单

获取一个链接，下载小组列表（CSV 文件）：

**访问这个地址**（需要替换成你的服务器地址）：
```
http://172.26.41.148:6099/astrbot_plugin_blindbox/group/export-csv
```

- 如果本地运行，通常就是 `http://localhost:6099`
- 如果在服务器上，替换成实际服务器地址

**你会看到一个 JSON，里面有 `csv` 字段**：
```json
{
  "success": true,
  "data": {
    "csv": "序号,组名,组长QQ,成员QQ列表\n1,小组一,A001,A001,A002,A003\n...",
    "filename": "blindbox_groups.csv"
  }
}
```

复制 `csv` 字段的内容，粘贴到文本编辑器，**保存为 `groups.csv`**。

#### 第二步：用 Excel 修改

1. 用 Excel / Google Sheets 打开 `groups.csv`
2. 修改各行的内容：

| 序号 | 组名 | 组长QQ | 成员QQ列表 |
|------|------|--------|-----------|
| 1 | 小组一 | 111111 | 111111,222222,333333 |
| 2 | 小组二 | 444444 | 444444,555555 |

**修改规则**：
- 序号、组名、组长 QQ 都**不能为空**
- 组长 QQ **必须在成员列表中**
- 成员 QQ 用**逗号**分隔，不要有空格

3. **保存为 CSV 格式**

#### 第三步：导入修改

打开这个网址进行导入：

```
http://172.26.41.148:6099/astrbot_plugin_blindbox/group/import-csv
```

这是一个 POST 接口。如果你不懂 POST，可以这样做：

**最简单的方法：用 Python 脚本**

1. 在电脑上创建一个文件 `upload.py`：

```python
import requests
import json

# 修改这里为你的服务器地址
BASE_URL = "http://172.26.41.148:6099"

# 读取修改后的 CSV 文件
with open("groups.csv", "r", encoding="utf-8") as f:
    csv_content = f.read()

# 上传到服务器
response = requests.post(
    f"{BASE_URL}/astrbot_plugin_blindbox/group/import-csv",
    json={"csv": csv_content}
)

# 显示结果
result = response.json()
print(json.dumps(result, indent=2, ensure_ascii=False))
```

2. 在命令行运行：
```bash
python upload.py
```

3. 看到 `success: true` 就说明成功了 ✓

**或者用 curl 命令**（如果你熟悉命令行）：

```bash
# 假设 CSV 文件在当前目录
csv_content=$(cat groups.csv | jq -R -s '.')
curl -X POST "http://172.26.41.148:6099/astrbot_plugin_blindbox/group/import-csv" \
  -H "Content-Type: application/json" \
  -d "{\"csv\": $csv_content}"
```

### 小组打卡记录总导出

如果你要人工复核所有小组的提交/打卡情况，直接导出总表就可以了。这个文件是 CSV 格式，Excel 可以直接打开。

**接口地址**：
```
http://172.26.41.148:6099/astrbot_plugin_blindbox/group/export-submissions-all-csv
```

**请求方式**：`POST`

**返回结果**：直接下载 CSV 文件，不再返回 JSON。

**导出的 CSV 包含**：
- 小组序号 / 小组名 / 组长 QQ
- 提交 ID
- 提交人 QQ
- 提交文字材料
- 图片链接
- 任务快照（类别、标题、积分）
- 审核状态、审核意见、审核人、审核时间
- 已发放积分和是否已应用

---

### 提交记录（全部导出/导入）模板

导出全部提交会生成包含以下列的 CSV（示例表头）：

```
group_no,group_name,leader_qq,submission_id,submitter_qq,source,week,review_status,review_reason,reviewer,reviewed_at,awarded_points,score_applied,submitted_at,task_category,task_title,task_points,image_urls,materials_text,task_snapshot_json
```

示例行：

```
1,小组一,100,abcd1234,100,manual,2026-W18,pending,,,,0,False,2026-05-06,"学习类","自习地点抽签",10,"http://...","小组提交材料","{}"
```

导入说明：
- 导入前请确保 CSV 的表头与上方模板一致（`group_no` 和 `submission_id` 为必需列）。
- 导入会按 `group_no` 将行分组，并覆盖对应小组的提交文件（`data/plugins/astrbot_plugin_blindbox/submissions/group_<no>.json`）。
- 当前导入仅支持 CSV；如需导入 `.xlsx`，请先另存为 CSV 后再导入。


## 🤖 AI 审核机制

### 工作流程

1. **成员提交任务** → `/blindbox submit <说明>`
2. **AI 自动审核** → 
   - 检查是否满足任务要求
   - 查看提交的材料（文字 + 图片）
   - 作出决定（通过 / 拒绝）
3. **自动加分** → 通过的提交自动添加积分到小组

### AI 怎么知道该干什么？

系统给 AI 提供了完整的**审核指南**：
- 每个任务的要求
- 各类别任务的审核标准
- 小组和成员信息

AI 会根据这些自动判断 ✓

---

## ❓ 常见问题

**Q: 为什么同一周只能抽 3 次？**
A: 为了保证任务的多样性和公平性，避免某个小组反复抽同一类型的任务。

**Q: 如果第一次抽的任务太难，能换吗？**
A: 可以！组长在本周内任何时候都可以用 `/blindbox redraw` 重抽，会覆盖上一个任务。但还是受 3 次的限制。

**Q: AI 审核会不会出错？**
A: 会。所以如果你觉得审核有问题，可以找管理员人工复核。

**Q: 提交后多久能审核？**
A: 看 AI 的繁忙程度，通常很快（分钟级别）。

**Q: 如何查看审核结果？**
A: 目前需要管理员查看，会在后续完善 UI。

---

## 📞 技术支持

- 群里有问题直接问
- 出 Bug 把截图发给管理员

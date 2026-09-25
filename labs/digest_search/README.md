# 日报检索台

离线查询 World Pulse 的结构化日报。它与脉络时间线不同：可组合中文/英文短语、日期、类别、地区和世界/AI栏目筛选，并把命中事件的来源 URL 一起返回，便于为滚动回顾或更正核查定位原始记录。只读本地 JSON，不联网、不修改归档。

## 用法

在仓库根目录运行：

```powershell
python labs/digest_search/digest_search.py data/2026/09 --query 挪威 --since 2026-09-20 --through 2026-09-25
python labs/digest_search/digest_search.py data/2026/09 --query 代理 --query 评测 --section ai-frontier
python labs/digest_search/digest_search.py data/2026/09 --category economy --region Canada --limit 10
```

重复 `--query` 表示所有短语都要在事件标题、摘要、重要性或不确定性字段中命中；匹配不区分大小写，但不做分词、同义词或跨语言翻译。日期边界包含当日。输出 UTF-8 JSON，包含匹配总数、返回数、覆盖日期、事件元数据与可用来源信息；默认最多返回50条，可用 `--limit` 调整。

## 测试

```powershell
python -m unittest tests.test_digest_search -v
python labs/digest-search/digest_search.py data/2026/09 --query 代理 --section ai-frontier
```

## 无障碍与限制

- 纯文本终端输入/输出，不依赖颜色、鼠标、动画或交互式焦点；命令行参数可由键盘操作，JSON 字段稳定且适合屏幕阅读器顺序朗读。
- 输入可为单个日报 JSON 或目录；递归扫描时排除聚合索引 `index.json`。结果按日期、事件 ID 稳定排序。
- 查询只搜索每条事件的标题、摘要、重要性与不确定性；不搜索来源网页或 AI 扩展元数据，不代表事实验证或来源仍可访问。
- 地区标签为仓库中的自由文本，使用完整标签精确匹配；事件内容与标签不会自动标准化。
- 未匹配到内容时返回空 `entries` 和 `matched_count: 0`；无效日期、损坏 JSON 或必需字段缺失会报错，不会静默跳过。

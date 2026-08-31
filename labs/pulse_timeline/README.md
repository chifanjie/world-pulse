# 脉络时间线生成器

这是一个离线 CLI 小工具：读取 `data/YYYY/MM/YYYY-MM-DD.json`，把每条日报事件压缩为可按日期和事件 ID 排序的时间线。它适合在滚动回顾前快速查看一个主题类别跨日期的变化，不会联网，也不会修改日报。

## 使用

在仓库根目录运行：

```powershell
python labs/pulse_timeline/pulse_timeline.py data/2026/08 --category technology
```

也可以传入多个日报文件：

```powershell
python labs/pulse_timeline/pulse_timeline.py data/2026/08/2026-08-27.json data/2026/08/2026-08-31.json
```

输出是 UTF-8 JSON：`count` 为事件数，`dates` 为覆盖日期，`entries` 包含 `date`、`id`、`title`、`category` 和排序后的 `regions`。目录扫描会忽略 `data/index.json`。

## 测试

```powershell
python -m unittest tests.test_pulse_timeline -v
```

## 无障碍检查

- 输出只使用普通 UTF-8 文本/JSON，不依赖颜色、图标、动画或鼠标操作。
- 字段名和事件顺序稳定，屏幕阅读器或重排文本的终端可以按顺序朗读。
- CLI 的键盘交互由终端负责；没有隐藏焦点、时限或需要拖拽的控件。

## 限制

- 工具不判断事件是否重复、不验证来源 URL，也不替代 `tools/validate_digest.py`。
- `--category` 是精确匹配，不做同义词或跨语言归一化。
- 输入文件必须符合日报 JSON 的基本 `date`、`items`、`id`、`title`、`category` 和 `regions` 字段；它不会从网页补齐缺失事实。

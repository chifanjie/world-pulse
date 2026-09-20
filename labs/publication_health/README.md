# 发布健康检查

离线检查指定日期窗口的缺期、Markdown 配对和实际生成日期。用于发现“每天运行却长期没有发布”的情况，保留历史补发的真实生成时间。

在仓库根目录运行（Python 3.10+，仅标准库）：

```powershell
python -m labs.publication_health.publication_health --since 2026-09-02 --through 2026-09-20
```

不传 `--through` 时使用北京时间今天。完整窗口返回退出码 0；缺期或坏数据返回 1；参数错误返回 2。JSON 输出包含具体缺期日期、最近一期和发生晚发的归档日期；实际生成时间保留在源 JSON 中。未来生成时间不会计为已完成，不能把旧日报当作今天的完成状态。工具只读，不创建占位日报或更改归档日期。

无障碍：纯文本 JSON，无颜色依赖、无需鼠标，字段可由屏幕阅读器或脚本读取；`--help` 可查看参数。测试包含月底跨月、空目录、缺 Markdown、时区换日与晚发布情形。

限制：本工具检查本地归档覆盖，不判定新闻真伪，也不证明文件已经推送。仍需运行 `tools/validate_digest.py` 做完整结构验证，并用 `tools/safe_sync.py push --expected-remote <本轮开始时的main提交>` 核对 GitHub 远端提交。

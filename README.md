# 京东App全网热销筛选 Skill

通过已登录安卓设备的京东原生App读取指定SKU的命名“全网热销”档位。默认筛选 **100万+纳入，1000万+排除**，输入多少处理多少；保留未命中、未知、标题变化和用户确认排除记录。

入口：[SKILL.md](skills/jd-app-hot-sales/SKILL.md)。将整个 `skills/jd-app-hot-sales` 文件夹复制到 `~/.codex/skills/`，使用 `$jd-app-hot-sales`，不要仅复制SKILL.md。

本人完成USB授权和京东登录，普通App全站搜索输入完整商品链接。标题不一致不归属页面指标，验证即停止保存断点。没有验证码自动化或精确销量接口。

命令见[运行说明](skills/jd-app-hot-sales/references/runbook.md)。Python依赖固定，Excel使用Codex bundled Artifact Tool。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

仓库仅含通用代码、合成测试和无私人数据的验收报告。输入、结果、界面证据、设备信息和环境不纳入Git。真实手机验收范围见 [VALIDATION.md](VALIDATION.md)。

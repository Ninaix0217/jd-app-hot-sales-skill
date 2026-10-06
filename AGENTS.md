# 工作约定

- 通用代码和合成测试可入库；用户SKU表、JSONL结果、手机serial、完整UI、账号和认证数据不得提交。
- 手机动作只有一个worker；保持前台和身份保护，验证由本人处理。不要为通过测试关闭保护或绕过平台加载限制。
- 修改流程后运行 `python -m unittest discover -s tests -v`。设备与页面版本必须实际观察；离线检查不能替代手机复现。
- 更新Skill时同步 `skills/jd-app-hot-sales/SKILL.md` 和受影响运行说明，验收事实记 `VALIDATION.md`，不复制私人证据。
- 默认处理全量输入，样本限制只用于明确测试；按展示档位筛选，不宣称精确销量区间。

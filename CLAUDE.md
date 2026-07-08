# CLAUDE.md

先读 `AGENTS.md`(环境事实:Base/账号/红线/工具,Codex 与 Claude Code 通用)。

**开发 or 运营?** 先读 `docs/运行模式.md` 分清两种 loop:
- **开发 loop**(改系统):`/loop 继续完善 guanyun-workspace…`,目标=`check_p*.sh` 全绿 + `ar_check` SCORE=100 + 开发 issue 清零,盯 测试红/schema 漂移/成熟度回归 三个 monitor。
- **运营 loop**(跑内容工厂=上线):`bash scripts/install_cron.sh --install` 在运营库 `ZhzJbf`(当前 .env 即对,`TEST_MODE=1` 本身就是上线态)。**"上线"≠切生产库 `N9IVbi`(焊死不碰)**,就是在测试库挂 cron。

架构与方法论:`docs/架构与方法论.md`;领域词汇:`CONTEXT.md`。

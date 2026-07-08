# guanyun-workspace
观云内容运营 Workspace:环境事实+推进器+契约——飞书当脸,CLI agent 当手,Bitable 当账本,git skills 当大脑

进门先读 `AGENTS.md`(环境事实);搭建计划在 `docs/PLAN.md`;P1 验收 `bash scripts/check_p1.sh`。

## .mcp.json 说明

`.mcp.json` 当前是**最小合法骨架**(`{"mcpServers": {}}`——JSON 不支持注释,说明写在这里):

- 后续在此声明 MCP 连接器,**密钥一律按名引用 env**(如 `"env": {"TIKHUB_API_KEY": "${TIKHUB_API_KEY}"}`),真值只存本地 `.env`。
- 计划接入:`xiaohongshu-mcp`(本地 `:18060`,采集/发布小红书,发布硬门=人确认+AI 声明)等;接入时机见 `docs/PLAN.md` P3-P6。

## 技能安装

```bash
bash scripts/install_skills.sh   # 按 skills.lock.json symlink 17 个技能进 skills/(不入库,幂等)
```

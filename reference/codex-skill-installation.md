# Codex Skill 多电脑安装说明

本文说明如何把本项目内的 Codex Skill 安装到不同电脑，适用于多人协作、换电脑、重新部署 Codex 环境。

## 目录关系

- 项目内 Skill 源文件：`skills/jewelry-on-hand-workflow`
- 安装脚本：`scripts/install_codex_skills.py`
- Codex 运行时读取位置：`$CODEX_HOME/skills`
- 未设置 `CODEX_HOME` 时，Codex 通常使用当前用户目录下的 `.codex/skills`

项目仓库是唯一可信来源。不要手工维护多份不同版本的 `jewelry-on-hand-workflow`。

## 新电脑安装步骤

1. 克隆或复制完整项目仓库。
2. 在项目根目录运行：

```powershell
python scripts/install_codex_skills.py --force
```

3. 如果这台电脑使用自定义 Codex home：

```powershell
python scripts/install_codex_skills.py --codex-home "D:\codex-home" --force
```

4. 重启 Codex，让新 Skill 生效。
5. 在 Codex 中打开本项目根目录；Skill 会从当前工作区定位 `src/jewelry_on_hand`、`reference` 和 `skills/aireiter-image-generation`。

## 安装更多项目内 Skill

默认只安装 `jewelry-on-hand-workflow`。如果需要同时安装项目内的 AIReiter Skill：

```powershell
python scripts/install_codex_skills.py --skill jewelry-on-hand-workflow --skill aireiter-image-generation --force
```

安装脚本会跳过 `references/config.json`，避免把本机 API key 当作共享 Skill 文件复制。新电脑需要自行设置 `AIREITER_API_KEY` 或创建本机私有配置。

## 可移植性规则

- Skill 文档不得写死某个用户目录、盘符或电脑名。
- Skill 只能把安装目录用于读取自己的 `references/` 和 `scripts/`。
- 业务代码、参考图、测试和运行产物都从当前项目工作区读取。
- 修改 Skill 后，先更新 `skills/jewelry-on-hand-workflow`，再运行安装脚本同步到本机 Codex。
- 对外协作只提交项目内 Skill；不要提交 `$CODEX_HOME/skills` 下的个人副本。

## 验证

在项目根目录运行：

```powershell
python -m pytest tests/test_skill_portability.py -q
```

如果通过，说明项目内 Skill 可被复制到指定 `CODEX_HOME`，且没有保留当前电脑的硬编码路径。

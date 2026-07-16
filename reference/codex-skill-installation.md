# Codex 珠宝工作流 Skill 多电脑安装说明

本文说明如何把本项目内的 Codex Skill 安装到不同电脑，适用于多人协作、换电脑、重新部署 Codex 环境。

## 目录关系

- 上手图工作流：`skills/jewelry-on-hand-workflow`
- 产品主图工作流：`skills/jewelry-product-hero-workflow`
- 产品主图生成依赖：`skills/aireiter-image-generation`
- 安装脚本：`scripts/install_codex_skills.py`
- Codex 运行时读取位置：`$CODEX_HOME/skills`
- 未设置 `CODEX_HOME` 时，Codex 通常使用当前用户目录下的 `.codex/skills`

项目仓库是唯一可信来源。不要手工维护运行时目录中的 Skill 副本。

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
5. 在 Codex 中打开本项目根目录。上手图工作流会定位项目业务代码；产品主图工作流的核心契约和脚本可独立运行，项目 `reference/product-hero-workflow.md` 仅提供扩展维护说明。
6. 产品主图需要飞书 `lark-wiki`、`lark-base`、`lark-drive` 能力；缺少时必须先安装或启用飞书连接器，不得用本地猜测数据替代。

## 默认与选择性安装

默认命令同时安装：

- `jewelry-on-hand-workflow`
- `jewelry-product-hero-workflow`
- `aireiter-image-generation`

这样清洁 `CODEX_HOME` 中的产品主图工作流不会缺少 AIReiter 生成依赖。若只需其中一个，可显式指定：

```powershell
python scripts/install_codex_skills.py --skill jewelry-product-hero-workflow --force
```

选择性安装产品主图 Skill 时，调用方必须另行保证 `$aireiter-image-generation` 可用。推荐仍使用默认安装。

安装脚本会跳过所有 Skill 的 `__pycache__`、`.pyc`、`.pyo`，并跳过 AIReiter 的 `references/config.json`，避免复制本机 API key。新电脑需要自行设置 `AIREITER_API_KEY` 或创建本机私有配置。

## 可移植性规则

- Skill 文档不得写死某个用户目录、盘符或电脑名。
- Skill 只能把安装目录用于读取自己的文档和 `scripts/`；产品主图 Skill 不把项目外 `reference/` 当作运行时硬依赖。
- 业务代码、参考图、测试和运行产物都从当前项目工作区读取。
- 修改任一 Skill 后，先更新项目内源目录，再运行安装脚本同步到本机 Codex。
- 对外协作只提交项目内 Skill；不要提交 `$CODEX_HOME/skills` 下的个人副本。

## 验证

在项目根目录运行：

```powershell
python -m pytest tests/test_skill_portability.py tests/test_product_hero_skill_portability.py -q
```

如果通过，说明三个默认 Skill 可复制到指定 `CODEX_HOME`，不会携带缓存或 AIReiter 私钥配置，并且产品主图核心模块可在项目目录之外导入。

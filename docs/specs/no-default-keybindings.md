# no-default-keybindings

关联：[GitHub Issue #11](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/11)
（本需求取代 [fix-issue-6-keymap](fix-issue-6-keymap.md) 中「保留 `super+shift+m`」的结论）

## 背景

包根目录的三个 `Default (OSX/Windows/Linux).sublime-keymap` 随包默认启用了
这些快捷键：

- `super+shift+m` / `ctrl+shift+m` → `markdown_preview_enhanced_toggle`
- `super+shift+v` / `ctrl+shift+v` → `markdown_preview_enhanced_paste_as_markdown`

前者覆盖 ST 内置的 **Expand Selection to Brackets**，后者覆盖 ST 内置的
**Paste and Indent**。社区约定：包不应随发行默认占用用户按键，更不能
shadow ST 内置快捷键。issue #6 已因 `super+shift+p` 撤销过一条，本需求要求
彻底不启用默认 keybindings。

## 目标

- 包不再随发行默认启用任何快捷键。
- 保留示例键位供用户自行开启（以注释形式，不生效）。
- 文档（README 双语）说明「默认无键位 + 如何自行绑定」。
- 命令面板提供入口，打开 keybindings 视图且左栏展示示例。

## 行为约定

- 用一个**无平台后缀**的包根 `Default.sublime-keymap` 承载全平台示例，内容
  **全部注释掉**，不启用任何键。这样：
  - ST 会自动加载该 keymap 文件，但解析结果为空绑定，不 shadow 任何内置键。
  - `edit_settings` 的 `base_file` 能打开它（`edit_settings` 只能打开包根资源，
    放子目录会 `res://` 加载失败——cite：ST 官方 `Preferences: Key Bindings`
    与 LSP 包的 `Preferences: LSP Key Bindings` 均将 keymap 置于包根）。
  - 注释示例用 `super+alt+m` / `ctrl+alt+m` 等**不冲突**键位，并注明 macOS 用
    `super`、Windows/Linux 用 `ctrl`。
- `Default.sublime-commands` 增加**一条**编辑命令，使用内置 `edit_settings`：
  - `base_file` = `${packages}/MarkdownPreviewEnhanced/Default.sublime-keymap`
    （只读，左栏，展示注释示例）
  - `user_file` = `${packages}/User/Default ($platform).sublime-keymap`
    （可编辑，右栏，保存即生效；`$platform` 展开为 `OSX/Windows/Linux`）
  - `default` = `"[\n\t$0\n]\n"`（User 文件首次为空数组 + 光标落点）
- README（`README.md` 与 `README_zh.md`）Usage 改为「命令面板运行 / 自行绑定」，
  并新增「Key bindings / 快捷键」小节：默认无键位、如何用命令面板命令或
  `Preferences → Key Bindings` 自行绑定、给出不冲突的推荐键位。

## 验收标准

- 包根 `Default.sublime-keymap` 不含任何**启用**的键绑定（全注释）。
- 包根不再存在 `Default (OSX/Windows/Linux).sublime-keymap`、`keybindings/`
  子目录。
- `Default.sublime-commands` 含一条 key bindings 编辑命令，`base_file` 指向
  `Default.sublime-keymap`、`user_file` 指向 `User/Default ($platform).sublime-keymap`。
- README 双语无「默认快捷键」表述，改为自行绑定说明。
- `python3 tests/run_all.py` 全绿。
- 命令面板该命令可打开双栏视图（左栏示例、右栏 User keymap），保存生效。

## 不做项

- 不新增 settings 开关配置快捷键（沿用 issue #6 结论，用 User 层 keymap）。
- 不为包重新分配新的默认键位。
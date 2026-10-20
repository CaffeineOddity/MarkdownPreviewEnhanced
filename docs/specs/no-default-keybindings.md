# no-default-keybindings

关联：[GitHub Issue #11](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/11)
（本需求取代 [fix-issue-6-keymap](fix-issue-6-keymap.md) 中「保留 `super+shift+m`」的结论）

## 背景

包根目录的三个 `Default (OSX/Windows/Linux).sublime-keymap` 随包默认启用了
这些快捷键：

- `super+shift+m` / `ctrl+shift+m` → `markdown_preview_enhanced_toggle`
- `super+shift+v` / `ctrl+shift+v` → `markdown_preview_enhanced_paste_as_markdown`

前者覆盖 ST 内置的 **Expand Selection to Brackets**，后者覆盖 ST 内置的
**Paste and Indent**。社区的约定是：包不应随发行默认占用用户按键，更不能
shadow ST 内置快捷键。issue #6 已经因为 `super+shift+p` 污染命令面板撤销过
一条，这次要求彻底不 ship 默认 keybindings。

## 目标

- 包不再随发行默认启用任何快捷键。
- 保留示例键位，供用户自行开启；用户默认不受任何键位影响。
- 文档（README 双语）说明「默认无键位 + 如何自行绑定」。
- 命令面板提供入口，打开 keybindings 视图且左栏展示示例文件。

## 行为约定

- 包根目录下不再存在 `Default (OSX).sublime-keymap`、
  `Default (Windows).sublime-keymap`、`Default (Linux).sublime-keymap`
  （删除，而非清空留空文件）。避免 `super+shift+m` / `super+shift+v`
  等键位被默认启用。
- 示例键位放到 `keybindings/` 子目录（不在包根，ST 不会自动加载，仅作参考）：
  - `keybindings/Default (OSX).sublime-keymap`
  - `keybindings/Default (Windows).sublime-keymap`
  - `keybindings/Default (Linux).sublime-keymap`
  每个示例用注释标出「这是示例，复制到 User/Default (<平台>).sublime-keymap
  才会生效」，并注明所选键会覆盖哪个 ST 内置键，提示可按需改键。
- `Default.sublime-commands` 增加三条编辑命令（macOS / Windows / Linux 各一），
  使用内置 `edit_settings`：
  - `base_file` = 对应平台的 `keybindings/Default (平台).sublime-keymap`（只读，左栏）
  - `user_file` = `${packages}/User/Default (平台).sublime-keymap`（可编辑，右栏）
  - `default` = `"[]\n"`（User 文件首次打开为空数组）
  三条命令必须显式写死平台后缀大小写（`OSX` / `Windows` / `Linux`），
  不能用 `${platform}`（该变量展开为小写 `osx/linux`，在 Linux 上大小写敏感
  会导致 User keymap 不生效）。
- README（`README.md` 与 `README_zh.md`）：
  - Usage 中不再写「按 `Cmd+Shift+M` / `Cmd+Shift+V` 打开」，改为「从命令面板
    运行，或自行绑定快捷键」。
  - 新增「Key bindings / 快捷键」小节，给出三平台示例 JSON，并说明默认无
    键位、如何用命令面板命令或 `Preferences → Key Bindings` 自行绑定。

## 验收标准

- 包根目录不含任何 `Default (*).sublime-keymap`。
- `keybindings/` 子目录含三平台示例文件，内容正确且含覆盖提示注释。
- `Default.sublime-commands` 含三条 key bindings 编辑命令，`user_file`
  指向 `User/Default (OSX|Windows|Linux).sublime-keymap`。
- README 双语不再出现「默认 `Cmd+Shift+M` / `Ctrl+Shift+V`」的表述为唯一入口，
  改为自行绑定的说明。
- `python3 tests/run_all.py` 全绿（本改动不涉及渲染逻辑，回归即可）。

## 不做项

- 不新增 settings 开关来配置快捷键（沿用 issue #6 结论，用 User 层 keymap）。
- 不为包重新分配新的默认键位。
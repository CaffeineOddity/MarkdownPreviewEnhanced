# fix-issue-6-keymap

关联：[GitHub Issue #6](https://github.com/CaffeineOddity/MarkdownPreviewEnhanced/issues/6)

## 背景

`Default (OSX).sublime-keymap` 把 `super+shift+p` 绑定到
`markdown_preview_enhanced_presentation`，覆盖了用户已习惯的
`super+shift+p`（ST 打开命令面板时的 overlay 类操作），被用户报告为
"污染了系统原来的 shift+cmd+p 命令"。

## 目标

- 默认快捷键只保留一个：`super+shift+m` → `markdown_preview_enhanced_toggle`
- 其余功能（close / export / presentation / refresh）不再默认绑键，
  仍可通过命令面板（`Default.sublime-commands` 已有条目）使用
- Windows / Linux 同样只保留 `ctrl+shift+m`

## 验收标准

- 三个平台 keymap 文件各只剩一条绑定
- `Default.sublime-commands` 条目不变（命令面板可触达全部命令）
- README 中如有快捷键说明需同步（提及的其它快捷键改为"可通过 User keymap 自行绑定"）

## 不做项

- 不新增 settings 开关来配置快捷键（用户可用 User 层 keymap 自定义）

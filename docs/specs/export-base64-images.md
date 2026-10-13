# 导出 HTML 图片 base64 内嵌

## 背景与目标

Export HTML 已是 standalone 导出（CSS/JS 内联、KaTeX CSS 内嵌离线可用），但本
地图片经 `rewrite_image_srcs(mode="file")` 改写为 `file://` **绝对路径**。导出
的单文件在本机能打开，拷到其他机器或发给别人后图片全部失效。

本需求：导出 HTML 时把本地图片读出并内嵌为 `data:` base64 URI，使导出文件成为
真正意义「单文件自包含」，可任意拷贝分发。

## 设计

- 新设置项 `embed_images`（默认 `true`）：
  - `true`：导出时本地图片（`file://` 与相对路径解析结果）读出转
    `data:<mime>;base64,...` 内嵌；读取失败的图片保持 `file://` 原样并在导出
    warnings 中提示。
  - `false`：维持现状（`file://` 绝对路径）。
- 实现位置：`mpe_core/html_builder.py` 新增 `embed_local_images(body_html)`，
  在 `build_export_html` 内对 `body_html` 后处理；仅在导出链路生效
  （`build_preview_shell` 实时预览不受影响）。
- MIME 推断：按扩展名映射（png/jpg/jpeg/gif/webp/svg/bmp/ico/avif），未知
  扩展名回落 `application/octet-stream`。
- 远程图片（http/https）不下载、不内嵌，保持原样——离线分发场景下用户应先
  用「Paste as markdown + paste_download_images」把远程图本地化。
- 仅作用于 `<img src>`；CSS `url()`、`<source>`、`poster` 等暂不处理。

## 行为约定

- 导出 PDF / PNG 复用同一渲染链路（`_render_standalone`），同样受益：headless
  Chrome 渲染时图片来自 data URI，不再依赖源文件路径。
- 大图片内嵌会显著增大 HTML 体积（base64 约膨胀 33%）；这是该功能的固有代价，
  由用户通过 `embed_images: false` 关闭。
- 路径含 URL 编码字符（空格、中文）时先 `unquote` 再读文件。

## 验收标准

1. 导出含相对路径本地图片的 md，产物 HTML 在无源文件目录的机器上打开图片正常。
2. `embed_images: false` 时行为与旧版一致（`file://` 路径）。
3. 图片文件不存在时导出不失败，warnings 提示，src 保持 `file://`。
4. 已有 tests smoke：相对图片、绝对路径图片、远程 URL、data: URI 各一例。

## 已知边界与不做项

- 不内嵌远程图片、不处理 CSS 内 `url()`。
- 不做图片压缩或缩放。

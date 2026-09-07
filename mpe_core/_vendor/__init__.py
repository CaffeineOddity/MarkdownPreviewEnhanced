"""Vendored third-party libraries (all permissive licenses).

- markdownify 1.2.3 (MIT) — HTML → Markdown 转换
- bs4 / beautifulsoup4 4.15.0 (MIT) — markdownify 的 HTML 解析依赖
- soupsieve 2.9.2 (MIT) — bs4 依赖
- typing_extensions 4.16.0 (PSF-2.0) — bs4 在 py3.8 需要

各库许可全文见 licenses/。six 依赖已从 markdownify 移除（仅 str() 两处）。
bs4 缺 lxml/html5lib 时自动降级到内置 HTMLParser，无需其他二进制依赖。

导入方式：mpe_core.vendor 先把本目录加到 sys.path，再 `import markdownify`。
"""

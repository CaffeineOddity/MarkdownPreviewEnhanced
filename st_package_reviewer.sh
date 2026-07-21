#!/bin/sh
# 本地 Package Control 合规检测脚本
# 用法: sh st_package_reviewer.sh
# 依赖: pip3 install --user st-package-reviewer

# 切到脚本所在目录(包根目录),保证从任意位置调用都检测当前包
cd "$(dirname "$0")" || exit 1

# 运行官方评审器 st_package_reviewer,透传退出码
# 退出码:0=无问题;1=包检测有 failure;2=仓库检测有 failure;4=无法下载仓库
exec st_package_reviewer .

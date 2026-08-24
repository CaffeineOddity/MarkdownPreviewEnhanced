"""Unified logging for MarkdownPreviewEnhanced.

DEBUG 为真时打印 debug 级日志(本地开发默认)。
release.sh 打 tag 前会把本文件改成 DEBUG 为假,发版包保持安静。
发版安装仍可在 User 设置里加 ``"debug": true`` 打开详细日志。
"""
import datetime
import os

# release.sh 发版时改为 False;master 开发保持 True。
DEBUG = True

_PREFIX = "[MarkdownPreviewEnhanced]"
_PATH = None


def set_path(path):
    """设置 debug.log 路径。None 则下次写入时再解析。"""
    global _PATH
    _PATH = path


def _want_debug():
    try:
        import sublime
        s = sublime.load_settings("MarkdownPreviewEnhanced.sublime-settings")
        if s.has("debug"):
            return bool(s.get("debug"))
    except Exception:
        pass
    return DEBUG


def _file_path():
    if _PATH:
        return _PATH
    try:
        from . import config
        return config.debug_log_path()
    except Exception:
        return os.path.expanduser("~/Downloads/MarkdownPreviewEnhanced/debug.log")


def _write_file(msg):
    try:
        path = _file_path()
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (ts, msg))
    except Exception:
        pass


def _emit(msg):
    line = "%s %s" % (_PREFIX, msg)
    print(line)
    _write_file(msg)


def info(msg):
    """始终打印:启动、关预览、失败等少量关键信息。"""
    _emit(msg)


def error(msg):
    """始终打印:失败与异常。"""
    _emit(msg)


def debug(msg):
    """详细跟踪;发版默认关闭。"""
    if _want_debug():
        _emit(msg)

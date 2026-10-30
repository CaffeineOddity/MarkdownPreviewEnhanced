"""Unified logging for MarkdownPreviewEnhanced.

所有写入 ST 控制台的输出都由 DEBUG 门控:发版包 (DEBUG=False) 不打印任何东西,
日志只写文件;开发态 (master DEBUG=True) 或用户在设置里开 ``"debug": true`` 时才打印。
release.sh 打 tag 前会把本文件改成 DEBUG 为假。
"""
import datetime
import os

# release.sh 发版时改为 False;master 开发保持 True。
DEBUG = False
DEBUG_PATH="~/Downloads/MarkdownPreviewEnhanced/debug.log"
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
    """DEBUG=True 时统一写到 ~/Downloads/MarkdownPreviewEnhanced/debug.log,
    方便开发期查看。发版时 DEBUG=False,走 config.output_dir() 路径。
    用户设置 "debug": true 时也走 Downloads 路径。
    """
    if _PATH:
        return _PATH
    try:
        if _want_debug():
            return os.path.expanduser(DEBUG_PATH)
    except Exception:
        pass
    try:
        from . import config
        return config.debug_log_path()
    except Exception:
        return os.path.expanduser(DEBUG_PATH)


def clear():
    """Truncate the debug log file (called on plugin_loaded)."""
    try:
        path = _file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("")
    except Exception:
        pass


def _write_file(msg):
    try:
        path = _file_path()
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (ts, msg))
    except Exception:
        if _want_debug():
            print("write_log failed")


def _emit(msg):
    if _want_debug():
        print("%s %s" % (_PREFIX, msg))
    _write_file(msg)


def info(msg):
    """写日志文件;DEBUG 打开时才打印到控制台。"""
    _emit(msg)


def error(msg):
    """写日志文件;DEBUG 打开时才打印到控制台(失败与异常)。"""
    _emit(msg)


def debug(msg):
    """详细跟踪;DEBUG 打开时才写文件并打印。"""
    if _want_debug():
        _emit(msg)

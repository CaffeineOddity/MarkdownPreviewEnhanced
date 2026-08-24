"""Core internals for MarkdownPreviewEnhanced.

These modules live in a subpackage so that Sublime Text does not load each one
as an independent root-level plugin. Only ``MarkdownPreviewEnhanced.py`` at the
package root defines ``sublime_plugin`` entry points; everything else is imported
through this package via relative imports.

``markdown`` and ``pygments`` are *not* vendored here. They are provided by the
``mdpopups`` dependency (see ``dependencies.json``), which vendors both
correctly without polluting the bare top-level ``sys.modules`` namespace. We
import them as ``from mdpopups import markdown`` / ``mdpopups.markdown.*`` and
never touch ``sys.modules`` ourselves (see issue #2).
"""

import os

# Absolute path to the MarkdownPreviewEnhanced package root (the directory
# that contains ``assets/`` and this ``mpe_core/`` subpackage).
#
# NOTE: when installed via Package Control this path points *inside* a
# ``.sublime-package`` zip archive and cannot be used with ``open()``. Use the
# ``mpe_core.assets`` helpers (which go through ``sublime.load_resource``) for
# reading any shipped file.
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

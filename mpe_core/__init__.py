"""Core internals for MarkdownPreviewEnhanced.

These modules live in a subpackage so that Sublime Text does not load each one
as an independent root-level plugin. Only ``MarkdownPreviewEnhanced.py`` at the
package root defines ``sublime_plugin`` entry points; everything else is imported
through this package via relative imports.

Vendored ``markdown`` / ``pygments`` live under this package but are also
registered under their bare top-level names so absolute imports
(``importlib.import_module("markdown.extensions.fenced_code")``,
``from pygments.lexers import ...``) resolve to the *same* module objects.

Important Sublime Text detail
-----------------------------
Under ST the package is a real Python package. This module's ``__name__`` is
``MarkdownPreviewEnhanced.mpe_core`` (not bare ``mpe_core``). Canon targets for
vendor aliases must therefore be derived from ``__name__``, e.g.
``MarkdownPreviewEnhanced.mpe_core.markdown``. Offline tests that put the zip on
``sys.path`` and ``import mpe_core`` still work because then ``__name__`` is
just ``mpe_core``.

Loading must work for both unpacked Packages/ and zipped .sublime-package
installs, so module loading always goes through the normal import system
(including zipimport). We never open source files by reconstructed paths.
"""

import os
import sys

# Absolute path to the MarkdownPreviewEnhanced package root (the directory
# that contains ``assets/`` and this ``mpe_core/`` subpackage).
#
# NOTE: when installed via Package Control this path points *inside* a
# ``.sublime-package`` zip archive and cannot be used with ``open()``. Use the
# ``mpe_core.assets`` helpers (which go through ``sublime.load_resource``) for
# reading any shipped file.
PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Fully-qualified name of *this* package under whatever loader is active.
# ST: "MarkdownPreviewEnhanced.mpe_core"  |  offline: "mpe_core"
_CORE_NAME = __name__


class _NoExecLoader(object):
    """Return an already-imported module without re-executing it."""

    def __init__(self, module):
        self.module = module

    def create_module(self, spec):
        return self.module

    def exec_module(self, module):
        return None

    # Python 3.3 (Sublime legacy plugin host) load_module protocol.
    def load_module(self, fullname):
        sys.modules[fullname] = self.module
        return self.module

    def __repr__(self):
        name = getattr(self.module, "__name__", "?")
        return "_NoExecLoader(%r)" % name


class _PackageAliasFinder(object):
    """Map bare ``markdown`` / ``pygments`` names onto this package's vendored copies.

    Canon modules are loaded with the normal import machinery (works under
    zipimport and under Sublime's ``PackageName.mpe_core.*`` naming). Alias
    names are bound to the *same* module objects so ``isinstance`` stays valid.

    Only the *alias* names are intercepted — never the canon
    ``…mpe_core.markdown`` tree — so we do not fight PathFinder/zipimport.
    """

    def __init__(self, alias_prefix, target_prefix):
        self.alias_prefix = alias_prefix
        self.target_prefix = target_prefix

    def _matches(self, fullname):
        return fullname == self.alias_prefix or fullname.startswith(
            self.alias_prefix + "."
        )

    def _canon_name(self, alias_fullname):
        return self.target_prefix + alias_fullname[len(self.alias_prefix):]

    def _bind(self, alias_fullname, mod):
        """Point both names at ``mod`` (and re-sync after automodule swaps)."""
        if mod is None:
            return None
        canon = self._canon_name(alias_fullname)
        # Prefer whatever is currently registered under the canon name —
        # pygments' ``_automodule`` replaces ``sys.modules[__name__]``.
        final = sys.modules.get(canon) or mod
        sys.modules[alias_fullname] = final
        sys.modules[canon] = final
        return final

    def _ensure_canon(self, canon_name):
        """Load ``canon_name`` via normal import; return the module or None."""
        mod = sys.modules.get(canon_name)
        if mod is not None:
            return mod
        try:
            __import__(canon_name, fromlist=["__name__"])
        except Exception:
            return None
        # Re-read: automodule may have replaced the entry during import.
        return sys.modules.get(canon_name)

    def _resolve(self, fullname):
        if not self._matches(fullname):
            return None
        existing = sys.modules.get(fullname)
        if existing is not None:
            return self._bind(fullname, existing)
        canon = self._canon_name(fullname)
        mod = self._ensure_canon(canon)
        return self._bind(fullname, mod)

    def find_spec(self, fullname, path, target=None):
        mod = self._resolve(fullname)
        if mod is None:
            return None
        try:
            import importlib.util
        except ImportError:  # Python 3.3
            return None
        is_pkg = hasattr(mod, "__path__")
        # Do NOT set origin / submodule_search_locations: that can push
        # importlib down a SourceFileLoader re-exec path for mid-load parents
        # and split module identity (see docs/issue.md).
        return importlib.util.spec_from_loader(
            fullname, _NoExecLoader(mod), is_package=is_pkg,
        )

    def find_module(self, fullname, path=None):
        """Python 3.3 finder protocol."""
        mod = self._resolve(fullname)
        if mod is None:
            return None
        return _NoExecLoader(mod)


def _mirror_package(alias, target):
    """Map every loaded ``target`` / ``target.*`` module onto ``alias`` / ``alias.*``."""
    src_dot = target + "."
    alias_dot = alias + "."
    for name in list(sys.modules.keys()):
        mod = sys.modules.get(name)
        if mod is None:
            continue
        if name == target:
            sys.modules[alias] = mod
        elif name.startswith(src_dot):
            sys.modules[alias + name[len(target):]] = mod
        elif name == alias:
            if target not in sys.modules:
                sys.modules[target] = mod
        elif name.startswith(alias_dot):
            canon = target + name[len(alias):]
            if canon not in sys.modules:
                sys.modules[canon] = mod


# Submodules codehilite / md_renderer import by absolute name.
_PYGMENTS_EAGER = (
    "util",
    "token",
    "filter",
    "filters",
    "regexopt",
    "plugin",
    "modeline",
    "console",
    "style",
    "styles",
    "lexer",
    "formatter",
    "lexers",
    "formatters",
    "lexers._mapping",
    "formatters._mapping",
    "formatters.html",
)

_MARKDOWN_EAGER = (
    "core",
    "preprocessors",
    "blockprocessors",
    "treeprocessors",
    "inlinepatterns",
    "postprocessors",
    "serializers",
    "util",
    "extensions",
    "extensions.fenced_code",
    "extensions.tables",
    "extensions.attr_list",
    "extensions.nl2br",
    "extensions.toc",
    "extensions.codehilite",
    "extensions.footnotes",
)


def _ensure_and_mirror(alias, target, sub=""):
    """Import a canon submodule (or the package root) and mirror to the alias."""
    if sub:
        canon_name = target + "." + sub
        alias_name = alias + "." + sub
    else:
        canon_name = target
        alias_name = alias

    mod = sys.modules.get(canon_name)
    if mod is None:
        try:
            __import__(canon_name, fromlist=["__name__"])
        except Exception as e:
            # Visible in the Sublime console — silent failure is how this
            # bug stayed hidden under Package Control installs.
            print(
                "[MarkdownPreviewEnhanced] vendor import failed: %s (%s: %s)"
                % (canon_name, type(e).__name__, e)
            )
            return None
        mod = sys.modules.get(canon_name)
    if mod is None:
        return None
    final = sys.modules.get(canon_name) or mod
    sys.modules[canon_name] = final
    sys.modules[alias_name] = final
    return final


def _install_vendor_aliases():
    """Register vendored markdown/pygments under their bare top-level names.

    Targets are ``<this package>.markdown`` / ``.pygments``, where
    ``<this package>`` is ``__name__`` (ST-prefixed or bare).

    **Order matters:** pygments must be registered before markdown. Eager-loading
    markdown pulls in ``extensions.codehilite``, which does
    ``from pygments import highlight`` at import time. If the pygments alias is
    not ready yet, codehilite permanently sets ``pygments = False`` and all
    highlighting becomes plain ``<pre class="codehilite">`` without token spans.
    """
    for alias, subpkg, eager in (
        ("pygments", "pygments", _PYGMENTS_EAGER),
        ("markdown", "markdown", _MARKDOWN_EAGER),
    ):
        target = _CORE_NAME + "." + subpkg

        # Healthy dual registration already present.
        if (
            alias in sys.modules
            and target in sys.modules
            and sys.modules[alias] is sys.modules[target]
        ):
            continue
        # Do not hijack a real third-party install of the bare name.
        if alias in sys.modules and target not in sys.modules:
            alias_file = (getattr(sys.modules[alias], "__file__", None) or "").replace(
                "\\", "/"
            )
            if "/mpe_core/" not in alias_file and ".sublime-package/" not in alias_file:
                continue

        if any(
            isinstance(f, _PackageAliasFinder) and f.alias_prefix == alias
            for f in sys.meta_path
        ):
            continue

        finder = _PackageAliasFinder(alias, target)
        sys.meta_path.insert(0, finder)

        pkg = _ensure_and_mirror(alias, target)
        if pkg is None:
            try:
                sys.meta_path.remove(finder)
            except ValueError:
                pass
            print(
                "[MarkdownPreviewEnhanced] vendor alias NOT installed: %s → %s"
                % (alias, target)
            )
            continue

        for sub in eager:
            _ensure_and_mirror(alias, target, sub)
        _mirror_package(alias, target)


_install_vendor_aliases()

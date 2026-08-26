"""Small helpers for safe ownership checks around MiniMax H3 runtime hooks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PatchStatus:
    state: str  # stock | ours | foreign | compatible
    owner: str
    module: str


def module_is_compatible(module, compatible_modules):
    module = str(module or "")
    for item in compatible_modules or ():
        item = str(item)
        if module == item or module.endswith("." + item) or module.endswith(item):
            return True
    return False


def classify_callable(owner_cls, fn, our_marker, known_external_markers=(),
                      compatible_modules=()):
    """Classify a callable as stock, ours, foreign, or a compatible observer.

    Stock methods live in the same module as their owning class and are not
    wrapped. Runtime wrappers generally move to another module or expose
    ``__wrapped__``. Explicit marker attributes are checked first so known H3
    chaining packs can produce a useful conflict message. Compatible observers
    such as SolAttn Morton wrap PackedLayout without changing H3 layout math
    and may be chained.
    """
    if fn is None:
        return PatchStatus("foreign", "missing callable", "?")

    module = str(getattr(fn, "__module__", "?") or "?")
    if getattr(fn, our_marker, False):
        return PatchStatus("ours", "Herrgotts-H3-Infinite-Continuation-Suite", module)

    for marker, label in known_external_markers:
        if getattr(fn, marker, False):
            return PatchStatus("foreign", label, module)

    if module_is_compatible(module, compatible_modules):
        return PatchStatus("compatible", f"compatible observer from {module}", module)

    if hasattr(fn, "__wrapped__"):
        return PatchStatus("foreign", f"wrapper from {module}", module)

    home = str(getattr(owner_cls, "__module__", "") or "")
    if home and module and module != home:
        return PatchStatus("foreign", f"runtime patch from {module}", module)

    return PatchStatus("stock", "ComfyUI stock", module)

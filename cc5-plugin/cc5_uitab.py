"""
Bring ONE tab of a CC5 tab widget to the front without the mouse: route /ui/tab.

Why (2026-11-19): the "Subdivide" button sits on a page of the Modify panel's tab widget
(objectName qtAttributeRootTab) that was not the front one. click_ui_button refuses hidden buttons (on
purpose) and nothing could switch the tab. The tabs there show icons only, so a tab is named by its
index or its tool tip as well as by its text.

What it does: finds the visible QTabWidget / QTabBar inside a named CC5 window, dialog or dock panel
(optionally the one with objectName tab_widget) and
  * lists it (list_only, or no index / text / tooltip given): objectName, class, current index and
    every tab's index, text, tool tip, enabled and visible state. Read-only, answered at once;
  * or selects exactly one tab with setCurrentIndex() on CC5's main thread (a job, like /ui/click),
    waits wait_ms and returns the index before and after, the labels, a picture of the window and the
    dialogs that are open.
It never presses a button, never answers a dialog and never opens a menu.

What it refuses (nothing changes; the reason comes back as HTTP 400):
  * a window name that matches nothing or more than one window;
  * no visible tab widget, or more than one when tab_widget is not given (the candidates are listed);
    hidden tab widgets never count;
  * an index / text / tooltip that matches no tab or several tabs (the tabs are listed);
  * a disabled or hidden tab;
  * a tab whose text or tool tip contains a cc5_uiclick.DENY_WORDS word or a word of
    cc5_ui.forbidden_reason (the same check as for buttons: cc5_uiclick.deny_reason);
  * any selection while a window that needs a person is open (licence, purchase, login, ...), or
    while a modal window is open that the tab widget is not in (cc5_uiclick.blocking_reason).

The checks live here, in CC5, because any local program can call the bridge: the MCP tool
(select_ui_tab) only forwards the request and shows the answer.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator

import cc5_ui
import cc5_uiclick

DEFAULT_WAIT_MS = 500
MIN_WAIT_MS = cc5_uiclick.MIN_WAIT_MS
MAX_WAIT_MS = cc5_uiclick.MAX_WAIT_MS
SELECT_DELAY_MS = 50                # the switch runs in its own timer callback, like a click
MAX_NAME_CHARS = cc5_uiclick.MAX_NAME_CHARS
MAX_LISTED = cc5_uiclick.MAX_LISTED  # tab widgets named in a list or a refusal
MAX_TABS = 100                      # tabs read from one tab widget
MAX_INDEX = 999
MAX_LABEL_CHARS = 200
ALLOWED_KEYS = frozenset({"window", "tab_widget", "index", "text", "tooltip", "list_only",
                          "wait_ms", "screenshot", "max_width"})
SELECTOR_KEYS = ("index", "text", "tooltip")

_call = cc5_uiclick._call
label_key = cc5_uiclick.label_key


# --- reading ------------------------------------------------------------------------------

def _at(holder: Any, method: str, index: int, default: Any) -> Any:
    """holder.method(index), or the default when this Qt has no such method or it raises."""
    return cc5_ui._safe(lambda: getattr(holder, method)(index), default)


def tab_info(holder: Any, index: int) -> dict[str, Any]:
    """One tab as plain data. isTabVisible is Qt 5.15+: without it a tab counts as visible."""
    info: dict[str, Any] = {
        "index": index,
        "text": cc5_ui.clean_text(_at(holder, "tabText", index, "")).replace("&", "")[:MAX_LABEL_CHARS],
        "tooltip": cc5_ui.clean_text(_at(holder, "tabToolTip", index, ""))[:MAX_LABEL_CHARS],
        "enabled": bool(_at(holder, "isTabEnabled", index, True)),
        "visible": bool(_at(holder, "isTabVisible", index, True)),
    }
    page = _at(holder, "widget", index, None)        # QTabWidget only: the page helps to name an icon-only tab
    page_name = _call(page, "objectName", "") if page is not None else ""
    if page_name:
        info["page"] = str(page_name)[:MAX_LABEL_CHARS]
    return info


def read_tabs(holder: Any) -> list[dict[str, Any]]:
    count = cc5_ui._clamp_int(_call(holder, "count", 0), 0, MAX_TABS, 0)
    return [tab_info(holder, i) for i in range(count)]


def describe_holder(holder: Any) -> dict[str, Any]:
    """A tab widget / tab bar and its tabs, as plain data (read-only)."""
    total = cc5_ui._clamp_int(_call(holder, "count", 0), 0, 1_000_000, 0)
    out: dict[str, Any] = {
        "object_name": _call(holder, "objectName", ""), "class": cc5_ui._class_of(holder),
        "current_index": cc5_ui._clamp_int(_call(holder, "currentIndex", -1), -1, 1_000_000, -1),
        "count": total, "enabled": bool(_call(holder, "isEnabled", True)), "tabs": read_tabs(holder),
    }
    if total > MAX_TABS:
        out["note"] = f"only the first {MAX_TABS} tabs are listed"
    return out


def _tab_desc(tab: dict[str, Any]) -> str:
    bits = [f"{tab['index']}:", f"'{tab['text']}'" if tab["text"] else "(no text)"]
    if tab["tooltip"] and label_key(tab["tooltip"]) != label_key(tab["text"]):
        bits.append(f"tip '{tab['tooltip'][:60]}'")
    if not tab["enabled"]:
        bits.append("(disabled)")
    if not tab["visible"]:
        bits.append("(hidden)")
    return " ".join(bits)


def _tabs_desc(tabs: list[dict[str, Any]]) -> str:
    return ", ".join(_tab_desc(t) for t in tabs[:MAX_LISTED]) or "(no tabs)"


def _holder_desc(holder: Any) -> str:
    name = _call(holder, "objectName", "")
    count = cc5_ui._clamp_int(_call(holder, "count", 0), 0, 1_000_000, 0)
    return (f"[{name}]" if name else "(no objectName)") + f" <{cc5_ui._class_of(holder)}> {count} tab(s)"


# --- matching -----------------------------------------------------------------------------

def holders_in(q: Any, scope: Any) -> list[Any]:
    """Every QTabWidget of `scope`, and every QTabBar that is not the bar of one of those, that
    belongs to scope's own window (not to a child dialog parented to it). Hidden ones included."""
    top = cc5_uiclick._top(scope)
    tab_widget, tab_bar = getattr(q, "QTabWidget", None), getattr(q, "QTabBar", None)
    found: list[Any] = []
    if tab_widget is not None:
        found += cc5_ui._safe(lambda: scope.findChildren(tab_widget), [])
    if tab_bar is not None:
        for bar in cc5_ui._safe(lambda: scope.findChildren(tab_bar), []):
            parent = _call(bar, "parent")
            if tab_widget is not None and parent is not None and isinstance(parent, tab_widget):
                continue                          # a QTabWidget's own bar: the tab widget stands for it
            found.append(bar)
    return [h for h in found if cc5_ui._same_widget(_call(h, "window"), top)]


def find_holders(q: Any, scope: Any, name: str | None) -> tuple[list[Any], int]:
    """(the visible tab widgets / bars, filtered by objectName when given; hidden matches skipped)."""
    matched = [h for h in holders_in(q, scope) if name is None or _call(h, "objectName", "") == name]
    visible = [h for h in matched if _call(h, "isVisible", False)]
    return visible, len(matched) - len(visible)


def find_holder(q: Any, scope: Any, name: str | None) -> tuple[Any | None, str | None]:
    """The one visible tab widget to switch, or the refusal."""
    visible, hidden = find_holders(q, scope, name)
    where = cc5_uiclick._describe_window(scope)
    if len(visible) == 1:
        return visible[0], None
    if not visible:
        if name is None:
            return None, f"no visible tab widget in {where}. Nothing was changed"
        if hidden:
            return None, (f"the tab widget {name!r} in {where} is hidden (not on screen); hidden tab widgets are "
                          "never switched. Bring its panel to the front first")
        others = ", ".join(_holder_desc(h) for h in find_holders(q, scope, None)[0][:MAX_LISTED])
        return None, f"no tab widget with objectName {name!r} in {where}. Visible tab widgets there: {others or '(none)'}"
    listed = ", ".join(_holder_desc(h) for h in visible[:MAX_LISTED])
    hint = ("they share that objectName, so this tool cannot tell them apart" if name is not None
            else "give tab_widget (the objectName of one of them)")
    return None, f"{len(visible)} visible tab widgets in {where}: {listed}. Nothing was changed; {hint}"


def find_tab(holder: Any, p: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """The one tab the request names (by index, text or tooltip) when it may be selected, or the refusal."""
    tabs = read_tabs(holder)
    where = f"the tab widget {_holder_desc(holder)}"
    if p.get("index") is not None:
        what = f"index {p['index']}"
        hits = [t for t in tabs if t["index"] == p["index"]]
    elif p.get("text") is not None:
        what = f"text {p['text']!r}"
        hits = [t for t in tabs if label_key(t["text"]) == label_key(p["text"])]
    else:
        what = f"tooltip {p['tooltip']!r}"
        hits = [t for t in tabs if label_key(t["tooltip"]) == label_key(p["tooltip"])]
    if not hits:
        return None, f"no tab with {what} in {where}. Tabs: {_tabs_desc(tabs)}. Nothing was changed"
    if len(hits) > 1:
        return None, (f"{len(hits)} tabs match {what} in {where}: {_tabs_desc(hits)}. Nothing was changed; "
                      "name the tab by its index")
    tab = hits[0]
    if not _call(holder, "isEnabled", True):
        return None, f"{where} is disabled (greyed out); nothing was changed"
    if not tab["enabled"]:
        return None, f"the tab {_tab_desc(tab)} is disabled (greyed out) and cannot be selected now"
    if not tab["visible"]:
        return None, f"the tab {_tab_desc(tab)} is hidden; hidden tabs are never selected"
    # the full strings are checked, not the shortened ones that are reported
    word = cc5_uiclick.deny_reason(_at(holder, "tabText", tab["index"], ""), _at(holder, "tabToolTip", tab["index"], ""))
    if word:
        return None, (f"refused: the tab {_tab_desc(tab)} mentions '{word}'. Tabs about points, buying, deleting / "
                      "removing, licences, activation, upgrades, credits, subscriptions or payment (and login / "
                      "update / terms / trial) are opened by a person only. Ask the owner")
    return tab, None


# --- arguments ----------------------------------------------------------------------------

def read_args(body: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    """Checked copy of the request body, or the reason it is refused. Unknown keys are refused."""
    p = dict(body or {})
    unknown = sorted(set(p) - ALLOWED_KEYS)
    if unknown:
        return None, f"unknown argument(s) {unknown}; allowed: {sorted(ALLOWED_KEYS)}"
    for key in ("window", "tab_widget", "text", "tooltip"):
        value = p.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_NAME_CHARS:
            return None, f"{key} must be a non-empty string of at most {MAX_NAME_CHARS} characters"
    if p.get("window") is None:
        return None, "window is required: the title (or objectName) of the CC5 window, dialog or panel"
    index = p.get("index")
    if index is not None and (isinstance(index, bool) or not isinstance(index, int) or not 0 <= index <= MAX_INDEX):
        return None, f"index must be a whole number from 0 to {MAX_INDEX} (the first tab is 0)"
    for key in ("screenshot", "list_only"):
        if key in p and not isinstance(p[key], bool):
            return None, f"{key} must be true or false"
    given = [key for key in SELECTOR_KEYS if p.get(key) is not None]
    if len(given) > 1:
        return None, f"give only one of index, text, tooltip (got {given})"
    p["list_only"] = p.get("list_only", False) is True or not given
    p["wait_ms"] = cc5_ui._clamp_int(p.get("wait_ms", DEFAULT_WAIT_MS), MIN_WAIT_MS, MAX_WAIT_MS, DEFAULT_WAIT_MS)
    p["max_width"] = cc5_ui._clamp_int(p.get("max_width", 900), 200, 2400, 900)
    p["screenshot"] = p.get("screenshot", True) is not False
    return p, None


# --- listing (read-only) ------------------------------------------------------------------

def list_tabs(p: dict[str, Any]) -> dict[str, Any]:
    """The visible tab widgets of the window and their tabs. Changes nothing."""
    q = cc5_ui._qt()
    window, error = cc5_uiclick.find_window(q, p["window"])
    if error:
        return {"success": False, "error": error}
    visible, hidden = find_holders(q, window, p.get("tab_widget"))
    out: dict[str, Any] = {"success": True, "listed": True, "window": cc5_uiclick._title(window),
                           "count": len(visible),
                           "tab_widgets": [describe_holder(h) for h in visible[:MAX_LISTED]]}
    if hidden:
        out["hidden_skipped"] = hidden
    return out


# --- selecting (a job) --------------------------------------------------------------------

def resolve(p: dict[str, Any]) -> dict[str, Any]:
    """{"window", "holder", "tab"} for a selection request, or {"error"}."""
    q = cc5_ui._qt()
    blocked = cc5_uiclick.blocking_reason(q)
    if blocked:
        return {"error": blocked}
    window, error = cc5_uiclick.find_window(q, p["window"])
    if error:
        return {"error": error}
    blocked = cc5_uiclick.blocking_reason(q, window)
    if blocked:
        return {"error": blocked}
    holder, error = find_holder(q, window, p.get("tab_widget"))
    if error:
        return {"error": error}
    tab, error = find_tab(holder, p)
    if error:
        return {"error": error}
    return {"window": window, "holder": holder, "tab": tab}


def _current(holder: Any) -> int:
    return cc5_ui._clamp_int(_call(holder, "currentIndex", -1), -1, 1_000_000, -1)


def _select_steps(p: dict[str, Any]) -> Iterator[float]:
    found = resolve(p)                            # again: the window may have changed since the request
    if "error" in found:
        return {"success": False, "error": found["error"]}
    window, holder, tab = found["window"], found["holder"], found["tab"]
    before = _current(holder)
    previous = tab_info(holder, before) if before >= 0 else None
    state: dict[str, Any] = {"ran": False, "returned": False, "error": None}

    def switch() -> None:
        state["ran"] = True
        try:
            holder.setCurrentIndex(tab["index"])
        except Exception as exc:                  # a timer callback must never raise
            state["error"] = f"{type(exc).__name__}: {exc}"
        state["returned"] = True

    cc5_ui._later(SELECT_DELAY_MS, switch)
    yield SELECT_DELAY_MS + p["wait_ms"]
    return _report(p, window, holder, tab, before, previous, state)


def _report(p: dict[str, Any], window: Any, holder: Any, tab: dict[str, Any], before: int,
            previous: dict[str, Any] | None, state: dict[str, Any]) -> dict[str, Any]:
    after = _current(holder)
    out: dict[str, Any] = {
        "success": state["ran"] and state["error"] is None and after == tab["index"],
        "window": cc5_uiclick._title(window),
        "tab_widget": {"object_name": _call(holder, "objectName", ""), "class": cc5_ui._class_of(holder)},
        "index_before": before, "index_after": after, "selected": tab, "previous": previous,
        "tabs": read_tabs(holder), "select_returned": state["returned"], "waited_ms": p["wait_ms"],
    }
    if not state["ran"]:
        out["error"] = "the tab switch did not run (CC5's Qt timer did not fire in time); look before trying again"
    elif state["error"]:
        out["error"] = f"setCurrentIndex raised {state['error']}"
    elif not state["returned"]:
        out["note"] = ("the tab switch has not returned yet: CC5 is showing a window it opened (see dialogs) or is "
                       "still working. Nothing was pressed")
    elif after != tab["index"]:
        out["error"] = (f"asked for tab {tab['index']} but the current tab is {after}: CC5 did not switch "
                        "(or switched back). Nothing else was tried")
    elif before == after:
        out["note"] = "that tab was already the front one"
    cc5_uiclick.add_window_view(out, p, window)
    return out


def ui_tab(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Route /ui/tab: list the tabs of a window's tab widget, or bring ONE tab to the front.

    Body: window (title, case-insensitive, or objectName of a CC5 window / dialog / dock panel;
    required), tab_widget (exact objectName of the QTabWidget / QTabBar; needed when the window shows
    more than one), ONE of index (0-based) | text (exact; ignores case and the & marker) | tooltip
    (exact; ignores case), list_only (default false), wait_ms (after the switch, default 500,
    200-15000), screenshot (default true: PNG of the window and of each open dialog), max_width
    (default 900). With list_only, or with no index / text / tooltip, the reply is the list itself
    (listed=true, tab_widgets; nothing changes, no job). Otherwise a job starts; its result has
    tab_widget, index_before / index_after, selected, previous, tabs, window_open, png_base64 and
    dialogs. Refusals: see the module docstring.
    """
    p, error = read_args(body)
    if error:
        return {"success": False, "error": error}
    if p["list_only"]:
        return list_tabs(p)
    found = resolve(p)
    if "error" in found:
        return {"success": False, "error": found["error"]}
    return cc5_ui.start_job("tab", _select_steps, p, max_seconds=p["wait_ms"] / 1000 + 120)


ROUTES: dict[str, tuple[str, Callable[..., dict[str, Any]]]] = {
    "/ui/tab": ("ui_tab", ui_tab),
}

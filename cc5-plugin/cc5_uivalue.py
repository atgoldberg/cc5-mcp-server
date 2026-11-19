"""
Set the value of ONE input widget of a CC5 window without the mouse or the keyboard: route /ui/value.

Why (2026-11-19): Modify > Character > SubD Levels > Render stayed at 0 after subdividing. The two SubD
boxes are spin boxes with the same objectName (qtSpinBox, inside qtRenderComboSpinBox and
qtPreviewComboSpinBox); click_ui_button presses buttons only, and nothing could type a number or tick
"Activate Expression Wrinkles".

What it does: finds one visible, enabled input widget inside a named CC5 window, dialog or dock panel,
by its exact objectName (and, when several share it, by `ancestor`: the objectName or class of a widget
it sits in), and
  * reports it (read_only): kind, current value, range, step, item list. Read-only, answered at once;
  * or sets it on CC5's main thread (a job, like /ui/click) with the Qt calls that send the usual change
    signals, so CC5 reacts as if a person had changed it, waits wait_ms and returns the value before and
    after, a picture of the window and the dialogs that are open.

    kind      widget                                  value          how it is set
    int       QSpinBox (and subclasses, QSpinBoxEx)   whole number   setValue, then editingFinished
    double    QDoubleSpinBox                          number         setValue, then editingFinished
    spin      any other QAbstractSpinBox with a       number         setProperty("value"), then
              numeric "value" property                               editingFinished
    slider    QSlider / QAbstractSlider               whole number   setSliderDown(True), setSliderPosition,
                                                                     setSliderDown(False) (a drag); setValue
                                                                     when the widget has no such methods
    combo     QComboBox                               item text      setCurrentIndex, then activated /
                                                      (string) or    textActivated
                                                      index (number)
    text      QLineEdit                               string         setText, then textEdited and
                                                                     editingFinished
    check     QCheckBox / QRadioButton                true / false   click() when the state differs
                                                                     (setChecked for a tri-state box)

It never presses a push button, never answers a dialog and never opens a menu.

What it refuses (nothing changes; the reason comes back as HTTP 400):
  * a window name that matches nothing or more than one window;
  * an objectName (with ancestor) that matches no supported input widget or more than one VISIBLE one
    (the candidates are listed with the widgets they sit in); hidden widgets never count;
  * a disabled or read-only widget; the inner text box of a spin box or combo box (name the box itself);
    a password box (it is neither read nor typed into);
  * a value of the wrong type, or OUTSIDE the widget's minimum / maximum: nothing is clamped silently, the
    range is reported; a combo text that matches no item or several, an index that is not there, a
    disabled item; a text longer than the box allows, or one its validator does not accept (the old text
    is put back);
  * a widget whose own text, objectName, tool tip, placeholder or label (a QLabel whose buddy it is, or
    the few QLabels next to it in the same parent), or the combo item to select, has a money or agreement
    word: the same check as for buttons (cc5_uiclick.deny_reason), with the same exact exceptions
    (cc5_uiclick.ALLOWLIST: "Activate Expression Wrinkles" may be ticked);
  * any change while a window about money or an agreement is open, or while a modal window is open that
    the widget is not in (cc5_uiclick.blocking_reason).

What a person typed into a text box is not read back (cc5_uiview has the same rule): its text is returned
only when it is a plain number; otherwise only its length.

The checks live here, in CC5, because any local program can call the bridge: the MCP tool
(set_ui_value) only forwards the request and shows the answer.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable, Iterator

import cc5_ui
import cc5_uiclick

DEFAULT_WAIT_MS = 500
MIN_WAIT_MS = cc5_uiclick.MIN_WAIT_MS
MAX_WAIT_MS = cc5_uiclick.MAX_WAIT_MS
SET_DELAY_MS = 50                   # the change runs in its own timer callback (it may open a window)
MAX_NAME_CHARS = cc5_uiclick.MAX_NAME_CHARS
MAX_TEXT_CHARS = 1024               # a text value
MAX_LISTED = cc5_uiclick.MAX_LISTED
MAX_ITEMS = 200                     # combo items read
MAX_LABEL_CHARS = 200
MAX_NEAR_LABELS = 3                 # QLabels in the same parent count as the widget's labels up to this many
MAX_PATH_DEPTH = 6
ALLOWED_KEYS = frozenset({"window", "object_name", "ancestor", "value", "read_only",
                          "wait_ms", "screenshot", "max_width"})
NUMBER_KINDS = ("int", "double", "spin", "slider")
_PLAIN_NUMBER_RE = re.compile(r"[-+]?\d{1,12}(?:[.,]\d{1,8})?")

_call = cc5_uiclick._call
label_key = cc5_uiclick.label_key


# --- reading ------------------------------------------------------------------------------

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _prop(w: Any, name: str) -> Any:
    """A Qt property by name (works for C++ classes PySide has no wrapper for)."""
    return cc5_ui._safe(lambda: w.property(name))


def kind_of(q: Any, w: Any) -> str | None:
    """Which kind of input a widget is (see the table in the module docstring), or None."""
    if isinstance(w, (q.QCheckBox, q.QRadioButton)):
        return "check"
    if isinstance(w, q.QComboBox):
        return "combo"
    if isinstance(w, q.QDoubleSpinBox):
        return "double"
    if isinstance(w, q.QSpinBox):
        return "int"
    if isinstance(w, q.QAbstractSpinBox):
        return "spin" if _is_number(_prop(w, "value")) else None
    if isinstance(w, q.QAbstractSlider):
        return "slider"
    if isinstance(w, q.QLineEdit):
        return "text"
    return None


def _number(w: Any, kind: str, name: str, default: Any = None) -> Any:
    """value / minimum / maximum / singleStep of a number widget (a property for the kind "spin")."""
    value = _prop(w, name) if kind == "spin" else _call(w, name)
    return value if _is_number(value) else default


def _decimals(w: Any, kind: str) -> int:
    if kind in ("int", "slider"):
        return 0
    value = _prop(w, "decimals") if kind == "spin" else _call(w, "decimals")
    return cc5_ui._clamp_int(value, 0, 12, 2 if kind == "double" else 6)


def _items(w: Any) -> list[str]:
    count = cc5_ui._clamp_int(_call(w, "count", 0), 0, MAX_ITEMS, 0)
    return [str(cc5_ui._safe(lambda i=i: w.itemText(i), "") or "") for i in range(count)]


def _is_password(q: Any, w: Any) -> bool:
    normal = getattr(q.QLineEdit, "Normal", 0)
    return _call(w, "echoMode", normal) != normal


def _shown_text(text: Any) -> tuple[str | None, bool]:
    """(the text, False) when it is a plain number or empty; (None, True) when it is hidden."""
    plain = "" if text is None else str(text)
    if plain == "" or _PLAIN_NUMBER_RE.fullmatch(plain.strip()):
        return plain, False
    return None, True


def current_value(w: Any, kind: str) -> Any:
    """The widget's value now: bool, number, {"index", "text"} for a combo, the raw text for a text box."""
    if kind == "check":
        return bool(_call(w, "isChecked", False))
    if kind == "combo":
        return {"index": cc5_ui._clamp_int(_call(w, "currentIndex", -1), -1, 1_000_000, -1),
                "text": str(_call(w, "currentText", "") or "")[:MAX_LABEL_CHARS]}
    if kind == "text":
        return str(_call(w, "text", "") or "")
    return _number(w, kind, "value")


def _public_value(kind: str, value: Any) -> tuple[Any, bool]:
    """(what is returned to the caller, hidden?)."""
    return _shown_text(value) if kind == "text" else (value, False)


def _path(w: Any) -> str:
    chain: list[str] = []
    parent = _call(w, "parent")
    while parent is not None and len(chain) < MAX_PATH_DEPTH:
        chain.append(_call(parent, "objectName", "") or cc5_ui._class_of(parent))
        parent = _call(parent, "parent")
    return " < ".join(chain)


def labels_of(q: Any, w: Any, scope: Any) -> list[str]:
    """The label texts that belong to a widget: QLabels whose buddy it is, and the QLabels that sit directly
    in the same parent when there are at most MAX_NEAR_LABELS of them (a row: label, slider, spin box)."""
    found: list[str] = []
    top = cc5_uiclick._top(scope)
    for label in cc5_ui._safe(lambda: top.findChildren(q.QLabel), []):
        buddy = _call(label, "buddy")
        if buddy is not None and cc5_ui._same_widget(buddy, w):
            found.append(cc5_ui.clean_text(_call(label, "text", "")))
    parent = _call(w, "parent")
    if parent is not None:
        near = [label for label in cc5_ui._safe(lambda: parent.findChildren(q.QLabel), [])
                if _call(label, "isVisible", False) and cc5_ui._same_widget(_call(label, "parent"), parent)]
        if len(near) <= MAX_NEAR_LABELS:
            found += [cc5_ui.clean_text(_call(label, "text", "")) for label in near]
    seen: list[str] = []
    for text in found:
        if text and text not in seen:
            seen.append(text)
    return seen


def describe(q: Any, w: Any, kind: str, scope: Any) -> dict[str, Any]:
    """One input widget as plain data (read-only). A text box's text is hidden unless it is a number."""
    out: dict[str, Any] = {"object_name": _call(w, "objectName", ""), "class": cc5_ui._class_of(w), "kind": kind,
                           "enabled": bool(_call(w, "isEnabled", True)), "path": _path(w)}
    value, hidden = _public_value(kind, current_value(w, kind))
    out["value"] = value
    if hidden:
        out["value_hidden"] = True
        out["text_length"] = len(current_value(w, kind))
    if kind in NUMBER_KINDS:
        out["minimum"], out["maximum"] = _number(w, kind, "minimum"), _number(w, kind, "maximum")
        step = _number(w, kind, "singleStep")
        if step is not None:
            out["single_step"] = step
        if kind in ("double", "spin"):
            out["decimals"] = _decimals(w, kind)
    elif kind == "combo":
        total = cc5_ui._clamp_int(_call(w, "count", 0), 0, 1_000_000, 0)
        out["count"] = total
        out["items"] = [text[:MAX_LABEL_CHARS] for text in _items(w)]
        out["editable"] = bool(_call(w, "isEditable", False))
        if total > MAX_ITEMS:
            out["note"] = f"only the first {MAX_ITEMS} items are listed"
    elif kind == "text":
        out["read_only"] = bool(_call(w, "isReadOnly", False))
        limit = cc5_ui._clamp_int(_call(w, "maxLength", 0), 0, 1_000_000, 0)
        if limit:
            out["max_length"] = limit
    elif kind == "check":
        out["text"] = cc5_ui.label_text(w)[:MAX_LABEL_CHARS]
    tip = cc5_ui.clean_text(_call(w, "toolTip", ""))
    if tip:
        out["tooltip"] = tip[:MAX_LABEL_CHARS]
    labels = labels_of(q, w, scope)
    if labels:
        out["labels"] = [text[:MAX_LABEL_CHARS] for text in labels[:MAX_LISTED]]
    return out


def _widget_desc(w: Any, kind: str | None = None) -> str:
    name = _call(w, "objectName", "")
    bits = [f"[{name}]" if name else "(no objectName)", f"<{cc5_ui._class_of(w)}>"]
    if kind:
        bits.append(kind)
    path = _path(w)
    if path:
        bits.append(f"in {path}")
    return " ".join(bits)


# --- matching -----------------------------------------------------------------------------

def _has_ancestor(w: Any, wanted: str, stop: Any) -> bool:
    """True when a widget above `w` (up to and including the window `stop`) has this objectName or class."""
    lowered = wanted.lower()
    node = _call(w, "parent")
    for _ in range(64):
        if node is None:
            return False
        if _call(node, "objectName", "") == wanted or lowered in (cc5_ui._class_of(node).lower(),
                                                                 type(node).__name__.lower()):
            return True
        if cc5_ui._same_widget(node, stop):
            return False
        node = _call(node, "parent")
    return False


def find_widget(q: Any, scope: Any, object_name: str, ancestor: str | None) -> tuple[Any | None, str | None, str | None, int]:
    """(the one visible input widget, its kind, refusal, number of hidden matches skipped)."""
    top = cc5_uiclick._top(scope)
    where = cc5_uiclick._describe_window(scope)
    what = f"objectName {object_name!r}" + (f" under {ancestor!r}" if ancestor is not None else "")
    named = [w for w in cc5_ui._safe(lambda: scope.findChildren(q.QWidget), [])
             if _call(w, "objectName", "") == object_name and cc5_ui._same_widget(_call(w, "window"), top)
             and (ancestor is None or _has_ancestor(w, ancestor, top))]
    if not named:
        return None, None, (f"no widget with {what} in {where}. Nothing was changed; find names with "
                            "find_ui_widgets (its 'path' shows what a widget sits in)"), 0
    matched = [(w, kind_of(q, w)) for w in named]
    inputs = [(w, kind) for w, kind in matched if kind is not None]
    if not inputs:
        w = named[0]
        hint = ("it is a button: press it with click_ui_button" if isinstance(w, q.QAbstractButton)
                else "this tool sets spin boxes, sliders, combo boxes, line edits, check boxes and radio buttons")
        return None, None, f"the widget {_widget_desc(w)} in {where} is not an input this tool can set; {hint}", 0
    visible = [(w, kind) for w, kind in inputs if _call(w, "isVisible", False)]
    hidden = len(inputs) - len(visible)
    if not visible:
        return None, None, (f"the widget with {what} in {where} is hidden (not on screen); hidden widgets are "
                            "never changed. Bring its page or tab to the front first (a tab: tool select_ui_tab)"), hidden
    if len(visible) > 1:
        listed = "; ".join(_widget_desc(w, kind) for w, kind in visible[:MAX_LISTED])
        return None, None, (f"{len(visible)} visible input widgets match {what} in {where}: {listed}. Nothing was "
                            "changed; give ancestor (the objectName or class of a widget only one of them sits "
                            "in)"), hidden
    return visible[0][0], visible[0][1], None, hidden


def widget_problem(q: Any, w: Any, kind: str) -> str | None:
    """Why this widget is never read or set by this tool (structure, not words), or None."""
    if kind == "text":
        parent = _call(w, "parent")
        if parent is not None and isinstance(parent, (q.QAbstractSpinBox, q.QComboBox)):
            return (f"the widget {_widget_desc(w)} is the inner text box of a spin box or combo box; name that box "
                    f"itself ({_widget_desc(parent)})")
        if _is_password(q, w):
            return f"the widget {_widget_desc(w)} is a password box: it is neither read nor typed into by this tool"
    return None


def word_problem(q: Any, w: Any, kind: str, scope: Any, item_text: str | None = None) -> str | None:
    """The money / agreement refusal for setting this widget (and selecting this combo item), or None."""
    own = cc5_ui.label_text(w) if kind == "check" else ""
    name = _call(w, "objectName", "")
    skip = cc5_uiclick.allowlist_ignores(scope, name, own)
    parts = [own, name, _call(w, "toolTip", ""), _call(w, "placeholderText", "") if kind == "text" else "",
             *labels_of(q, w, scope)]
    word = cc5_uiclick.deny_reason(*parts, skip_words=skip)
    if word:
        return (f"refused: the widget {_widget_desc(w, kind)} (text, objectName, tool tip or label) mentions "
                f"'{word}'. Controls about {cc5_ui.POLICY_SUMMARY} are changed by a person only. Ask the owner")
    if item_text is not None:
        word = cc5_uiclick.deny_reason(item_text)
        if word:
            return (f"refused: the item '{item_text[:MAX_LABEL_CHARS]}' mentions '{word}' (money or an agreement); "
                    "it is selected by a person only. Ask the owner")
    return None


def _range_text(lo: Any, hi: Any) -> str:
    return f"minimum {lo}, maximum {hi}"


def plan_value(w: Any, kind: str, value: Any) -> tuple[dict[str, Any] | None, str | None]:
    """({"target": what to set, "item_text"?}, None) when `value` fits the widget, else (None, refusal).
    Nothing is clamped: a value outside the range is refused and the range is named."""
    who = f"the widget {_widget_desc(w, kind)}"
    if kind == "check":
        if not isinstance(value, bool):
            return None, f"{who} is a check box / radio button: value must be true or false"
        return {"target": value}, None
    if kind in NUMBER_KINDS:
        if not _is_number(value):
            return None, f"{who} takes a number: value must be a number (not text, not true / false)"
        whole = kind in ("int", "slider")
        if whole and float(value) != int(value):
            return None, f"{who} takes whole numbers only; {value} was not set"
        target: Any = int(value) if whole else float(value)
        lo, hi = _number(w, kind, "minimum"), _number(w, kind, "maximum")
        if lo is None or hi is None:
            return None, f"{who} did not tell its minimum and maximum, so the value cannot be checked; nothing was set"
        if not lo <= target <= hi:
            return None, (f"{target} is outside the range of {who}: {_range_text(lo, hi)}. Nothing was set (values "
                          "are never clamped)")
        if kind in ("int", "double") and _call(w, "isReadOnly", False):
            return None, f"{who} is read-only; nothing was set"
        return {"target": target}, None
    if kind == "combo":
        items = _items(w)
        listed = ", ".join(f"{i}: '{text[:60]}'" for i, text in enumerate(items[:MAX_LISTED])) or "(no items)"
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            return None, f"{who} is a combo box: value must be the exact item text (a string) or the item index (a number)"
        if isinstance(value, str):
            hits = [i for i, text in enumerate(items) if text == value]
            if not hits:
                hits = [i for i, text in enumerate(items) if label_key(text) == label_key(value)]
            if not hits:
                return None, f"no item {value!r} in {who}. Items: {listed}. Nothing was set"
            if len(hits) > 1:
                return None, (f"{len(hits)} items of {who} are called {value!r} (indexes {hits[:MAX_LISTED]}). "
                              "Nothing was set; give the index (a number) instead")
            index = hits[0]
        else:
            if float(value) != int(value) or not 0 <= int(value) < len(items):
                return None, (f"{who} has no item with index {value} (it has {len(items)}, the first is 0). "
                              f"Items: {listed}. Nothing was set")
            index = int(value)
        item = cc5_ui._safe(lambda: w.model().item(index))
        if item is not None and cc5_ui._safe(item.isEnabled, True) is False:
            return None, f"the item {index}: '{items[index][:60]}' of {who} is disabled (greyed out); nothing was set"
        return {"target": index, "item_text": items[index]}, None
    if not isinstance(value, str):                      # kind "text"
        return None, f"{who} is a text box: value must be a string"
    if _call(w, "isReadOnly", False):
        return None, f"{who} is read-only; nothing was set"
    limit = cc5_ui._clamp_int(_call(w, "maxLength", 0), 0, 1_000_000, 0)
    if limit and len(value) > limit:
        return None, f"{who} takes at most {limit} characters ({len(value)} given); nothing was set"
    return {"target": value}, None


# --- arguments ----------------------------------------------------------------------------

def read_args(body: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    """Checked copy of the request body, or the reason it is refused. Unknown keys are refused."""
    p = dict(body or {})
    unknown = sorted(set(p) - ALLOWED_KEYS)
    if unknown:
        return None, f"unknown argument(s) {unknown}; allowed: {sorted(ALLOWED_KEYS)}"
    for key in ("window", "object_name", "ancestor"):
        value = p.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_NAME_CHARS:
            return None, f"{key} must be a non-empty string of at most {MAX_NAME_CHARS} characters"
    if p.get("window") is None:
        return None, "window is required: the title (or objectName) of the CC5 window, dialog or panel"
    if p.get("object_name") is None:
        return None, "object_name is required: the exact objectName of the input widget (find it with find_ui_widgets)"
    for key in ("screenshot", "read_only"):
        if key in p and not isinstance(p[key], bool):
            return None, f"{key} must be true or false"
    p["read_only"] = p.get("read_only", False) is True
    value = p.get("value")
    if not p["read_only"]:
        if value is None:
            return None, "value is required (or read_only=true to only read the widget)"
        if not isinstance(value, (bool, int, float, str)):
            return None, "value must be a number, a string or true / false"
        if isinstance(value, float) and not math.isfinite(value):
            return None, "value must be a finite number"
        if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
            return None, f"a text value may have at most {MAX_TEXT_CHARS} characters"
    p["wait_ms"] = cc5_ui._clamp_int(p.get("wait_ms", DEFAULT_WAIT_MS), MIN_WAIT_MS, MAX_WAIT_MS, DEFAULT_WAIT_MS)
    p["max_width"] = cc5_ui._clamp_int(p.get("max_width", 900), 200, 2400, 900)
    p["screenshot"] = p.get("screenshot", True) is not False
    return p, None


# --- reading (read-only) ------------------------------------------------------------------

def read_widget(p: dict[str, Any]) -> dict[str, Any]:
    """The widget's kind, value, range and items. Changes nothing."""
    q = cc5_ui._qt()
    window, error = cc5_uiclick.find_window(q, p["window"])
    if error:
        return {"success": False, "error": error}
    w, kind, error, hidden = find_widget(q, window, p["object_name"], p.get("ancestor"))
    if error is None:
        error = widget_problem(q, w, kind)
    if error:
        return {"success": False, "error": error}
    out: dict[str, Any] = {"success": True, "read_only": True, "window": cc5_uiclick._title(window),
                           "widget": describe(q, w, kind, window)}
    if hidden:
        out["hidden_skipped"] = hidden
    return out


# --- setting (a job) ----------------------------------------------------------------------

def resolve(p: dict[str, Any]) -> dict[str, Any]:
    """{"window", "widget", "kind", "plan", "hidden_skipped"} for a change request, or {"error"}."""
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
    w, kind, error, hidden = find_widget(q, window, p["object_name"], p.get("ancestor"))
    if error is None:
        error = widget_problem(q, w, kind)
    if error:
        return {"error": error}
    if not _call(w, "isEnabled", True):
        return {"error": f"the widget {_widget_desc(w, kind)} is disabled (greyed out) and cannot be changed now"}
    plan, error = plan_value(w, kind, p["value"])
    if error is None:
        error = word_problem(q, w, kind, window, plan.get("item_text"))
    if error:
        return {"error": error}
    return {"window": window, "widget": w, "kind": kind, "plan": plan, "hidden_skipped": hidden}


def _emit(w: Any, signal: str, *args: Any, overload: Any = None) -> bool:
    """Emit one of the widget's own signals, as Qt does after a person's change. False when it has none."""
    def fire() -> bool:
        bound = getattr(w, signal)
        (bound if overload is None else bound[overload]).emit(*args)
        return True

    return bool(cc5_ui._safe(fire, False))


def same_value(kind: str, now: Any, target: Any, decimals: int = 0) -> bool:
    """True when the widget shows the value that was asked for."""
    if kind == "combo":
        return isinstance(now, dict) and now.get("index") == target
    if kind in ("double", "spin"):
        return _is_number(now) and abs(float(now) - float(target)) <= 0.5 * 10 ** (-decimals) + 1e-12
    return now == target


def apply_value(w: Any, kind: str, plan: dict[str, Any]) -> list[str]:
    """Change the widget with the calls a person's change would cause; returns the signals sent by hand.
    Raises ValueError when a text box does not accept the text (the old text is put back first)."""
    target, sent = plan["target"], []
    if kind == "check":
        if _call(w, "isTristate", False):
            w.setChecked(target)
        else:
            w.click()
    elif kind == "combo":
        w.setCurrentIndex(target)
        if _emit(w, "activated", target):
            sent.append("activated")
        if _emit(w, "textActivated", plan.get("item_text", "")):
            sent.append("textActivated")
    elif kind == "slider":
        if all(callable(getattr(w, name, None)) for name in ("setSliderDown", "setSliderPosition")):
            w.setSliderDown(True)
            try:
                w.setSliderPosition(target)
            finally:
                w.setSliderDown(False)
        else:
            w.setValue(target)
    elif kind == "text":
        old = str(_call(w, "text", "") or "")
        w.setText(target)
        if _call(w, "hasAcceptableInput", True) is False:
            w.setText(old)
            raise ValueError("the text box does not accept that text (its validator or input mask); "
                             "the old text was put back")
        sent += [name for name, args in (("textEdited", (target,)), ("editingFinished", ())) if _emit(w, name, *args)]
    else:                                               # int, double, spin
        if kind == "spin":
            w.setProperty("value", target)
        else:
            w.setValue(target)
        if _emit(w, "editingFinished"):
            sent.append("editingFinished")
    return sent


def _set_steps(p: dict[str, Any]) -> Iterator[float]:
    found = resolve(p)                            # again: the window may have changed since the request
    if "error" in found:
        return {"success": False, "error": found["error"]}
    w, kind, plan = found["widget"], found["kind"], found["plan"]
    before = current_value(w, kind)
    state: dict[str, Any] = {"ran": False, "returned": False, "error": None, "signals": [], "skipped": False}

    def change() -> None:
        state["ran"] = True
        try:
            if same_value(kind, before, plan["target"], _decimals(w, kind)):
                state["skipped"] = True           # already there: nothing is sent, as when a person leaves it alone
            else:
                state["signals"] = apply_value(w, kind, plan)
        except Exception as exc:                  # a timer callback must never raise
            state["error"] = str(exc) if isinstance(exc, ValueError) else f"{type(exc).__name__}: {exc}"
        state["returned"] = True

    cc5_ui._later(SET_DELAY_MS, change)
    yield SET_DELAY_MS + p["wait_ms"]
    return _report(p, found, before, state)


def _report(p: dict[str, Any], found: dict[str, Any], before: Any, state: dict[str, Any]) -> dict[str, Any]:
    q = cc5_ui._qt()
    window, w, kind, plan = found["window"], found["widget"], found["kind"], found["plan"]
    target = plan["target"]
    after = current_value(w, kind)
    took = same_value(kind, after, target, _decimals(w, kind))
    shown_before, hidden_before = _public_value(kind, before)
    out: dict[str, Any] = {
        "success": state["ran"] and state["error"] is None and state["returned"] and took,
        "window": cc5_uiclick._title(window),
        "widget": {"object_name": _call(w, "objectName", ""), "class": cc5_ui._class_of(w), "kind": kind,
                   "path": _path(w)},
        "requested": p["value"], "value_before": shown_before,
        "value_after": after,                     # a text box: what the caller itself asked for, read back
        "changed": before != after, "set_returned": state["returned"], "waited_ms": p["wait_ms"],
    }
    if hidden_before:
        out["value_before_hidden"] = True
    if kind == "text" and not took:
        out["value_after"], hidden_after = _shown_text(after)
        if hidden_after:
            out["value_after_hidden"] = True
    if kind in NUMBER_KINDS:
        out["minimum"], out["maximum"] = _number(w, kind, "minimum"), _number(w, kind, "maximum")
    if state["signals"]:
        out["signals_sent"] = state["signals"]
    if not state["ran"]:
        out["error"] = "the change did not run (CC5's Qt timer did not fire in time); look before trying again"
    elif state["error"]:
        out["error"] = f"the change failed: {state['error']}"
    elif not state["returned"]:
        out["note"] = ("the change has not returned yet: CC5 is showing a window it opened (see dialogs) or is "
                       "still working. Nothing else was changed or pressed; read the widget again (read_only) "
                       "when the window is gone")
    elif not took:
        out["error"] = (f"asked for {target!r} but the widget shows {out['value_after']!r}: CC5 did not take the "
                        "value (or changed it back). Nothing else was tried")
    elif state["skipped"]:
        out["note"] = "the widget already had that value; nothing was sent"
    elif kind in ("double", "spin") and _is_number(after) and float(after) != float(target):
        out["note"] = f"the widget keeps {_decimals(w, kind)} decimal(s): it shows {after}"
    if found["hidden_skipped"]:
        out["hidden_skipped"] = found["hidden_skipped"]
    cc5_uiclick.add_window_view(out, p, window)
    return out


def ui_value(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Route /ui/value: read ONE input widget of a window, or set its value.

    Body: window (title, case-insensitive, or objectName of a CC5 window / dialog / dock panel;
    required), object_name (exact objectName of the widget; required), ancestor (objectName or class of
    a widget it sits in; needed when several visible widgets share the objectName), value (number,
    string or true / false, by the widget's kind; required unless read_only), read_only (default false),
    wait_ms (after the change, default 500, 200-15000), screenshot (default true: PNG of the window and
    of each open dialog), max_width (default 900). With read_only the reply is the widget itself
    (read_only=true, widget: kind, value, minimum / maximum, items, ...; nothing changes, no job).
    Otherwise a job starts; its result has widget, requested, value_before / value_after, changed,
    signals_sent, window_open, png_base64 and dialogs. Refusals: see the module docstring.
    """
    p, error = read_args(body)
    if error:
        return {"success": False, "error": error}
    if p["read_only"]:
        return read_widget(p)
    found = resolve(p)
    if "error" in found:
        return {"success": False, "error": found["error"]}
    return cc5_ui.start_job("value", _set_steps, p, max_seconds=p["wait_ms"] / 1000 + 120)


ROUTES: dict[str, tuple[str, Callable[..., dict[str, Any]]]] = {
    "/ui/value": ("ui_value", ui_value),
}

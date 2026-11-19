"""
Press ONE named button of a CC5 window without the mouse: route /ui/click (a job).

Why (2026-10-30): while the Windows screen is locked (on the remote CC5 machine) mouse clicks do nothing, so a worker could
not press Body Wrap's "Save Skeleton" and the owner's hand-fixed points were lost. Qt's
QAbstractButton.click() still works on a locked screen (proven with Headshot's Paste button).

What it does: finds one button (QPushButton / QToolButton / any QAbstractButton) inside a named CC5
window, dialog or dock panel, by objectName and/or its exact visible text -- optionally one entry of
that button's own drop-down menu (menu_item) -- and clicks it on CC5's main thread, deferred by a
Qt timer like the SkinGen switch. It waits wait_ms, then returns a picture of the window and the
dialogs that are open. A window the click opens is reported, never answered.

What it refuses (nothing is pressed; the reason comes back as HTTP 400):
  * a window name or button that matches nothing, or more than one VISIBLE thing (hidden buttons
    never count and are never pressed);
  * a disabled or hidden button or menu entry;
  * a button or menu entry whose text, objectName or tool tip contains a DENY_WORDS word (points,
    buy, purchase, licence, upgrade, credit, subscribe, pay and the Japanese words) or a
    word of cc5_ui.forbidden_reason (order, checkout, cart, price, trial, terms / agreement, ...).
    Since 2026-11-19 only money and agreements are refused: delete, remove, login and update buttons
    ARE pressed (the policy is written down once, at cc5_ui.MONEY_STEMS). Two words are narrower on a
    control than in a window (cc5_ui NARROWED RULE 1 and 2): "order" is not refused in "sort order",
    "draw order", "render order", "layer order", "order by", "in order to"; "activate" is refused only
    next to a licence / product word or when the label names nothing else ("Activate", "Activation"),
    so "Activate Physics" is pressed;
  * (exceptions: the exact controls of the ALLOWLIST table below are pressed although one named word
    matches: Body Wrap's "Generate Wrap Points" / "Align Points" buttons and "Save Wrap Points" /
    "Load Wrap Points" menu entries, owner 2026-10-31, and the Modify panel's "Activate Expression
    Wrinkles" check box, owner 2026-11-19)
  * any click while a window about money or an agreement is open (purchase, licence, activation, terms, ...);
  * a button outside the modal window that is open (a person could not press it either);
  * a button that opens a drop-down menu when no menu_item is given (the menu would stay open).

The checks live here, in CC5, because any local program can call the bridge: the MCP tool
(click_ui_button) only forwards the request and shows the answer.
"""

from __future__ import annotations

import dataclasses
import re
import unicodedata
from typing import Any, Callable, Iterator

import cc5_ui
import cc5_uiview

DEFAULT_WAIT_MS = 1000
MIN_WAIT_MS = 200
MAX_WAIT_MS = 15000
CLICK_DELAY_MS = 50                 # the click runs in its own timer callback (it may open a modal window)
MAX_NAME_CHARS = 256
MAX_LISTED = 25                     # buttons / windows / menu entries named in a refusal
DIALOG_SHOT_WIDTH = 800
ALLOWED_KEYS = frozenset({"window", "object_name", "text", "menu_item", "wait_ms", "screenshot", "max_width"})

# Words that put a button or menu entry off limits. MONEY only (2026-11-19: the owner relaxed the list
# of 2026-10-30 to money only; "delete", "削除" and "remove" were taken out). Matched case-insensitively
# ANYWHERE in the text, objectName and tool tip after cc5_ui.norm() (so 'qtBuyButton' counts); the
# longer ones also with spaces and punctuation removed ('Pur chase'). The window word groups
# cc5_ui.MONEY_* and cc5_ui.AGREEMENT_* (order, checkout, cart, price, trial, terms, agreement, ...)
# are checked as well, through cc5_ui.forbidden_reason: the policy is described there.
DENY_WORDS: tuple[str, ...] = (
    "point", "ポイント", "buy", "購入", "purchase",
    "license", "licence", "ライセンス", "activate", "upgrade", "credit", "クレジット",
    "subscribe", "pay", "支払",
)
_DENY_NEEDLES = tuple((word, cc5_ui.norm(word)) for word in DENY_WORDS)
_COMPACT_MIN_CHARS = 5

_POINT_WORDS = frozenset({"point", "ポイント"})
_ACTIVATION_WORDS = frozenset({cc5_ui.ACTIVATION_WORD})


# --- THE ALLOWLIST: exact controls that may be used although ONE named refusal word matches ----------
#
# How to read an entry: in the window (window_title: its title, compared like every name here, i.e.
# case-insensitive; and / or window_object_name: its exact objectName; the window is the TOP-LEVEL window the
# control sits in, so a control in a dock panel is matched by the main window), the control of this `kind`
# with exactly this objectName AND exactly this visible text may ignore the refusal words in `ignore`.
#   * kind "control": a button, a check box or an input widget; text is its own visible text.
#   * kind "menu_entry": one entry of a button's drop-down menu; text is the entry's text, object_name the
#     objectName of the button that holds the menu. The words are then ignored for the entry AND for the
#     button that holds it.
#   * ignore: names from DENY_WORDS ("point", "ポイント") or cc5_ui.ACTIVATION_WORD ("activat").
# What an entry does NOT do:
#   * it never widens a word rule: a control with a similar name or text stays refused;
#   * every OTHER money / agreement word in the control's text, objectName or tool tip still refuses it;
#   * it only switches off the control's own word check. Nothing is pressed while a money or agreement
#     window is open (blocking_reason), and hidden / disabled / ambiguous controls stay refused.
# object_name None means "any objectName": ONLY the four Body Wrap entries of 2026-10-31 have it, because
# their real objectNames were never written down (they matched on window title and text from the start).
# Every new entry must name the objectName. Add an entry only with the owner's word; note date and reason.
@dataclasses.dataclass(frozen=True)
class AllowEntry:
    window_title: str | None
    window_object_name: str | None
    kind: str                                   # "control" | "menu_entry"
    object_name: str | None
    text: str
    ignore: frozenset[str]
    why: str


ALLOWLIST: tuple[AllowEntry, ...] = (
    # Owner, 2026-10-31 ("いいよ、進めて"): the two Body Wrap steps that only place wrap points on the mesh
    # (they do not use AI points). "AI Points" and the like stay refused (cc5_ui.MONEY_STEMS "ai point").
    AllowEntry("body wrap", None, "control", None, "generate wrap points", _POINT_WORDS,
               "places wrap points on the mesh; no AI points are used"),
    AllowEntry("body wrap", None, "control", None, "align points", _POINT_WORDS,
               "aligns the wrap points; no AI points are used"),
    # Owner, 2026-10-31 (second request, "道具の決まりも変えていい"): the 💾 menu's two entries that save /
    # load the wrap points to a file.
    AllowEntry("body wrap", None, "menu_entry", None, "save wrap points", _POINT_WORDS,
               "saves the wrap points to a file"),
    AllowEntry("body wrap", None, "menu_entry", None, "load wrap points", _POINT_WORDS,
               "loads the wrap points from a file"),
    # Owner, 2026-11-19 (FORK-FIXES.md): Modify panel > Expression Wrinkles tab. Turns the wrinkle system on
    # for the open character; no licence, no cost.
    AllowEntry(None, "MainWindow", "control", "qtActiveWrinkleCheckBox", "activate expression wrinkles",
               _ACTIVATION_WORDS, "switches expression wrinkles on for the open character"),
)

# The old names of the Body Wrap exception, read from the table (kept for readers of older notes).
POINT_EXCEPTION_WINDOW = "body wrap"
POINT_EXCEPTION_BUTTONS = frozenset(e.text for e in ALLOWLIST if e.window_title == "body wrap" and e.kind == "control")
POINT_EXCEPTION_MENU_ENTRIES = frozenset(e.text for e in ALLOWLIST
                                         if e.window_title == "body wrap" and e.kind == "menu_entry")

# CC5's start-up box below. Until 2026-11-19 only its Cancel button could be pressed (its text says
# "update", which was a refused word then). "update" is allowed now, so both buttons can be pressed like
# any other; what is left is the window lookup: the box has the same title as the main window, so a
# request that names "Character Creator 5" while exactly this box is open means the box.
UNSAVED_TITLE = "character creator 5"
UNSAVED_TEXT = "unsaved project data found. would you like to update your project with the unsaved changes?"
UNSAVED_BUTTONS = frozenset({"ok", "cancel"})


def _is_unsaved_box(info: dict[str, Any]) -> bool:
    return (label_key(info.get("title", "")) == UNSAVED_TITLE
            and label_key(info.get("text", "")) == UNSAVED_TEXT
            and not info.get("needs_human")
            and not info.get("checkboxes")
            and {label_key(b) for b in info.get("buttons", [])} <= UNSAVED_BUTTONS)


def _asks_unsaved_box(p: dict[str, Any]) -> bool:
    return label_key(p.get("window") or "") == UNSAVED_TITLE and p.get("menu_item") is None


def _call(obj: Any, method: str, default: Any = None) -> Any:
    """obj.method(), or the default when the method is missing or raises (a dead Qt wrapper)."""
    fn = getattr(obj, method, None)
    return cc5_ui._safe(fn, default) if callable(fn) else default


# --- the safety words ---------------------------------------------------------------------

def deny_reason(*parts: Any, skip_words: frozenset[str] = frozenset()) -> str | None:
    """The word that puts a button or menu entry off limits, or None.

    Each part (text, objectName, tool tip) is checked on its own, with tags removed both with and
    without a space ('<b>Del</b>ete'), so words cannot hide across parts or inside rich text.
    skip_words names words that are not counted: only an ALLOWLIST entry gives them (allowlist_ignores).
    "activate" follows cc5_ui's NARROWED RULE 2 for controls (cc5_ui.activation_reason), not the
    anywhere-match of the other DENY_WORDS; "order" follows NARROWED RULE 1.
    """
    for part in parts:
        if not part:
            continue
        for variant in {cc5_ui.clean_text(part), cc5_ui._squash_tags(part)}:
            text = cc5_ui.norm(variant)
            compact = re.sub(r"[\W_]+", "", text)
            for word, needle in _DENY_NEEDLES:
                if word in skip_words or word == "activate":
                    continue
                if needle in text or (len(needle) >= _COMPACT_MIN_CHARS and needle in compact):
                    return word
    ignore = _ACTIVATION_WORDS if cc5_ui.ACTIVATION_WORD in skip_words else frozenset()
    return cc5_ui.forbidden_reason(*parts, control=True, ignore=ignore)


# --- matching -----------------------------------------------------------------------------

def label_key(text: Any) -> str:
    """How names are compared: rich text removed, NFKC, no '&' marker, white space collapsed, case-folded."""
    plain = unicodedata.normalize("NFKC", cc5_ui.clean_text(text)).replace("&", "")
    return " ".join(plain.casefold().split())


def _title(w: Any) -> str:
    return cc5_ui.clean_text(_call(w, "windowTitle", ""))


def _describe_window(w: Any) -> str:
    name = _call(w, "objectName", "")
    return f"'{_title(w) or '(no title)'}'" + (f" [{name}]" if name else "") + f" <{cc5_ui._class_of(w)}>"


def candidate_windows(q: Any) -> list[Any]:
    """Visible top-level windows (not menus) and visible dock panels: where buttons are looked for."""
    app = q.QApplication.instance()
    if app is None:
        return []
    found = [w for w in app.topLevelWidgets()
             if _call(w, "isVisible", False) and not isinstance(w, q.QMenu)]
    dock = getattr(q, "QDockWidget", None)
    if dock is not None:
        for w in q.QApplication.allWidgets():
            if isinstance(w, dock) and _call(w, "isVisible", False) and not any(w is f for f in found):
                found.append(w)
    return found


def find_window(q: Any, name: str) -> tuple[Any | None, str | None]:
    """The one open window / dialog / dock whose title (case-insensitive) or objectName is `name`."""
    wanted = label_key(name)
    windows = candidate_windows(q)
    hits = [w for w in windows if label_key(_call(w, "windowTitle", "")) == wanted or _call(w, "objectName", "") == name]
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        known = [_describe_window(w) for w in windows if _title(w) or _call(w, "objectName", "")][:MAX_LISTED]
        return None, (f"no open CC5 window, dialog or panel is called {name!r}. "
                      f"Open ones: {', '.join(known) or '(none)'}")
    listed = ", ".join(_describe_window(w) for w in hits[:MAX_LISTED])
    return None, (f"{len(hits)} open windows are called {name!r}: {listed}. Nothing was pressed; "
                  "name the window by its objectName instead")


def _top(w: Any) -> Any:
    return _call(w, "window") or w


def blocking_reason(q: Any, scope: Any | None = None) -> str | None:
    """Why nothing may be pressed now: a window about money or an agreement is open (it needs a person),
    or a modal window is open and the target is not in it. None when pressing is allowed."""
    for info, _w in cc5_ui.scan_windows():
        if info["needs_human"]:
            return (f"the window '{info['title']}' mentions '{info['needs_human']}' (money or an agreement): a "
                    "person must decide, and nothing is pressed while it is open. Show it to the owner "
                    "(list_cc5_windows)")
    if scope is None:
        return None
    app = q.QApplication.instance()
    modals = [w for w in (app.topLevelWidgets() if app is not None else [])
              if _call(w, "isVisible", False) and _call(w, "isModal", False)]
    if not modals:
        return None
    active = _call(q.QApplication, "activeModalWidget")
    allowed = [active] if active is not None else modals
    top = _top(scope)
    if any(cc5_ui._same_widget(top, m) for m in allowed):
        return None
    titles = ", ".join(f"'{_title(m) or '(no title)'}'" for m in allowed)
    return (f"the modal window {titles} is open, so a person could not press a button in "
            f"{_describe_window(scope)} now either. Deal with that window first (list_cc5_windows)")


def _button_desc(b: Any) -> str:
    text = cc5_ui.label_text(b)
    name = _call(b, "objectName", "")
    tip = cc5_ui.clean_text(_call(b, "toolTip", ""))
    bits = [f"'{text}'" if text else "(no text)"]
    if name:
        bits.append(f"[{name}]")
    if tip and label_key(tip) != label_key(text):
        bits.append(f"tip '{tip[:60]}'")
    return " ".join(bits)


def _what(object_name: str | None, text: str | None) -> str:
    bits = []
    if object_name is not None:
        bits.append(f"objectName {object_name!r}")
    if text is not None:
        bits.append(f"text {text!r}")
    return " and ".join(bits)


def buttons_in(q: Any, scope: Any) -> list[Any]:
    """Buttons of `scope` that belong to its own window (not to a child dialog parented to it)."""
    top = _top(scope)
    return [b for b in cc5_ui._safe(lambda: scope.findChildren(q.QAbstractButton), [])
            if cc5_ui._same_widget(_call(b, "window"), top)]


def find_button(q: Any, scope: Any, object_name: str | None, text: str | None) -> tuple[Any | None, str | None, int]:
    """(the one visible matching button, refusal, number of hidden matches skipped)."""
    buttons = buttons_in(q, scope)
    wanted_text = label_key(text) if text is not None else None
    matched = [b for b in buttons
               if (object_name is None or _call(b, "objectName", "") == object_name)
               and (wanted_text is None or label_key(cc5_ui.label_text(b)) == wanted_text)]
    visible = [b for b in matched if _call(b, "isVisible", False)]
    hidden = len(matched) - len(visible)
    what, where = _what(object_name, text), _describe_window(scope)
    if not matched:
        shown = [_button_desc(b) for b in buttons if _call(b, "isVisible", False)][:MAX_LISTED]
        return None, f"no button with {what} in {where}. Visible buttons there: {', '.join(shown) or '(none)'}", 0
    if not visible:
        return None, (f"the button with {what} in {where} is hidden (not on screen); hidden buttons are never "
                      "pressed. Bring its page or tab to the front first (a tab: tool select_ui_tab)"), hidden
    if len(visible) > 1:
        listed = ", ".join(_button_desc(b) for b in visible[:MAX_LISTED])
        return None, (f"{len(visible)} visible buttons match {what} in {where}: {listed}. Nothing was pressed; "
                      "give object_name (and text) so exactly one matches"), hidden
    return visible[0], None, hidden


def _menu_entries(menu: Any) -> list[Any]:
    return [a for a in _call(menu, "actions", []) if not _call(a, "isSeparator", False)]


def _entry_texts(menu: Any) -> str:
    texts = [f"'{cc5_ui.label_text(a)}'" for a in _menu_entries(menu) if _call(a, "isVisible", True)]
    return ", ".join(texts[:MAX_LISTED]) or "(empty)"


def find_menu_entry(menu: Any, item: str) -> tuple[Any | None, str | None]:
    """The one visible, enabled entry of a drop-down menu whose text is `item`."""
    wanted = label_key(item)
    hits = [a for a in _menu_entries(menu) if label_key(cc5_ui.label_text(a)) == wanted]
    visible = [a for a in hits if _call(a, "isVisible", True)]
    if not visible:
        state = "hidden" if hits else "not there"
        return None, f"the menu entry {item!r} is {state}. Entries: {_entry_texts(menu)}"
    if len(visible) > 1:
        return None, f"{len(visible)} menu entries are called {item!r}; nothing was pressed"
    entry = visible[0]
    if _call(entry, "menu") is not None:
        return None, f"the menu entry {item!r} opens a sub-menu; only plain entries can be pressed"
    if not _call(entry, "isEnabled", True):
        return None, f"the menu entry {item!r} is disabled (greyed out) and cannot be pressed now"
    return entry, None


def allowlist_ignores(scope: Any | None, object_name: Any, text: Any, kind: str = "control") -> frozenset[str]:
    """The refusal words the ALLOWLIST lets this exact control ignore (empty for every other control).
    scope: the window / panel the control was found in; object_name and text: the control's own (for
    kind "menu_entry": the holding button's objectName and the entry's text)."""
    if scope is None:
        return frozenset()
    top = _top(scope)
    title, window_name, wanted = label_key(_title(top)), _call(top, "objectName", ""), label_key(text)
    words: set[str] = set()
    for entry in ALLOWLIST:
        if (entry.kind == kind and entry.text == wanted
                and (entry.window_title is not None or entry.window_object_name is not None)
                and entry.window_title in (None, title)
                and entry.window_object_name in (None, window_name)
                and entry.object_name in (None, object_name)):
            words |= entry.ignore
    return frozenset(words)


def _target_problem(button: Any, menu_item: str | None,
                    scope: Any | None = None) -> tuple[Any | None, str | None]:
    """(what to press: the button or one of its menu entries, refusal)."""
    if not _call(button, "isEnabled", True):
        return None, f"the button {_button_desc(button)} is disabled (greyed out) and cannot be pressed now"
    name = _call(button, "objectName", "")
    skip = (allowlist_ignores(scope, name, menu_item, "menu_entry") if menu_item is not None
            else allowlist_ignores(scope, name, cc5_ui.label_text(button)))
    word = deny_reason(cc5_ui.label_text(button), _call(button, "objectName", ""), _call(button, "toolTip", ""),
                       skip_words=skip)
    if word:
        return None, (f"refused: the button {_button_desc(button)} mentions '{word}'. Buttons about "
                      f"{cc5_ui.POLICY_SUMMARY} are pressed by a person only. Ask the owner")
    menu = _call(button, "menu")
    if menu_item is None:
        if menu is not None:
            return None, (f"the button {_button_desc(button)} opens a drop-down menu ({_entry_texts(menu)}); "
                          "pass menu_item with the exact text of the entry to press")
        return button, None
    if menu is None:
        return None, f"the button {_button_desc(button)} has no drop-down menu, so menu_item cannot be used"
    entry, error = find_menu_entry(menu, menu_item)
    if error:
        return None, error
    word = deny_reason(cc5_ui.label_text(entry), _call(entry, "objectName", ""), _call(entry, "toolTip", ""),
                       skip_words=skip)
    if word:
        return None, (f"refused: the menu entry '{cc5_ui.label_text(entry)}' mentions '{word}' (money or an "
                      "agreement); it is pressed by a person only. Ask the owner")
    return entry, None


# --- arguments ----------------------------------------------------------------------------

def read_args(body: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str | None]:
    """Checked copy of the request body, or the reason it is refused. Unknown keys are refused."""
    p = dict(body or {})
    unknown = sorted(set(p) - ALLOWED_KEYS)
    if unknown:
        return None, f"unknown argument(s) {unknown}; allowed: {sorted(ALLOWED_KEYS)}"
    for key in ("window", "object_name", "text", "menu_item"):
        value = p.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_NAME_CHARS:
            return None, f"{key} must be a non-empty string of at most {MAX_NAME_CHARS} characters"
    if p.get("window") is None:
        return None, "window is required: the title (or objectName) of the CC5 window, dialog or panel"
    if p.get("object_name") is None and p.get("text") is None:
        return None, "give object_name or text (or both) of the button to press"
    for key in ("screenshot",):
        if key in p and not isinstance(p[key], bool):
            return None, f"{key} must be true or false"
    p["wait_ms"] = cc5_ui._clamp_int(p.get("wait_ms", DEFAULT_WAIT_MS), MIN_WAIT_MS, MAX_WAIT_MS, DEFAULT_WAIT_MS)
    p["max_width"] = cc5_ui._clamp_int(p.get("max_width", 900), 200, 2400, 900)
    p["screenshot"] = p.get("screenshot", True) is not False
    return p, None


def resolve(p: dict[str, Any]) -> dict[str, Any]:
    """{"window", "button", "target", "hidden_skipped"} for a request, or {"error"}."""
    q = cc5_ui._qt()
    unsaved = _asks_unsaved_box(p)
    blocked = blocking_reason(q)
    if blocked:
        return {"error": blocked}
    if unsaved:                                   # the main window shares the title: take the box when it is open
        boxes = [w for info, w in cc5_ui.scan_windows() if _is_unsaved_box(info)]
        window, error = (boxes[0], None) if len(boxes) == 1 else find_window(q, p["window"])
    else:
        window, error = find_window(q, p["window"])
    if error:
        return {"error": error}
    blocked = blocking_reason(q, window)
    if blocked:
        return {"error": blocked}
    button, error, hidden = find_button(q, window, p.get("object_name"), p.get("text"))
    if error:
        return {"error": error}
    target, error = _target_problem(button, p.get("menu_item"), window)
    if error:
        return {"error": error}
    return {"window": window, "button": button, "target": target, "hidden_skipped": hidden}


# --- the job ------------------------------------------------------------------------------

def _checked(button: Any) -> bool | None:
    return bool(_call(button, "isChecked", False)) if _call(button, "isCheckable", False) else None


def _click_steps(p: dict[str, Any]) -> Iterator[float]:
    found = resolve(p)                            # again: the window may have changed since the request
    if "error" in found:
        return {"success": False, "error": found["error"]}
    window, button, target = found["window"], found["button"], found["target"]
    is_entry = p.get("menu_item") is not None
    before = _checked(button)
    state: dict[str, Any] = {"ran": False, "returned": False, "error": None}

    def press() -> None:
        state["ran"] = True
        try:
            if is_entry:
                target.trigger()
            else:
                target.click()
        except Exception as exc:                  # a timer callback must never raise
            state["error"] = f"{type(exc).__name__}: {exc}"
        state["returned"] = True

    cc5_ui._later(CLICK_DELAY_MS, press)
    yield CLICK_DELAY_MS + p["wait_ms"]
    return _report(p, window, button, before, state, found["hidden_skipped"])


def _report(p: dict[str, Any], window: Any, button: Any, before: bool | None, state: dict[str, Any],
            hidden: int) -> dict[str, Any]:
    pressed: dict[str, Any] = {"text": cc5_ui.label_text(button), "object_name": _call(button, "objectName", ""),
                               "class": cc5_ui._class_of(button)}
    tip = cc5_ui.clean_text(_call(button, "toolTip", ""))
    if tip:
        pressed["tooltip"] = tip[:200]
    if p.get("menu_item") is not None:
        pressed["menu_item"] = p["menu_item"]
    out: dict[str, Any] = {"success": state["ran"] and state["error"] is None, "window": _title(window),
                           "pressed": pressed, "click_returned": state["returned"], "waited_ms": p["wait_ms"]}
    if not state["ran"]:
        out["error"] = "the click did not run (CC5's Qt timer did not fire in time); look before trying again"
    elif state["error"]:
        out["error"] = f"the click raised {state['error']}"
    elif not state["returned"]:
        out["note"] = ("the click has not returned yet: CC5 is showing a window it opened (see dialogs) or is "
                       "still working. Nothing else was pressed")
    if before is not None:
        out["checked_before"], out["checked_after"] = before, _checked(button)
    if hidden:
        out["hidden_skipped"] = hidden
    add_window_view(out, p, window)
    return out


def add_window_view(out: dict[str, Any], p: dict[str, Any], window: Any) -> None:
    """Fill window_open, the window picture (p["screenshot"]) and the open dialogs into a job result.
    Read-only: no dialog is answered. Shared with cc5_uitab."""
    out["window_open"] = bool(_call(window, "isVisible", False))
    if p["screenshot"] and out["window_open"]:
        shot = cc5_uiview.grab_png(window, p["max_width"])
        if "png_base64" in shot:
            out["png_base64"], out["png_size"] = shot["png_base64"], shot["png_size"]
        else:
            out["screenshot_error"] = shot.get("error", "no picture")
    dialogs = cc5_uiview.ui_windows({"screenshot": p["screenshot"], "max_width": min(p["max_width"], DIALOG_SHOT_WIDTH)})
    out["dialogs"] = dialogs.get("windows", [])


def ui_click(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Route /ui/click: press ONE named button (or one entry of its drop-down menu). Starts a job.

    Body: window (title, case-insensitive, or objectName of a CC5 window / dialog / dock panel;
    required), object_name and/or text of the button (exact; text ignores case and the & marker),
    menu_item (exact text of an entry in the button's own drop-down menu), wait_ms (after the click,
    default 1000, 200-15000), screenshot (default true: PNG of the window and of each open dialog),
    max_width (default 900). Refusals: see the module docstring. The job result has pressed,
    click_returned (false while a window the click opened is still up), checked_before/after for
    toggles, window_open, png_base64 and dialogs.
    """
    p, error = read_args(body)
    if error:
        return {"success": False, "error": error}
    found = resolve(p)
    if "error" in found:
        return {"success": False, "error": found["error"]}
    return cc5_ui.start_job("click", _click_steps, p, max_seconds=p["wait_ms"] / 1000 + 120)


ROUTES: dict[str, tuple[str, Callable[..., dict[str, Any]]]] = {
    "/ui/click": ("ui_click", ui_click),
}

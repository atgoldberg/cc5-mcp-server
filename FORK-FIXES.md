# Fork fix list (branch `piqsiq`)

Running list of changes wanted in this fork, collected while driving Character Creator 5.2 for the PIQSIQ
character upgrade. Fixes are batched: each batch needs the plugin installer re-run (administrator), a Character
Creator restart and a Claude Code restart, so nothing here is applied one item at a time.

Policy reminder (owner, 2026-11-19): the UI tools refuse only what spends money or commits to paying, plus
accepting terms or agreements. Everything else may be pressed.

## Allowlist: exact controls to allow although a refusal word matches

Each entry is one exact control (window, objectName, visible text). An allowlist entry never widens a word rule;
a control with a similar name stays refused. Model: the existing Body Wrap "points" exception in
`cc5-plugin/cc5_uiclick.py`.

| Status | Window / panel | objectName | Text | Refused because | Why it is safe |
|---|---|---|---|---|---|
| pending | Modify > Expression Wrinkles | `qtActiveWrinkleCheckBox` | Activate Expression Wrinkles | "activate" (licence activation) | Turns the wrinkle system on for the open character. No licence, no cost. |

## Denylist: words or controls to refuse that are not refused yet

| Status | Rule | Why |
|---|---|---|
| done `b019d2e` | Window text with cost, deduct, charge, charging, spend, spent | A "This will cost 50 points. Continue?" box had no money word, so its OK could be pressed. |
| to check | Real wording of Character Creator's points-spending and AI Studio dialogs | Nobody has seen one yet. Add the exact wording when one appears. |

## Over-broad rules to narrow

| Status | Rule | Problem | Proposed change |
|---|---|---|---|
| pending | "activat" stem on buttons and windows | Catches ordinary feature switches such as "Activate Expression Wrinkles" and "Activate Physics". | Count it as money only next to licence, product, serial, key or online wording; otherwise allow. Until then use allowlist entries. |
| pending | Whole word "order" | Refuses harmless labels such as "Sort Order". | Refuse "order" only as a verb or with now / place / confirm / summary; allow "sort order", "draw order", "order by". |

## Missing capabilities

| Status | Need | Seen when | Idea |
|---|---|---|---|
| pending | Set a spin box or slider value by objectName | Modify > Character > SubD Levels > Render stays at 0 after subdividing; only the viewport level can be set. | New `set_ui_value` tool (QSpinBox / QDoubleSpinBox / QSlider / QComboBox), same refusals as the button tool. |
| pending | Load expression-wrinkle presets | `apply_preset` accepts `.rlwrinkle` since `ad88cc8`, but `RFileIO.LoadFile` reports an error for it. | Find the RLPy wrinkle call or drive the Expression Wrinkles tab; otherwise remove the extension again so the tool does not promise it. |
| pending | Tool descriptions | `click_ui_button` still lists delete, login and update as refused in the description the client shows. | Regenerate or correct the description strings after the money-only change. |

## Security items from the code review (2026-11-19)

| Status | Item | Note |
|---|---|---|
| open | Unguarded `/workflow/menu/trigger`, `/workflow/dialog/native`, `/workflow/dialog/file_fill` can reach Script > Load Python | Reachable only by direct HTTP, not as MCP tools. Close by putting them behind the same gate as `exec_python`. |
| open | No authentication on the loopback bridge | Any local program can call it. Consider a per-start token passed to the MCP server. |
| open | 9 dependency advisories in the MCP toolkit's web-server packages | Fixes exist; updating changes the lockfile that was reviewed. |

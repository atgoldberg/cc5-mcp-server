# Fork fix list (branch `piqsiq`)

Running list of changes wanted in this fork, collected while driving Character Creator 5.2 for the PIQSIQ
character upgrade. Fixes are batched: each batch needs the plugin installer re-run (administrator), a Character
Creator restart and a Claude Code restart, so nothing here is applied one item at a time.

Policy reminder (owner, 2026-11-19): the UI tools refuse only what spends money or commits to paying, plus
accepting terms or agreements. Everything else may be pressed.

## Allowlist: exact controls to allow although a refusal word matches

Each entry is one exact control (window, objectName, visible text). An allowlist entry never widens a word rule;
a control with a similar name stays refused. The table in the code is `ALLOWLIST` in
`cc5-plugin/cc5_uiclick.py` (it also holds the four Body Wrap "points" entries of 2026-10-31); `click_ui_button`
and `set_ui_value` both read it.

| Status | Window / panel | objectName | Text | Refused because | Why it is safe |
|---|---|---|---|---|---|
| done `this batch` | Modify > Expression Wrinkles (main window, objectName `MainWindow`) | `qtActiveWrinkleCheckBox` | Activate Expression Wrinkles | "activate" (licence activation) | Turns the wrinkle system on for the open character. No licence, no cost. |

## Denylist: words or controls to refuse that are not refused yet

| Status | Rule | Why |
|---|---|---|
| done `b019d2e` | Window text with cost, deduct, charge, charging, spend, spent | A "This will cost 50 points. Continue?" box had no money word, so its OK could be pressed. |
| to check | Real wording of Character Creator's points-spending and AI Studio dialogs | Nobody has seen one yet. Add the exact wording when one appears. |

## Over-broad rules to narrow

| Status | Rule | Problem | Proposed change |
|---|---|---|---|
| done `this batch` | "activat" stem on buttons and windows | Catches ordinary feature switches such as "Activate Expression Wrinkles" and "Activate Physics". | Done for controls (buttons, menu entries, tabs, input widgets): refused only next to licence, product, serial, key, online, purchase, trial, subscription, account or code wording, or when the label names nothing else ("Activate", "Activation", "Deactivate", "Activate now"). Window text is unchanged on purpose: any "activat" in a window still counts as money. |
| done `this batch` | Whole word "order" | Refuses harmless labels such as "Sort Order". | Done: not refused in "sort order", "draw order", "render order", "layer order", "order by", "in order to" (inside one label); still refused in order now / place order / your order / order summary / order ID and in the plural "orders". |

## Missing capabilities

| Status | Need | Seen when | Idea |
|---|---|---|---|
| done `this batch` | Set a spin box or slider value by objectName | Modify > Character > SubD Levels > Render stays at 0 after subdividing; only the viewport level can be set. | New `set_ui_value` tool (route `/ui/value`): QSpinBox / QDoubleSpinBox / QSlider / QComboBox / QLineEdit / check box, by objectName plus `ancestor`, same refusals as the button tool. Not yet run against a live Character Creator. |
| done `this batch` | Load expression-wrinkle presets | `apply_preset` accepts `.rlwrinkle` since `ad88cc8`, but `RFileIO.LoadFile` reports an error for it. | The extension was removed again, so the tool does not promise it. |
| done `this batch` | Tool descriptions | `click_ui_button` still lists delete, login and update as refused in the description the client shows. | The description strings and the README rows were rewritten for the money-only rule, the two narrowed words and the allowlist. A client that still shows the old text is running an old build: rebuild (`npm run build`) and restart it. |
| done `this batch` | `export_fbx` reports "This operation was aborted" on a long export | A real export took longer than the 30 s request limit; Character Creator finished and wrote the files. | `export_fbx`, `export_obj` and `save_project` wait 300 s (bridge and MCP server); a missing answer now says that Character Creator may still be working and to check the output folder. |

Note: expression wrinkles are not loaded as a preset file; they are switched on from the Modify panel's Expression Wrinkles tab (`select_ui_tab`, then `set_ui_value` or `click_ui_button` on `qtActiveWrinkleCheckBox`).

## Security items from the code review (2026-11-19)

| Status | Item | Note |
|---|---|---|
| open | Unguarded `/workflow/menu/trigger`, `/workflow/dialog/native`, `/workflow/dialog/file_fill` can reach Script > Load Python | Reachable only by direct HTTP, not as MCP tools. Close by putting them behind the same gate as `exec_python`. |
| open | No authentication on the loopback bridge | Any local program can call it. Consider a per-start token passed to the MCP server. |
| open | 9 dependency advisories in the MCP toolkit's web-server packages | Fixes exist; updating changes the lockfile that was reviewed. |

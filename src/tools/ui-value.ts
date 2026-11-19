/**
 * set_ui_value: read ONE input widget of a CC5 window, or set its value (Qt setters, no mouse, no keyboard).
 *
 * Made on 2026-11-19: Modify > Character > SubD Levels > Render stayed at 0 after subdividing; the two SubD
 * boxes are spin boxes with the same objectName (qtSpinBox), click_ui_button presses buttons only, and no
 * tool could type a number. What may be set is decided by the bridge (cc5-plugin/cc5_uivalue.py), because
 * any local program can call it; this tool only forwards the request and shows the answer.
 */

import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CC5Bridge } from "../cc5-bridge.js";
import type { UiValue, UiValueArgs, UiValueReply, UiValueResult, UiValueWidget } from "../types.js";
import { bridgeCallRich, pngContent, textContent, type ToolContent } from "../util.js";
import { describeWindow, failureContent, refusedContent, runUiJob, stillRunningText, windowImages, type WaitOptions } from "./ui-common.js";

const DEFAULT_WAIT_MS = 500;
const EXTRA_WAIT_SECONDS = 60;

const nameField = z.string().min(1).max(256);

function valueText(value: UiValue | undefined, hidden?: boolean): string {
  if (hidden) return "(text not shown)";
  if (value === null || value === undefined) return "(none)";
  if (typeof value === "object") return `${value.index}: '${value.text ?? ""}'`;
  return typeof value === "string" ? `'${value}'` : String(value);
}

function widgetName(widget: UiValueWidget | undefined): string {
  if (!widget) return "the widget";
  const name = widget.object_name ? `[${widget.object_name}]` : "(no objectName)";
  return `${name} <${widget.class ?? "?"}>${widget.kind ? ` ${widget.kind}` : ""}`;
}

export function formatValueRead(reply: UiValueReply): string {
  const w = reply.widget ?? {};
  const lines: string[] = [
    `${widgetName(w)} in '${reply.window ?? "?"}' (read-only: nothing was changed).`,
    `Value: ${valueText(w.value, w.value_hidden)}${w.value_hidden && w.text_length !== undefined ? ` (${w.text_length} characters)` : ""}`,
  ];
  if (w.minimum !== undefined && w.minimum !== null) {
    const step = w.single_step !== undefined ? `, step ${w.single_step}` : "";
    const decimals = w.decimals !== undefined ? `, ${w.decimals} decimal(s)` : "";
    lines.push(`Range: ${w.minimum} to ${w.maximum}${step}${decimals}`);
  }
  if (w.items) {
    lines.push(`Items (${w.count ?? w.items.length}${w.editable ? ", editable" : ""}):`);
    const current = typeof w.value === "object" && w.value !== null ? w.value.index : -1;
    w.items.forEach((item, index) => lines.push(`  ${index === current ? "*" : "-"} ${index}: '${item}'`));
  }
  if (w.text) lines.push(`Text: '${w.text}'`);
  if (w.labels && w.labels.length > 0) lines.push(`Labels: ${w.labels.map((l) => `'${l}'`).join(", ")}`);
  if (w.tooltip) lines.push(`Tool tip: '${w.tooltip}'`);
  if (w.max_length !== undefined) lines.push(`At most ${w.max_length} characters.`);
  if (w.read_only) lines.push("The box is read-only.");
  if (w.enabled === false) lines.push("The widget is disabled (greyed out): it cannot be set now.");
  if (w.path) lines.push(`Sits in: ${w.path}`);
  if (w.note) lines.push(`(${w.note})`);
  if (reply.hidden_skipped) lines.push(`(${reply.hidden_skipped} hidden widget(s) with the same name were left out.)`);
  return lines.join("\n");
}

export function formatValueResult(result: UiValueResult): string {
  const lines: string[] = [];
  const before = valueText(result.value_before, result.value_before_hidden);
  const after = valueText(result.value_after, result.value_after_hidden);
  if (result.success) {
    lines.push(`Set ${widgetName(result.widget)} in '${result.window ?? "?"}' to ${after} (before: ${before}).`);
  } else {
    lines.push(`Failed: ${result.error ?? "the value was not set"}`);
    if (result.widget) lines.push(`Value before: ${before}, after: ${after}.`);
  }
  if (result.note) lines.push(result.note);
  if (result.minimum !== undefined && result.minimum !== null) lines.push(`Range: ${result.minimum} to ${result.maximum}.`);
  if (result.signals_sent && result.signals_sent.length > 0) lines.push(`Signals sent after the setter: ${result.signals_sent.join(", ")}.`);
  if (result.hidden_skipped) lines.push(`(${result.hidden_skipped} hidden widget(s) with the same name were left alone.)`);
  if (result.window_open === false) lines.push("The window closed after the change.");
  if (result.screenshot_error) lines.push(`No picture of the window: ${result.screenshot_error}`);
  const dialogs = result.dialogs ?? [];
  if (result.window !== undefined || dialogs.length > 0) {
    lines.push(dialogs.length === 0
      ? "Open dialogs after the change: none."
      : `Open dialogs after the change (none was answered):\n${dialogs.map((d) => `  - ${describeWindow(d)}`).join("\n")}`);
  }
  return lines.join("\n");
}

export function registerUiValueTools(server: McpServer, bridge: CC5Bridge, wait: WaitOptions = {}): void {
  server.tool(
    "set_ui_value",
    "Read ONE input widget inside a CC5 window, dialog or dock panel, or set its value from inside CC5 (Qt " +
      "setters that send the normal change signals, no mouse, no keyboard): QSpinBox / QDoubleSpinBox and " +
      "subclasses (value: a number), QSlider (a whole number), QComboBox (the exact item text as a string, or " +
      "the item index as a number), QLineEdit (a string), QCheckBox / radio button (true / false). Name the " +
      "window (title, case-insensitive, or objectName, as for click_ui_button) and the widget by its exact " +
      "object_name (find names with find_ui_widgets); when several visible widgets share the name, give " +
      "ancestor: the objectName or class of a widget only one of them sits in (the SubD level boxes are both " +
      "qtSpinBox, inside qtRenderComboSpinBox and qtPreviewComboSpinBox). First call it with read_only=true: " +
      "that only READS the kind, current value, minimum / maximum, step and item list, and changes nothing " +
      "(text typed into a box is shown only when it is a plain number). It sets one value and does nothing " +
      "else: it never presses a button, answers a dialog or opens a menu. CC5 refuses, and changes nothing, " +
      "when: no or more than one VISIBLE input widget matches; the widget is disabled, hidden, read-only or a " +
      "password box; the value has the wrong type or is outside the minimum / maximum (nothing is clamped: the " +
      "range is reported); the combo item is not there, ambiguous or disabled; the widget's text, objectName, " +
      "tool tip or label (or the combo item) is about spending money -- points, buy, purchase, checkout, cart, " +
      "credit, subscribe, pay, price, upgrade, trial, licence, 'order' (but not 'sort order', 'draw order', " +
      "'render order', 'layer order', 'order by'), 'activate' next to a licence / product / serial / key / " +
      "online / account word or standing alone (a feature switch such as 'Activate Physics' or 'Activate " +
      "Expression Wrinkles' IS set) (or ポイント 購入 ライセンス クレジット 支払) -- or about accepting terms / " +
      "an agreement; a window about those (purchase, licence, activation, terms) is open; a modal window is " +
      "open and the widget is not in it. After the change it waits wait_ms, then returns the value before " +
      "and after, a picture of the window and the dialogs that are open (never answered). Do not use it to " +
      "get past a refusal of another tool.",
    {
      window: nameField.describe("Title (case-insensitive) or objectName of the CC5 window, dialog or dock panel"),
      object_name: nameField.describe("Exact objectName of the input widget"),
      ancestor: nameField.optional().describe("objectName or class of a widget it sits in (needed when several visible widgets share object_name)"),
      value: z.union([z.number(), z.string().max(1024), z.boolean()]).optional()
        .describe("The value to set: number (spin box, slider, or a combo item's index), string (line edit text, or a combo item's exact text), true / false (check box, radio button). Required unless read_only"),
      read_only: z.boolean().optional().describe("Only read the widget (kind, value, range, items); change nothing (default false)"),
      wait_ms: z.number().int().min(200).max(15000).optional().describe(`Wait after the change before the picture (default ${DEFAULT_WAIT_MS})`),
      screenshot: z.boolean().optional().describe("Return a PNG of the window and of each open dialog after a change (default true)"),
      max_width: z.number().int().min(200).max(2400).optional().describe("Scale the window PNG down to this width (default 900)"),
    },
    async (args) => {
      if (args.value === undefined && args.read_only !== true) {
        return { content: failureContent("give value (or read_only=true to only read the widget)") };
      }
      if (typeof args.value === "number" && !Number.isFinite(args.value)) {
        return { content: failureContent("value must be a finite number") };
      }
      const body: UiValueArgs = { ...args };
      const seconds = Math.ceil((args.wait_ms ?? DEFAULT_WAIT_MS) / 1000) + EXTRA_WAIT_SECONDS;
      return bridgeCallRich(async (): Promise<ToolContent[]> => {
        const reply = await bridge.uiSetValue(body);
        if (reply.success && reply.read_only) return [textContent(formatValueRead(reply))];
        const run = await runUiJob<UiValueResult>(bridge, async () => reply, seconds, wait);
        if ("refused" in run) return refusedContent(run.refused);
        if (!run.outcome.finished) return [textContent(stillRunningText(run.jobId, seconds, run.outcome.status))];
        const result = run.outcome.result ?? { success: false, error: "the job returned nothing" };
        const content: ToolContent[] = [textContent(formatValueResult(result))];
        if (result.png_base64) content.push(pngContent(result.png_base64));
        content.push(...windowImages(result.dialogs));
        return content;
      }, (content) => content);
    },
  );
}

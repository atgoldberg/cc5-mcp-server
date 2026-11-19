/**
 * select_ui_tab: list the tabs of a CC5 tab widget, or bring ONE tab to the front (Qt setCurrentIndex(), no mouse).
 *
 * Made on 2026-11-19: the "Subdivide" button sits on a page of the Modify panel's tab widget
 * (qtAttributeRootTab) that was not the front one, click_ui_button refuses hidden buttons, and no tool
 * could switch the tab. What may be selected is decided by the bridge (cc5-plugin/cc5_uitab.py), because
 * any local program can call it; this tool only forwards the request and shows the answer.
 */

import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import type { CC5Bridge } from "../cc5-bridge.js";
import type { UiTabArgs, UiTabInfo, UiTabReply, UiTabResult } from "../types.js";
import { bridgeCallRich, pngContent, textContent, type ToolContent } from "../util.js";
import { describeWindow, failureContent, refusedContent, runUiJob, stillRunningText, windowImages, type WaitOptions } from "./ui-common.js";

const DEFAULT_WAIT_MS = 500;
const EXTRA_WAIT_SECONDS = 60;

const nameField = z.string().min(1).max(256);

function tabText(tab: UiTabInfo | null | undefined): string {
  if (!tab) return "(none)";
  const bits = [`${tab.index}:`, tab.text ? `'${tab.text}'` : "(no text)"];
  if (tab.tooltip) bits.push(`tip '${tab.tooltip}'`);
  if (tab.page) bits.push(`page [${tab.page}]`);
  if (tab.enabled === false) bits.push("(disabled)");
  if (tab.visible === false) bits.push("(hidden)");
  return bits.join(" ");
}

export function formatTabList(reply: UiTabReply): string {
  const holders = reply.tab_widgets ?? [];
  const lines: string[] = [
    `${reply.count ?? holders.length} visible tab widget(s) in '${reply.window ?? "?"}' (read-only: nothing was changed).`,
  ];
  for (const holder of holders) {
    const name = holder.object_name ? `[${holder.object_name}]` : "(no objectName)";
    const state = holder.enabled === false ? ", disabled" : "";
    lines.push(`${name} <${holder.class ?? "?"}>: ${holder.count ?? holder.tabs?.length ?? 0} tab(s), current index ${holder.current_index ?? "?"}${state}`);
    for (const tab of holder.tabs ?? []) {
      lines.push(`  ${tab.index === holder.current_index ? "*" : "-"} ${tabText(tab)}`);
    }
    if (holder.note) lines.push(`  (${holder.note})`);
  }
  if (reply.hidden_skipped) lines.push(`(${reply.hidden_skipped} hidden tab widget(s) were left out.)`);
  if (holders.length > 0) lines.push("Select one with index, text or tooltip (and tab_widget when there are several).");
  return lines.join("\n");
}

export function formatTabResult(result: UiTabResult): string {
  const lines: string[] = [];
  if (result.success) {
    const holder = result.tab_widget?.object_name ? `[${result.tab_widget.object_name}]` : "the tab widget";
    lines.push(`Selected tab ${tabText(result.selected)} of ${holder} in '${result.window ?? "?"}' ` +
      `(index before: ${result.index_before ?? "?"}, after: ${result.index_after ?? "?"}).`);
  } else {
    lines.push(`Failed: ${result.error ?? "the tab was not selected"}`);
    if (result.index_before !== undefined) {
      lines.push(`Index before: ${result.index_before}, after: ${result.index_after ?? "?"}.`);
    }
  }
  if (result.note) lines.push(result.note);
  if (result.tabs && result.tabs.length > 0) {
    lines.push(`Tabs:\n${result.tabs.map((t) => `  ${t.index === result.index_after ? "*" : "-"} ${tabText(t)}`).join("\n")}`);
  }
  if (result.window_open === false) lines.push("The window closed after the tab switch.");
  if (result.screenshot_error) lines.push(`No picture of the window: ${result.screenshot_error}`);
  const dialogs = result.dialogs ?? [];
  if (result.window !== undefined || dialogs.length > 0) {
    lines.push(dialogs.length === 0
      ? "Open dialogs after the tab switch: none."
      : `Open dialogs after the tab switch (none was answered):\n${dialogs.map((d) => `  - ${describeWindow(d)}`).join("\n")}`);
  }
  return lines.join("\n");
}

export function registerUiTabTools(server: McpServer, bridge: CC5Bridge, wait: WaitOptions = {}): void {
  server.tool(
    "select_ui_tab",
    "List the tabs of a tab widget (QTabWidget / QTabBar) inside a CC5 window, dialog or dock panel, or bring " +
      "ONE tab to the front from inside CC5 (Qt setCurrentIndex(), no mouse), e.g. to reach a button that " +
      "click_ui_button calls hidden because its tab is not the front one. Name the window (title, " +
      "case-insensitive, or objectName, as for click_ui_button) and, when it shows more than one tab widget, " +
      "tab_widget (its exact objectName, e.g. qtAttributeRootTab for the Modify panel). First call it with " +
      "list_only=true (or with no index / text / tooltip): that only READS each tab widget's objectName, class, " +
      "current index and every tab's index, text, tool tip, enabled and visible state, and changes nothing. " +
      "Then give exactly ONE of index (0-based), text or tooltip (icon-only tabs have no text). It selects a " +
      "tab and does nothing else: it never presses a button, answers a dialog or opens a menu. CC5 refuses, " +
      "and changes nothing, when: no or more than one VISIBLE tab widget matches; no or more than one tab " +
      "matches; the tab is disabled or hidden; its text or tool tip mentions points, buy, purchase, delete, " +
      "remove, licence, activate, upgrade, credit, subscribe, pay (or ポイント 購入 削除 ライセンス クレジット " +
      "支払), or login / update / terms / trial; a licence / purchase / login window is open; a modal window " +
      "is open and the tab widget is not in it. After the switch it waits wait_ms, then returns the index " +
      "before and after, the tab labels, a picture of the window and the dialogs that are open (never " +
      "answered). Do not use it to get past a refusal of another tool.",
    {
      window: nameField.describe("Title (case-insensitive) or objectName of the CC5 window, dialog or dock panel"),
      tab_widget: nameField.optional().describe("Exact objectName of the QTabWidget / QTabBar (needed when the window shows several)"),
      index: z.number().int().min(0).max(999).optional().describe("0-based index of the tab to select"),
      text: nameField.optional().describe("Exact text of the tab to select (case and the & marker are ignored)"),
      tooltip: nameField.optional().describe("Exact tool tip of the tab to select (case is ignored); for icon-only tabs"),
      list_only: z.boolean().optional().describe("Only list the tab widgets and their tabs; change nothing (default false)"),
      wait_ms: z.number().int().min(200).max(15000).optional().describe(`Wait after the switch before the picture (default ${DEFAULT_WAIT_MS})`),
      screenshot: z.boolean().optional().describe("Return a PNG of the window and of each open dialog after a switch (default true)"),
      max_width: z.number().int().min(200).max(2400).optional().describe("Scale the window PNG down to this width (default 900)"),
    },
    async (args) => {
      const given = [args.index, args.text, args.tooltip].filter((v) => v !== undefined).length;
      if (given > 1) {
        return { content: failureContent("give only one of index, text, tooltip") };
      }
      const body: UiTabArgs = { ...args };
      const seconds = Math.ceil((args.wait_ms ?? DEFAULT_WAIT_MS) / 1000) + EXTRA_WAIT_SECONDS;
      return bridgeCallRich(async (): Promise<ToolContent[]> => {
        const reply = await bridge.uiSelectTab(body);
        if (reply.success && reply.listed) return [textContent(formatTabList(reply))];
        const run = await runUiJob<UiTabResult>(bridge, async () => reply, seconds, wait);
        if ("refused" in run) return refusedContent(run.refused);
        if (!run.outcome.finished) return [textContent(stillRunningText(run.jobId, seconds, run.outcome.status))];
        const result = run.outcome.result ?? { success: false, error: "the job returned nothing" };
        const content: ToolContent[] = [textContent(formatTabResult(result))];
        if (result.png_base64) content.push(pngContent(result.png_base64));
        content.push(...windowImages(result.dialogs));
        return content;
      }, (content) => content);
    },
  );
}

/**
 * select_ui_tab: forwards to /ui/tab; shows the list as it is, or waits for the job and shows the result,
 * the window picture and the dialogs. What may be selected is decided by the bridge
 * (tests/python/test_ui_tab.py).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { registerUiTabTools, formatTabList, formatTabResult } from "../../src/tools/ui-tab.js";
import { createMockServer } from "../helpers/mock-server.js";

function makeBridge() {
  return { uiSelectTab: vi.fn(), uiWaitJob: vi.fn(), uiClick: vi.fn() };
}

let bridge: ReturnType<typeof makeBridge>;
let server: ReturnType<typeof createMockServer>;

beforeEach(() => {
  bridge = makeBridge();
  server = createMockServer();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  registerUiTabTools(server as any, bridge as any);
});

const call = (args: Record<string, unknown>) => server.getRegisteredTool("select_ui_tab")(args);
const texts = (result: { content: Array<{ type: string; text?: string }> }) =>
  result.content.filter((c) => c.type === "text").map((c) => c.text).join("\n");
const images = (result: { content: Array<{ type: string }> }) => result.content.filter((c) => c.type === "image");
const schema = () => server.tool.mock.calls.find((c: unknown[]) => c[0] === "select_ui_tab")[2];

const LISTING = {
  success: true, listed: true, window: "Character Creator 5", count: 1,
  tab_widgets: [{
    object_name: "qtAttributeRootTab", class: "QTabWidget", current_index: 0, count: 3, enabled: true,
    tabs: [
      { index: 0, text: "", tooltip: "Morph", enabled: true, visible: true, page: "qtMorphPage" },
      { index: 1, text: "", tooltip: "Modify", enabled: false, visible: true },
      { index: 2, text: "Motion", tooltip: "", enabled: true, visible: false },
    ],
  }],
  hidden_skipped: 2,
};

describe("select_ui_tab – registration", () => {
  it("registers one tool whose description names what it does not do and the refusals", () => {
    expect(server.tool).toHaveBeenCalledTimes(1);
    const description = server.tool.mock.calls[0][1] as string;
    for (const word of ["setCurrentIndex", "list_only", "changes nothing", "never presses a button", "disabled or hidden",
      "points", "buy", "purchase", "order", "checkout", "cart", "credit", "subscribe", "pay", "price", "upgrade",
      "trial", "activate", "licence", "terms", "agreement",
      "ポイント", "購入", "ライセンス", "クレジット", "支払", "modal", "tab_widget"]) {
      expect(description).toContain(word);
    }
    for (const gone of ["delete", "remove", "login", "update", "削除"]) expect(description).not.toContain(gone);
  });

  it("schema: window is required, names are bounded, index is 0-999, wait_ms is 200-15000", () => {
    const shape = schema();
    expect(Object.keys(shape).sort()).toEqual(
      ["index", "list_only", "max_width", "screenshot", "tab_widget", "text", "tooltip", "wait_ms", "window"]);
    expect(shape.window.safeParse("").success).toBe(false);
    expect(shape.window.safeParse("Modify").success).toBe(true);
    expect(shape.tab_widget.safeParse("x".repeat(257)).success).toBe(false);
    expect(shape.tooltip.safeParse("x".repeat(257)).success).toBe(false);
    expect(shape.index.safeParse(-1).success).toBe(false);
    expect(shape.index.safeParse(1.5).success).toBe(false);
    expect(shape.index.safeParse(1000).success).toBe(false);
    expect(shape.index.safeParse(0).success).toBe(true);
    expect(shape.list_only.safeParse("yes").success).toBe(false);
    expect(shape.wait_ms.safeParse(100).success).toBe(false);
    expect(shape.wait_ms.safeParse(15001).success).toBe(false);
    expect(shape.wait_ms.safeParse(2000).success).toBe(true);
  });
});

describe("select_ui_tab – calls", () => {
  it("refuses two selectors before anything is sent", async () => {
    expect(texts(await call({ window: "Modify", index: 0, tooltip: "Modify" }))).toContain("give only one of index, text, tooltip");
    expect(bridge.uiSelectTab).not.toHaveBeenCalled();
  });

  it("list_only shows the list and waits for no job", async () => {
    bridge.uiSelectTab.mockResolvedValue(LISTING);
    const args = { window: "Character Creator 5", list_only: true };
    const result = await call(args);
    expect(bridge.uiSelectTab).toHaveBeenCalledWith(args);
    expect(bridge.uiWaitJob).not.toHaveBeenCalled();
    const text = texts(result);
    expect(text).toContain("1 visible tab widget(s) in 'Character Creator 5' (read-only: nothing was changed).");
    expect(text).toContain("[qtAttributeRootTab] <QTabWidget>: 3 tab(s), current index 0");
    expect(text).toContain("* 0: (no text) tip 'Morph' page [qtMorphPage]");
    expect(text).toContain("- 1: (no text) tip 'Modify' (disabled)");
    expect(text).toContain("- 2: 'Motion' (hidden)");
    expect(text).toContain("2 hidden tab widget(s) were left out");
    expect(images(result)).toHaveLength(0);
  });

  it("selects, waits for the job and returns the text, the window picture and the dialog pictures", async () => {
    bridge.uiSelectTab.mockResolvedValue({ success: true, job_id: "tab-1", state: "queued" });
    bridge.uiWaitJob.mockResolvedValue({
      finished: true,
      result: {
        success: true, window: "Character Creator 5", tab_widget: { object_name: "qtAttributeRootTab", class: "QTabWidget" },
        index_before: 0, index_after: 1, selected: { index: 1, text: "", tooltip: "Modify" },
        previous: { index: 0, text: "", tooltip: "Morph" },
        tabs: [{ index: 0, text: "", tooltip: "Morph" }, { index: 1, text: "", tooltip: "Modify" }],
        window_open: true, png_base64: "V0lO",
        dialogs: [{ title: "Note", text: "Loading", buttons: ["OK"], png_base64: "RElB" }],
      },
    });
    const args = { window: "Character Creator 5", tab_widget: "qtAttributeRootTab", tooltip: "Modify", wait_ms: 1500 };
    const result = await call(args);
    expect(bridge.uiSelectTab).toHaveBeenCalledTimes(1);
    expect(bridge.uiSelectTab).toHaveBeenCalledWith(args);
    expect(bridge.uiWaitJob).toHaveBeenCalledWith("tab-1", { timeoutMs: 62_000 });
    expect(bridge.uiClick).not.toHaveBeenCalled();
    const text = texts(result);
    expect(text).toContain("Selected tab 1: (no text) tip 'Modify' of [qtAttributeRootTab] in 'Character Creator 5' (index before: 0, after: 1).");
    expect(text).toContain("  * 1: (no text) tip 'Modify'");
    expect(text).toContain("Open dialogs after the tab switch (none was answered):");
    expect(text).toContain("- 'Note': Loading | buttons: OK");
    expect(images(result)).toEqual([
      { type: "image", data: "V0lO", mimeType: "image/png" },
      { type: "image", data: "RElB", mimeType: "image/png" },
    ]);
  });

  it("shows CC5's refusal as it is (nothing was changed)", async () => {
    bridge.uiSelectTab.mockResolvedValue({ success: false, error: "refused: the tab 2: 'Buy' mentions 'buy'. ... Ask the owner" });
    const text = texts(await call({ window: "Modify", index: 2 }));
    expect(text).toBe("Failed: refused: the tab 2: 'Buy' mentions 'buy'. ... Ask the owner");
    expect(bridge.uiWaitJob).not.toHaveBeenCalled();
  });

  it("reports a job that failed inside CC5 and a job that is still running", async () => {
    bridge.uiSelectTab.mockResolvedValue({ success: true, job_id: "tab-2" });
    bridge.uiWaitJob.mockResolvedValueOnce({
      finished: true,
      result: { success: false, error: "the tab 1: (no text) tip 'Modify' is disabled (greyed out) and cannot be selected now" },
    });
    const failed = await call({ window: "Modify", index: 1 });
    expect(texts(failed)).toBe("Failed: the tab 1: (no text) tip 'Modify' is disabled (greyed out) and cannot be selected now");
    expect(images(failed)).toHaveLength(0);
    bridge.uiWaitJob.mockResolvedValueOnce({ finished: false, status: { success: true, state: "running" } });
    expect(texts(await call({ window: "Modify", index: 1 }))).toContain("Still running after 61s (job tab-2)");
  });

  it("turns a lost bridge into one readable text", async () => {
    bridge.uiSelectTab.mockRejectedValue(new Error("tunnel down"));
    expect(texts(await call({ window: "Modify", index: 1 }))).toContain("CC5 bridge error: tunnel down");
  });
});

describe("formatTabList / formatTabResult", () => {
  it("an empty list", () => {
    expect(formatTabList({ success: true, listed: true, window: "Empty", count: 0, tab_widgets: [] }))
      .toBe("0 visible tab widget(s) in 'Empty' (read-only: nothing was changed).");
  });

  it("a switch that did not take, a note, a closed window and a missing picture", () => {
    const text = formatTabResult({
      success: false, error: "asked for tab 3 but the current tab is 0", window: "Modify",
      index_before: 0, index_after: 0, note: "look first", window_open: false,
      screenshot_error: "grab returned an empty image", dialogs: [],
    });
    expect(text).toContain("Failed: asked for tab 3 but the current tab is 0");
    expect(text).toContain("Index before: 0, after: 0.");
    expect(text).toContain("look first");
    expect(text).toContain("The window closed after the tab switch.");
    expect(text).toContain("No picture of the window: grab returned an empty image");
    expect(text).toContain("Open dialogs after the tab switch: none.");
  });

  it("a failure without details", () => {
    expect(formatTabResult({ success: false })).toBe("Failed: the tab was not selected");
  });
});

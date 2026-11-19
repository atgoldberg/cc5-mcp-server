/**
 * set_ui_value: forwards to /ui/value; shows the widget as it is (read_only), or waits for the job and shows
 * the value before and after, the window picture and the dialogs. What may be set is decided by the bridge
 * (tests/python/test_ui_value.py).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { registerUiValueTools, formatValueRead, formatValueResult } from "../../src/tools/ui-value.js";
import { createMockServer } from "../helpers/mock-server.js";

function makeBridge() {
  return { uiSetValue: vi.fn(), uiWaitJob: vi.fn(), uiClick: vi.fn() };
}

let bridge: ReturnType<typeof makeBridge>;
let server: ReturnType<typeof createMockServer>;

beforeEach(() => {
  bridge = makeBridge();
  server = createMockServer();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  registerUiValueTools(server as any, bridge as any);
});

const call = (args: Record<string, unknown>) => server.getRegisteredTool("set_ui_value")(args);
const texts = (result: { content: Array<{ type: string; text?: string }> }) =>
  result.content.filter((c) => c.type === "text").map((c) => c.text).join("\n");
const images = (result: { content: Array<{ type: string }> }) => result.content.filter((c) => c.type === "image");
const schema = () => server.tool.mock.calls.find((c: unknown[]) => c[0] === "set_ui_value")[2];

const SPIN = { window: "MainWindow", object_name: "qtSpinBox", ancestor: "qtRenderComboSpinBox" };

describe("set_ui_value – registration", () => {
  it("registers one tool whose description names the widgets, what it does not do and the refusals", () => {
    expect(server.tool).toHaveBeenCalledTimes(1);
    const description = server.tool.mock.calls[0][1] as string;
    for (const word of ["QSpinBox", "QDoubleSpinBox", "QSlider", "QComboBox", "QLineEdit", "QCheckBox", "radio button",
      "read_only", "changes nothing", "never presses a button", "ancestor", "qtRenderComboSpinBox",
      "outside the minimum / maximum", "nothing is clamped", "disabled, hidden, read-only", "password",
      "points", "buy", "purchase", "checkout", "cart", "credit", "subscribe", "pay", "price", "upgrade", "trial",
      "licence", "terms", "agreement", "'order' (but not 'sort order'", "'activate' next to a licence",
      "'Activate Expression Wrinkles' IS set", "ポイント", "購入", "ライセンス", "クレジット", "支払", "modal"]) {
      expect(description).toContain(word);
    }
    for (const gone of ["delete", "remove", "login", "update", "削除"]) expect(description).not.toContain(gone);
  });

  it("schema: the exact argument names; names are bounded; value is a number, a string or a boolean", () => {
    const shape = schema();
    expect(Object.keys(shape).sort()).toEqual(
      ["ancestor", "max_width", "object_name", "read_only", "screenshot", "value", "wait_ms", "window"]);
    expect(shape.window.safeParse("").success).toBe(false);
    expect(shape.object_name.safeParse(undefined).success).toBe(false);
    expect(shape.object_name.safeParse("qtSpinBox").success).toBe(true);
    expect(shape.ancestor.safeParse("x".repeat(257)).success).toBe(false);
    for (const good of [2, 0.5, -1, "Body", "", true, false, undefined]) expect(shape.value.safeParse(good).success).toBe(true);
    for (const bad of [null, [1], { index: 1 }, "x".repeat(1025)]) expect(shape.value.safeParse(bad).success).toBe(false);
    expect(shape.read_only.safeParse("yes").success).toBe(false);
    expect(shape.wait_ms.safeParse(100).success).toBe(false);
    expect(shape.wait_ms.safeParse(15001).success).toBe(false);
    expect(shape.wait_ms.safeParse(2000).success).toBe(true);
  });
});

describe("set_ui_value – calls", () => {
  it("refuses a call with no value (and not read_only) before anything is sent", async () => {
    expect(texts(await call({ ...SPIN }))).toContain("give value (or read_only=true");
    expect(texts(await call({ ...SPIN, read_only: false }))).toContain("give value");
    expect(texts(await call({ ...SPIN, value: Number.POSITIVE_INFINITY }))).toContain("finite number");
    expect(bridge.uiSetValue).not.toHaveBeenCalled();
  });

  it("read_only shows the widget and waits for no job", async () => {
    bridge.uiSetValue.mockResolvedValue({
      success: true, read_only: true, window: "Character Creator 5", hidden_skipped: 1,
      widget: { object_name: "qtSpinBox", class: "QSpinBoxEx", kind: "int", enabled: true, value: 0, minimum: 0, maximum: 2,
        single_step: 1, labels: ["Render"], path: "qtRenderComboSpinBox < qtSubDGroup" },
    });
    const args = { ...SPIN, read_only: true };
    const result = await call(args);
    expect(bridge.uiSetValue).toHaveBeenCalledWith(args);
    expect(bridge.uiWaitJob).not.toHaveBeenCalled();
    const text = texts(result);
    expect(text).toContain("[qtSpinBox] <QSpinBoxEx> int in 'Character Creator 5' (read-only: nothing was changed).");
    expect(text).toContain("Value: 0");
    expect(text).toContain("Range: 0 to 2, step 1");
    expect(text).toContain("Labels: 'Render'");
    expect(text).toContain("Sits in: qtRenderComboSpinBox < qtSubDGroup");
    expect(text).toContain("1 hidden widget(s) with the same name were left out");
    expect(images(result)).toHaveLength(0);
  });

  it("sets, waits for the job and returns the text, the window picture and the dialog pictures", async () => {
    bridge.uiSetValue.mockResolvedValue({ success: true, job_id: "value-1", state: "queued" });
    bridge.uiWaitJob.mockResolvedValue({
      finished: true,
      result: {
        success: true, window: "Character Creator 5", widget: { object_name: "qtSpinBox", class: "QSpinBoxEx", kind: "int" },
        requested: 2, value_before: 0, value_after: 2, changed: true, minimum: 0, maximum: 2,
        signals_sent: ["editingFinished"], window_open: true, png_base64: "V0lO",
        dialogs: [{ title: "Note", text: "Subdividing", buttons: ["OK"], png_base64: "RElB" }],
      },
    });
    const args = { ...SPIN, value: 2, wait_ms: 1500 };
    const result = await call(args);
    expect(bridge.uiSetValue).toHaveBeenCalledTimes(1);
    expect(bridge.uiSetValue).toHaveBeenCalledWith(args);
    expect(bridge.uiWaitJob).toHaveBeenCalledWith("value-1", { timeoutMs: 62_000 });
    expect(bridge.uiClick).not.toHaveBeenCalled();
    const text = texts(result);
    expect(text).toContain("Set [qtSpinBox] <QSpinBoxEx> int in 'Character Creator 5' to 2 (before: 0).");
    expect(text).toContain("Range: 0 to 2.");
    expect(text).toContain("Signals sent after the setter: editingFinished.");
    expect(text).toContain("Open dialogs after the change (none was answered):");
    expect(text).toContain("- 'Note': Subdividing | buttons: OK");
    expect(images(result)).toEqual([
      { type: "image", data: "V0lO", mimeType: "image/png" },
      { type: "image", data: "RElB", mimeType: "image/png" },
    ]);
  });

  it("passes false, 0 and an empty string through as values", async () => {
    bridge.uiSetValue.mockResolvedValue({ success: false, error: "x" });
    for (const value of [false, 0, ""]) {
      await call({ window: "w", object_name: "n", value });
      expect(bridge.uiSetValue).toHaveBeenLastCalledWith({ window: "w", object_name: "n", value });
    }
  });

  it("shows CC5's refusal as it is (nothing was changed)", async () => {
    bridge.uiSetValue.mockResolvedValue({ success: false, error: "3 is outside the range of the widget [qtSpinBox] <QSpinBoxEx> int: minimum 0, maximum 2. Nothing was set (values are never clamped)" });
    const text = texts(await call({ ...SPIN, value: 3 }));
    expect(text).toBe("Failed: 3 is outside the range of the widget [qtSpinBox] <QSpinBoxEx> int: minimum 0, maximum 2. Nothing was set (values are never clamped)");
    expect(bridge.uiWaitJob).not.toHaveBeenCalled();
  });

  it("reports a job that failed inside CC5 and a job that is still running", async () => {
    bridge.uiSetValue.mockResolvedValue({ success: true, job_id: "value-2" });
    bridge.uiWaitJob.mockResolvedValueOnce({
      finished: true,
      result: { success: false, error: "asked for 2 but the widget shows 1", widget: { object_name: "qtSpinBox", class: "QSpinBox", kind: "int" }, value_before: 1, value_after: 1 },
    });
    const failed = texts(await call({ ...SPIN, value: 2 }));
    expect(failed).toContain("Failed: asked for 2 but the widget shows 1");
    expect(failed).toContain("Value before: 1, after: 1.");
    bridge.uiWaitJob.mockResolvedValueOnce({ finished: false, status: { success: true, state: "running" } });
    expect(texts(await call({ ...SPIN, value: 2 }))).toContain("Still running after 61s (job value-2)");
  });

  it("turns a lost bridge into one readable text", async () => {
    bridge.uiSetValue.mockRejectedValue(new Error("tunnel down"));
    expect(texts(await call({ ...SPIN, value: 2 }))).toContain("CC5 bridge error: tunnel down");
  });
});

describe("formatValueRead / formatValueResult", () => {
  it("a combo box with its items, a check box and a hidden text", () => {
    const combo = formatValueRead({
      success: true, read_only: true, window: "Modify",
      widget: { object_name: "qtCombo", class: "QComboBox", kind: "combo", value: { index: 1, text: "Body" }, count: 2, items: ["Head", "Body"], editable: true, enabled: false },
    });
    expect(combo).toContain("Value: 1: 'Body'");
    expect(combo).toContain("Items (2, editable):\n  - 0: 'Head'\n  * 1: 'Body'");
    expect(combo).toContain("disabled (greyed out)");
    const check = formatValueRead({ success: true, read_only: true, window: "Modify",
      widget: { object_name: "qtActiveWrinkleCheckBox", class: "QCheckBox", kind: "check", value: false, text: "Activate Expression Wrinkles", tooltip: "Wrinkles" } });
    expect(check).toContain("Value: false");
    expect(check).toContain("Text: 'Activate Expression Wrinkles'");
    expect(check).toContain("Tool tip: 'Wrinkles'");
    const text = formatValueRead({ success: true, read_only: true, window: "Modify",
      widget: { object_name: "qtMail", class: "QLineEdit", kind: "text", value: null, value_hidden: true, text_length: 14, max_length: 40, read_only: true } });
    expect(text).toContain("Value: (text not shown) (14 characters)");
    expect(text).toContain("At most 40 characters.");
    expect(text).toContain("The box is read-only.");
  });

  it("a set text whose old text is not shown, a note, a closed window and a missing picture", () => {
    const text = formatValueResult({
      success: true, window: "Modify", widget: { object_name: "qtEdit", class: "QLineEdit", kind: "text" },
      value_before: null, value_before_hidden: true, value_after: "180", note: "look first", window_open: false,
      screenshot_error: "grab returned an empty image", dialogs: [], hidden_skipped: 2,
    });
    expect(text).toContain("Set [qtEdit] <QLineEdit> text in 'Modify' to '180' (before: (text not shown)).");
    expect(text).toContain("look first");
    expect(text).toContain("2 hidden widget(s) with the same name were left alone");
    expect(text).toContain("The window closed after the change.");
    expect(text).toContain("No picture of the window: grab returned an empty image");
    expect(text).toContain("Open dialogs after the change: none.");
  });

  it("a failure without details", () => {
    expect(formatValueResult({ success: false })).toBe("Failed: the value was not set");
  });
});

/**
 * Unit tests for the bridgeCall utility.
 */

import { describe, it, expect } from "vitest";
import { bridgeCall, bridgeCallRich, isEnvFlagEnabled } from "../src/util.js";
import { CC5StillWorkingError } from "../src/cc5-bridge.js";

describe("isEnvFlagEnabled", () => {
  it("is false when the variable is not set", () => {
    expect(isEnvFlagEnabled("CC5_TEST_FLAG", {})).toBe(false);
  });

  it.each(["1", "true", "TRUE", "yes", " Yes "])("is true for %j", (value) => {
    expect(isEnvFlagEnabled("CC5_TEST_FLAG", { CC5_TEST_FLAG: value })).toBe(true);
  });

  it.each(["", "0", "false", "no", "off", "2", "enabled"])("is false for %j", (value) => {
    expect(isEnvFlagEnabled("CC5_TEST_FLAG", { CC5_TEST_FLAG: value })).toBe(false);
  });
});

describe("bridgeCall", () => {
  it("returns formatted success text when the fn resolves", async () => {
    const result = await bridgeCall(
      () => Promise.resolve("raw value"),
      (v) => `Got: ${v}`
    );
    expect(result.content[0].text).toBe("Got: raw value");
    expect(result.content[0].type).toBe("text");
  });

  it("returns CC5 bridge error text when fn rejects with an Error", async () => {
    const result = await bridgeCall(
      () => Promise.reject(new Error("timeout")),
      () => "should not reach"
    );
    expect(result.content[0].text).toContain("CC5 bridge error: timeout");
    expect(result.content[0].text).toContain("Is CC5 running");
  });

  it("shows a long command's 'no answer yet' as it is, without asking whether CC5 is running", async () => {
    const result = await bridgeCall(
      () => Promise.reject(new CC5StillWorkingError("FBX export to D:/out/a.fbx", 300)),
      () => "should not reach"
    );
    const text = result.content[0].text;
    expect(text).toContain("No answer from CC5 after 300 s (FBX export to D:/out/a.fbx)");
    expect(text).toContain("CC5 may still be working");
    expect(text).toContain("Check the output folder");
    expect(text).not.toContain("Is CC5 running");
    expect(text).not.toContain("aborted");
    const rich = await bridgeCallRich(() => Promise.reject(new CC5StillWorkingError("saving", 310)), () => []);
    expect(rich.content).toEqual([{ type: "text", text: expect.stringContaining("Do NOT send the request again yet") }]);
  });

  it("returns CC5 bridge error text when fn rejects with a string", async () => {
    const result = await bridgeCall(
      () => Promise.reject("plain string error"),
      () => "should not reach"
    );
    expect(result.content[0].text).toContain("CC5 bridge error: plain string error");
  });

  it("returns a single content item", async () => {
    const result = await bridgeCall(
      () => Promise.resolve(42),
      (v) => `Value is ${v}`
    );
    expect(result.content).toHaveLength(1);
  });

  it("does not call formatSuccess when fn rejects", async () => {
    let called = false;
    await bridgeCall(
      () => Promise.reject(new Error("err")),
      () => { called = true; return "text"; }
    );
    expect(called).toBe(false);
  });

  it("passes the resolved value to formatSuccess", async () => {
    const data = { id: "av1", name: "Hero" };
    const result = await bridgeCall(
      () => Promise.resolve(data),
      (v) => `Avatar: ${v.name}`
    );
    expect(result.content[0].text).toBe("Avatar: Hero");
  });

  it("handles null as a successful resolved value", async () => {
    const result = await bridgeCall(
      () => Promise.resolve(null),
      (v) => (v === null ? "no value" : "has value")
    );
    expect(result.content[0].text).toBe("no value");
  });

  it("returns content array with type as literal 'text'", async () => {
    const result = await bridgeCall(
      () => Promise.resolve("ok"),
      (v) => v
    );
    expect(result.content[0].type).toBe("text");
  });
});

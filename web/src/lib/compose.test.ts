import { afterEach, describe, expect, it, vi } from "vitest";
import { isMobileDevice, linkedInComposeUrl, linkedInViaShareSheet, shareText } from "./compose";

const PIXEL = "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36";
const IPAD = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15";
const MAC = IPAD;

function device(ua: string, touchPoints = 0, share?: (data: ShareData) => Promise<void>) {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(ua);
  Object.defineProperty(navigator, "maxTouchPoints", { value: touchPoints, configurable: true });
  Object.defineProperty(navigator, "share", { value: share, configurable: true, writable: true });
}

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "share", { value: undefined, configurable: true, writable: true });
});

describe("Open LinkedIn on a phone", () => {
  it("knows phones and tablets, including an iPad that says it's a Mac", () => {
    device(PIXEL);
    expect(isMobileDevice()).toBe(true);
    device(IPAD, 5);
    expect(isMobileDevice()).toBe(true);
    device(MAC, 0);
    expect(isMobileDevice()).toBe(false);
  });

  it("uses the share sheet only on a phone that has one; the web composer link otherwise", () => {
    device(PIXEL, 5, async () => undefined);
    expect(linkedInViaShareSheet()).toBe(true);
    device(PIXEL, 5, undefined);
    expect(linkedInViaShareSheet()).toBe(false);
    device(MAC, 0, async () => undefined);
    expect(linkedInViaShareSheet()).toBe(false);
    expect(linkedInComposeUrl("Hi #AI")).toBe("https://www.linkedin.com/feed/?shareActive=true&text=Hi%20%23AI");
  });

  it("says whether the post was shared, the sheet was closed, or sharing failed", async () => {
    const share = vi.fn(async () => undefined);
    device(PIXEL, 5, share);
    expect(await shareText("The post")).toBe("shared");
    expect(share).toHaveBeenCalledWith({ text: "The post" });
    device(PIXEL, 5, async () => {
      throw new DOMException("closed", "AbortError");
    });
    expect(await shareText("x")).toBe("cancelled");
    device(PIXEL, 5, async () => {
      throw new DOMException("no gesture", "NotAllowedError");
    });
    expect(await shareText("x")).toBe("failed");
  });
});

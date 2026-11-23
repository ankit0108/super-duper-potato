import { card, desk, event } from "@/test/fixtures";
import type { Attachment } from "@/types";
import { applyEvents } from "./overlay";
import { STARTS_RUN } from "./outbox";
import { applyMedia, creditLine, mediaItems, pictureLabel, sparePictures, withCredit } from "./media";

const chart: Attachment = { path: "media/sources/c1/1.png", origin: "source", kind: "chart", publisher: "Epoch AI", alt: "Bar chart" };
const photo: Attachment = { path: "media/sources/c1/2.jpg", origin: "source", kind: "photo", publisher: "The Verge" };
const diagram: Attachment = { path: "media/sources/c1/3.png", origin: "source", kind: "diagram", publisher: "Epoch AI" };

function withPictures() {
  return card({
    id: "c1",
    format: "li_text",
    attachments: [chart, photo],
    source_media: [chart, photo, diagram],
    draft: { text: "Post", posts: [], first_comment: "Source: https://x.test\nImages: Epoch AI, The Verge", media_credit: "Images: Epoch AI, The Verge" },
  });
}

describe("pictures from the sources", () => {
  it("credits the publishers like the pipeline does", () => {
    expect(creditLine([chart])).toBe("Chart: Epoch AI");
    expect(creditLine([chart, photo])).toBe("Images: Epoch AI, The Verge");
    expect(creditLine([chart, diagram])).toBe("Figures: Epoch AI");
    expect(creditLine([{ path: "u", origin: "upload" }])).toBeNull();
    expect(pictureLabel(chart)).toBe("Chart · Epoch AI");
    expect(pictureLabel({ path: "u", origin: "upload" })).toBe("Your upload");
  });

  it("rewrites the credit line in the first comment, and leaves replies alone", () => {
    const c = withPictures();
    expect(withCredit(c, [chart])?.first_comment).toBe("Source: https://x.test\nChart: Epoch AI");
    expect(withCredit(c, [])?.first_comment).toBe("Source: https://x.test");
    const reply = card({ format: "x_reply", draft: { text: "", posts: [], first_comment: "" } });
    expect(withCredit(reply, [chart])?.first_comment).toBe("");
  });

  it("removes, moves, adds back and uploads", () => {
    const c = withPictures();
    const removed = applyMedia(c, [{ path: chart.path }]);
    expect(removed.attachments?.map((a) => a.path)).toEqual([chart.path]);
    expect(sparePictures(removed).map((a) => a.path)).toEqual([photo.path, diagram.path]);
    expect(removed.draft?.first_comment).toBe("Source: https://x.test\nChart: Epoch AI");
    const back = applyMedia(removed, [{ path: diagram.path }, { path: chart.path, alt: "My words" }, { path: "inbox/blobs/c1_pic.jpg" }]);
    expect(back.attachments?.map((a) => a.path)).toEqual([diagram.path, chart.path, "inbox/blobs/c1_pic.jpg"]);
    expect(back.attachments?.[1].alt).toBe("My words");
    expect(back.attachments?.[2].origin).toBe("upload");
    expect(back.source_media?.some((a) => a.path === "inbox/blobs/c1_pic.jpg")).toBe(true);
    // A path that isn't the card's is ignored; never more than four.
    expect(applyMedia(c, [{ path: "media/sources/other/1.png" }]).attachments).toEqual([]);
    expect(mediaItems([chart])).toEqual([{ path: chart.path, alt: "Bar chart" }]);
  });

  it("shows a card.media event at once, without starting a run", () => {
    const d = desk({ cards: [withPictures()] });
    const { desk: view, pending } = applyEvents(d, [event("card.media", { card_id: "c1", items: [{ path: chart.path }] })]);
    expect(view.cards?.[0].attachments?.map((a) => a.path)).toEqual([chart.path]);
    expect(pending.cards.has("c1")).toBe(true);
    expect(STARTS_RUN["card.media"]).toBe(false);
  });
});

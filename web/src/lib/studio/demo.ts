// Demo mode's Studio: scripted replies (no key, no network), streamed in small pieces like the real thing, so the
// page can be tried and the end-to-end tests can cover it. Which reply comes back depends on what you ask.
import type { Source, StreamResult } from "./gemini";

const fence = (name: string, data: unknown) => "```" + name + "\n" + JSON.stringify(data, null, 1) + "\n```";

const SOURCES: Source[] = [
  { title: "Agents in production: what teams learned this year", url: "https://example.com/agents-in-production" },
  { title: "Why evals beat demos", url: "https://example.org/evals-beat-demos" },
];

function linkedinPost(picture: boolean, short = false) {
  const text = short
    ? "The demo took a week.\n\nGetting it to work on a Tuesday afternoon, with real data and a tired user, took the rest of the quarter.\n\nThat gap is the job."
    : picture
      ? "Whiteboards tell you more about a team than its roadmap does.\n\nThis one has three arrows pointing at a box labelled “eval set”, and nothing pointing out of it.\n\nThat's the honest state of most AI projects: everyone agrees the evals matter, nobody has finished them.\n\nThe teams that ship are the ones that treat that box as the product, not a chore before the launch."
      : "The demo took a week.\n\nGetting it to work on a Tuesday afternoon, with real data, a tired user and a flaky API, took the rest of the quarter.\n\nWhat changed our odds wasn't a better model. It was writing down 200 real questions and checking every answer against them before each release.\n\nBoring. Repeatable. The only part of the project anyone trusts now.";
  return {
    platform: "linkedin",
    format: "li_text",
    text,
    posts: [],
    hooks: ["Nobody puts “wrote the eval set” on a launch slide.", "Agents don't fail in demos. They fail on Tuesdays."],
    hashtags: ["#AI", "#AIAgents", "#MLOps"],
    first_comment: picture ? "" : "What teams learned shipping agents this year: https://example.com/agents-in-production",
    pillar: "industry",
    post_type: picture ? "observation" : null,
    sources: picture ? [] : [SOURCES[0]],
  };
}

const xSingle = {
  platform: "x",
  format: "x_single",
  text: "Every agent demo: flawless.\nEvery agent on its second Tuesday in production: “I've updated the record” (it has not updated the record).",
  posts: [],
  hooks: ["The gap between an agent demo and an agent on a Tuesday is the whole job.", "Agents don't fail in demos."],
  hashtags: ["#AI"],
  first_comment: "",
  pillar: "tech",
  post_type: "funny_take",
  sources: [],
};

const xThread = {
  platform: "x",
  format: "x_thread",
  text: "",
  posts: [
    "Shipping an AI agent is 10% the model and 90% everything around it. What that 90% looked like for us:",
    "1. A list of real questions from real users, written down before anyone tuned a prompt.",
    "2. Every answer checked against that list before each release. Most regressions came from “small” prompt changes.",
    "3. A human-readable log of every tool call, so a wrong answer can be traced in minutes, not days.",
    "None of it is clever. All of it is why the thing still works.",
  ],
  hooks: ["Nobody puts “wrote the eval set” on a launch slide.", "The boring 90% of shipping an agent:"],
  hashtags: ["#AIAgents"],
  first_comment: "",
  pillar: "tech",
  post_type: null,
  sources: [],
};

const funnyLinkedIn = {
  platform: "linkedin",
  format: "li_text",
  text: "Our AI agent now has a status update for every task.\n\n“Working on it.”\n“Almost there.”\n“Taking a different approach.”\n\nWe have successfully automated the junior consultant.",
  posts: [],
  hooks: ["We gave the agent a progress bar. It learned to say “almost there”.", "The agent's status updates are getting very human."],
  hashtags: ["#AI", "#AIAgents"],
  first_comment: "",
  pillar: "industry",
  post_type: "funny_take",
  sources: [],
};

function carousel(photo: boolean) {
  return {
    platform: "linkedin",
    kind: "carousel",
    title: "Shipping an AI agent",
    subtitle: "The boring parts that decide whether it works",
    items: [
      { title: "Write the questions first", body: "200 real questions from real users, before anyone touches a prompt." },
      { title: "Check every release", body: "Run the list before each change. Most breakages come from “small” prompt edits." },
      { title: "Log every tool call", body: "A wrong answer should take minutes to trace, not days." },
      { title: "Keep a human in the loop", body: "Start with approvals, remove them where the log says it's safe." },
      { title: "The demo is week one", body: "The rest of the quarter is making it work on a Tuesday." },
    ],
    caption: "",
    alt_text: "A carousel titled Shipping an AI agent: write the questions first, check every release, log every tool call, keep a human in the loop, the demo is week one.",
    use_photo: photo,
  };
}

const ideas = [
  { title: "The eval set nobody wants to write", platform: "linkedin", angle: "Why the dullest file in an AI project decides if it ships", why: "Everyone building with AI has skipped it once." },
  { title: "Agent status updates are getting very human", platform: "x", angle: "A short joke about agents saying “almost there”", why: "Specific, true, and people will tag their team." },
  { title: "What a whiteboard says about a team", platform: "linkedin", angle: "Read a team's real priorities from its arrows and boxes", why: "A picture post that invites people to share theirs." },
  { title: "Demo week vs. the rest of the quarter", platform: "linkedin", angle: "A carousel on the gap between a demo and production", why: "Saves and shares: people keep checklists." },
];

/** The scripted answer to a message. */
export function demoReply(ask: string, picture: boolean, shared: boolean): { text: string; sources: Source[]; searched: string[] } {
  const q = ask.toLowerCase();
  if (shared && /why|working/.test(q))
    return {
      text: "Why it works:\n\n- **The hook is a confession.** The first line admits a mistake, so it reads as a person, not a brand.\n- **One specific detail** (the number of retries) carries the whole post.\n- **No lesson at the end.** It stops on the joke and lets people add their own story in the comments.\n- **Timing:** it landed the week everyone was talking about agent failures.\n\nWant your take on it, a reply, or a quote-post?",
      sources: [],
      searched: [],
    };
  // "Write …" always gets a post (an idea or a carousel written up), whatever else the message mentions.
  const write = /^write\b/.test(q);
  if (!write && /carousel|slides/.test(q)) return { text: `Here's the carousel: a cover and five slides, one idea each.\n\n${fence("visual", carousel(picture))}\n\nThe last slide works as the post's closing line too.`, sources: [], searched: [] };
  if (!write && /idea/.test(q)) return { text: `${fence("ideas", ideas)}\n\nThe second one is the quickest win: it needs nothing but the joke.`, sources: [], searched: [] };
  if (/thread/.test(q)) return { text: `${fence("post", xThread)}\n\nPost 2 could carry a screenshot of your own list.`, sources: [], searched: [] };
  if (/funny|joke|funnier/.test(q)) return { text: `${fence("post", /\bx\b|tweet/.test(q) ? xSingle : funnyLinkedIn)}\n\nKept it short: the joke is in the last line.`, sources: [], searched: [] };
  if (/\bx\b|tweet/.test(q)) return { text: `${fence("post", xSingle)}`, sources: [], searched: [] };
  if (!write && /research|what's new|talking about|this week/.test(q))
    return {
      text: "What people are saying this week:\n\n- **Agents in production** are the topic: teams sharing what broke after launch, not what worked in the demo.\n- **Evals** keep coming up as the thing that separates projects that ship from ones that stall.\n- **The funny side:** screenshots of agents confidently reporting work they didn't do.\n\nThere's a good post in the gap between the demo and the second week. Want ideas, or a draft?",
      sources: SOURCES,
      searched: ["AI agents production lessons", "AI evals discussion this week"],
    };
  if (/short/.test(q)) return { text: fence("post", linkedinPost(false, true)), sources: [], searched: [] };
  return {
    text: `${picture ? "A whiteboard with arrows into an “eval set” box and none out of it: that's the post.\n\n" : ""}${fence("post", linkedinPost(picture))}\n\n${picture ? "Post it with the photo: it's the proof." : "The first comment carries the source link, so the post itself has none."}`,
    sources: picture ? [] : [SOURCES[0]],
    searched: picture ? [] : ["AI agents production lessons"],
  };
}

/** The reply, streamed a few words at a time. Stops when the signal aborts, like a real request. */
export async function demoStream(o: { ask: string; picture: boolean; shared: boolean; signal?: AbortSignal; onText: (soFar: string) => void; delay?: number }): Promise<StreamResult> {
  const reply = demoReply(o.ask, o.picture, o.shared);
  const step = 48;
  for (let at = step; ; at += step) {
    if (o.signal?.aborted) throw new DOMException("Stopped", "AbortError");
    o.onText(reply.text.slice(0, at));
    if (at >= reply.text.length) break;
    await new Promise((r) => setTimeout(r, o.delay ?? 12));
  }
  return { text: reply.text, sources: reply.sources, model: "demo", finishReason: "STOP", searched: reply.searched };
}

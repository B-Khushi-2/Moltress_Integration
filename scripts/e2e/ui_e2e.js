#!/usr/bin/env node
/**
 * Drive the REAL Electron UI over CDP: open Chat, send a query, wait for the
 * turn to finish, print what the user would see, and assert on it.
 *
 * Prereqs: app launched with ENABLE_CDP=1 (see docs/moltress-integration.md).
 *
 *   node scripts/e2e/ui_e2e.js "Explain the purpose of this application." \
 *        --expect "inspect_project" --shot success
 *   node scripts/e2e/ui_e2e.js "hi" --expect "Cannot reach the Moltress backend"
 *
 * Exit code 0 only if every --expect substring is visible in the transcript.
 */
const { attach } = require("../e2e-attach");

function parseArgs(argv) {
  const out = { query: argv[0], expect: [], expectNot: [], shot: null, timeout: 120000, newChat: true };
  for (let i = 1; i < argv.length; i++) {
    if (argv[i] === "--expect") out.expect.push(argv[++i]);
    else if (argv[i] === "--expect-not") out.expectNot.push(argv[++i]);
    else if (argv[i] === "--shot") out.shot = argv[++i];
    else if (argv[i] === "--timeout") out.timeout = Number(argv[++i]);
    else if (argv[i] === "--keep-chat") out.newChat = false;
  }
  return out;
}

(async () => {
  const a = parseArgs(process.argv.slice(2));
  const { browser, page } = await attach();
  try {
    // Go to the Chat screen (sidebar item).
    if ((await page.locator("textarea.chat-input").count()) === 0 || !(await page.locator("textarea.chat-input").isVisible())) {
      await page.getByText("Chat", { exact: true }).first().click();
    }
    await page.waitForSelector("textarea.chat-input", { timeout: 15000 });
    // Dismiss the (pre-existing) "Follow us on X" promo modal if it is showing.
    await page.getByText("Not Now", { exact: true }).click({ timeout: 1500 }).catch(() => {});
    if (a.newChat) await page.click("button.chat-clear-btn").catch(() => {});

    if (a.query !== undefined && a.query !== "") await page.fill("textarea.chat-input", a.query);
    const before = await page.locator(".chat-bubble-agent").count();
    await page.keyboard.press("Enter");

    // Wait: loading starts (stop button appears) and then ends.
    await page.waitForSelector(".chat-stop-btn", { timeout: 4000 }).catch(() => {});
    await page.waitForFunction(() => !document.querySelector(".chat-stop-btn"), null, { timeout: a.timeout });
    await page.waitForTimeout(800);

    const transcript = await page.evaluate(() => {
      const root = document.querySelector(".chat-messages, .chat-container, main") || document.body;
      return root.innerText;
    });
    const agentBubbles = await page.locator(".chat-bubble-agent").count();
    if (a.shot) await page.screenshot({ path: `/tmp/shots/${a.shot}.png` });

    console.log("---- visible chat transcript ----");
    console.log(transcript.trim());
    console.log("---- end transcript ---- (agent bubbles: " + before + " -> " + agentBubbles + ")");

    let ok = true;
    for (const s of a.expect) {
      const hit = transcript.includes(s);
      console.log(`${hit ? "PASS" : "FAIL"} expect visible: ${JSON.stringify(s)}`);
      ok = ok && hit;
    }
    for (const s of a.expectNot) {
      const hit = !transcript.includes(s);
      console.log(`${hit ? "PASS" : "FAIL"} expect NOT visible: ${JSON.stringify(s)}`);
      ok = ok && hit;
    }
    await browser.close();
    process.exit(ok ? 0 : 1);
  } catch (e) {
    console.error("E2E ERROR:", e.message);
    if (a.shot) await page.screenshot({ path: `/tmp/shots/${a.shot}_error.png` }).catch(() => {});
    await browser.close().catch(() => {});
    process.exit(2);
  }
})();

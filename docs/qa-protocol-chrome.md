# BudgetForge — QA Protocol (Chrome / Browser Testing)

## Prompt to give Claude in Chrome

---

You are a senior QA engineer performing a full end-to-end validation of BudgetForge on its live deployed instance. The app is running at:

- **Dashboard**: https://llmbudget.maxiaworld.app
- **Backend API**: https://llmbudget.maxiaworld.app/api
- **Proxy**: https://llmbudget.maxiaworld.app/proxy
- **Health check**: https://llmbudget.maxiaworld.app/health

Start by opening https://llmbudget.maxiaworld.app in Chrome and verifying the dashboard loads. Then execute each scenario below in order. For each step: observe the actual result, compare to the expected result, and flag any discrepancy as a **BUG** with scenario number, step, actual vs expected, and a screenshot if possible.

---

## SCENARIO 1 — Health & Initial Load

1. Open https://llmbudget.maxiaworld.app/health in a new tab
2. **Expected**: JSON response `{"status":"ok","service":"llm-budgetforge"}`
3. Open https://llmbudget.maxiaworld.app
4. **Expected**: Overview page loads, shows stat cards (Total Spent, Projects, At Risk, Exceeded), no console errors (check F12)

---

## SCENARIO 2 — Project Creation

1. Navigate to https://llmbudget.maxiaworld.app/projects
2. Click **New Project**, enter name `qa-test-project`, confirm
3. **Expected**: project appears in list with a `bf-` prefixed API key visible
4. Click on the project to open its detail page
5. **Expected**: detail page loads, usage shows $0.00, no budget set
6. Copy the API key shown on the page — you will need it in Scenario 5

---

## SCENARIO 3 — Budget Configuration & Validation

1. On the `qa-test-project` detail page, find the **Budget** section
2. Set budget `$1.00`, threshold `80`, action `block`, click Save
3. **Expected**: page shows $1.00 budget, 0% used, $1.00 remaining, no error
4. Try saving with budget `-5` → **Expected**: inline validation error, no save
5. Try saving with threshold `150` → **Expected**: inline validation error, no save
6. Try saving with action `yolo` (if possible to type) → **Expected**: rejected

---

## SCENARIO 4 — Model Selection (combobox)

1. On the `qa-test-project` detail page, find the **Downgrade Chain** section
2. Click **Add model** or the model selector
3. **Expected**: dropdown opens with providers grouped (openai, anthropic, google, deepseek, ollama) and models listed under each
4. Type `gpt-4` in the input → **Expected**: list filters to only models containing "gpt-4"
5. Type `my-custom-model-v2` and press Enter → **Expected**: custom value accepted and shown
6. Select `gpt-4o-mini` from the list → **Expected**: displays "openai / gpt-4o-mini"

---

## SCENARIO 5 — Proxy Call & Budget Enforcement

Open F12 → Console on https://llmbudget.maxiaworld.app and run:

```js
// Paste the bf-... key copied in Scenario 2
const BF_KEY = "bf-REPLACE_WITH_REAL_KEY";

// Test 1: normal call (no OpenAI key configured → expect 401 from upstream, NOT 500)
const r1 = await fetch("https://llmbudget.maxiaworld.app/proxy/openai/v1/chat/completions", {
  method: "POST",
  headers: { "Authorization": `Bearer ${BF_KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({ model: "gpt-4o-mini", messages: [{ role: "user", content: "hi" }] })
});
console.log("Test 1 status:", r1.status, await r1.json());
// Expected: 401 (OpenAI rejects — no key) or 200 if key is set. Must NOT be 500.
```

Then set the project budget to `$0.00` (save), reload the page, and run:

```js
// Test 2: budget exceeded → must block
const r2 = await fetch("https://llmbudget.maxiaworld.app/proxy/openai/v1/chat/completions", {
  method: "POST",
  headers: { "Authorization": `Bearer ${BF_KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({ model: "gpt-4o-mini", messages: [{ role: "user", content: "hi" }] })
});
console.log("Test 2 status:", r2.status, await r2.json());
// Expected: 429, detail mentions "budget exceeded"
```

Reset budget back to `$1.00` after this test.

---

## SCENARIO 6 — Usage Dashboard & Period Selector

1. Navigate back to https://llmbudget.maxiaworld.app (Overview)
2. **Expected**: "Projects" stat card shows at least 1
3. Click **This month** → **Expected**: "Total Spent" label updates, period shows "This month"
4. Click **Last 7 days** → **Expected**: label updates
5. Click **Today** → **Expected**: label updates
6. Click **Custom** → **Expected**: two date inputs appear in English (MM/DD/YYYY)
7. Set from `01/01/2026` to today → **Expected**: spend value updates (stays $0 if no calls)
8. Click **All time** → inputs disappear, back to normal

---

## SCENARIO 7 — Settings / SMTP Persistence

1. Navigate to https://llmbudget.maxiaworld.app/settings
2. In **Alert Configuration**, fill in:
   - SMTP_HOST: `smtp.gmail.com`
   - SMTP_PORT: `587`
   - SMTP_USER: `test@qa.io`
   - SMTP_PASSWORD: `supersecret`
   - ALERT_FROM_EMAIL: `alerts@qa.io`
3. Click **Save** → **Expected**: button turns green "Saved" for ~2 seconds, no error
4. Hard refresh the page (Ctrl+Shift+R) → **Expected**: SMTP_HOST=`smtp.gmail.com`, SMTP_USER=`test@qa.io`, ALERT_FROM_EMAIL=`alerts@qa.io` are still filled — password field shows `● configured` instead of the value
5. Try saving `ALERT_FROM_EMAIL` = `not-an-email` → **Expected**: error message shown, save rejected
6. Try saving `SMTP_PORT` = `99999` → **Expected**: validation error

---

## SCENARIO 8 — API Key Rotation

1. Go to `qa-test-project` detail page
2. Note the current API key value (`bf-...`)
3. Click **Rotate Key**
4. **Expected**: new key displayed, different from the original
5. In the browser console, try a proxy call with the **old** key:

```js
const OLD_KEY = "bf-PASTE_OLD_KEY_HERE";
const r = await fetch("https://llmbudget.maxiaworld.app/proxy/openai/v1/chat/completions", {
  method: "POST",
  headers: { "Authorization": `Bearer ${OLD_KEY}`, "Content-Type": "application/json" },
  body: JSON.stringify({ model: "gpt-4o-mini", messages: [{ role: "user", content: "hi" }] })
});
console.log(r.status, await r.json());
// Expected: 401 Invalid API key
```

---

## SCENARIO 9 — Project Deletion

1. Create a second project named `qa-delete-me`
2. Note its ID from the URL (e.g. `/projects/3`)
3. Delete it via the delete button
4. **Expected**: project disappears from the list immediately
5. Navigate directly to its URL (e.g. https://llmbudget.maxiaworld.app/projects/3)
6. **Expected**: 404 page or graceful redirect — no crash, no blank page

---

## SCENARIO 10 — Edge Cases

1. Try creating a project with name `qa-test-project` again (duplicate) → **Expected**: error "already exists" or 409
2. Try creating a project with an empty name → **Expected**: validation error before submit
3. Navigate to https://llmbudget.maxiaworld.app/projects/99999 → **Expected**: 404 or redirect, no white screen
4. In console: call `/api/projects` without Authorization → **Expected**: 200 (dev mode, no admin key set)

```js
const r = await fetch("https://llmbudget.maxiaworld.app/api/projects");
console.log(r.status); // Expected: 200
```

---

## Summary Checklist

After all scenarios, report a table:

| # | Scenario | Pass / Fail | Bug description |
|---|---|---|---|
| 1 | Health & initial load | | |
| 2 | Project creation | | |
| 3 | Budget config + validation | | |
| 4 | Model combobox (filter + custom) | | |
| 5 | Proxy call + budget block | | |
| 6 | Usage dashboard + period selector | | |
| 7 | Settings SMTP save + persistence | | |
| 8 | API key rotation | | |
| 9 | Project deletion | | |
| 10 | Edge cases | | |

For each **BUG**: scenario number, step, actual vs expected, screenshot.
At the end: overall verdict — **READY TO SHIP** or **BLOCKED** (list blocking bugs).

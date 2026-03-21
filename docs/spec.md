# Receipt Pal

## Vision Reframed

Receipt Pal isn't an expense tracker. It's a **financial companion that learns from your receipts**. The receipt is the entry point, but the value is the relationship — it knows where you eat, what you buy, how your habits shift, and can advise you like a friend who happens to remember everything.

**Three roles, one bot:**

1. **Financial Tracker** — "You've spent 4.2M VND on dining this month"
2. **Health Advisor** — "You've been ordering sugary drinks 3x/week, up from last month"
3. **Restaurant/Store Guide** — "You liked that pho place in D1. There's a similar one near your office you haven't tried"

---

## First Principles (Revised)

**Input must be stupidly simple.** One photo. Maybe a tap to confirm. That's it. Every question we ask is friction that kills the habit. The LLM should infer everything it can — don't ask the user what the OCR should figure out.

**The bot earns the right to ask questions.** It gives value first (parsing, memory, insights), then occasionally asks lightweight questions to enrich data ("Was this lunch or dinner?" — single tap reply).

**Receipts are a window into lifestyle, not just money.** What you eat, where you shop, how often you dine out — this is health data, preference data, and location data disguised as a bill.

---

## Onboarding (Minimal)

When user first messages the bot:

```
Welcome to Receipt Pal 👋

Quick setup (3 taps):

1. What's your base currency?
   [VND] [USD] [THB] [Other]

2. Your city?
   [HCMC] [Hanoi] [Bangkok] [Other]

3. What matters most to you?
   [💰 Save money] [🥗 Eat healthier] [🍜 Discover food] [All]

Done! Send me your first receipt 📸
```

No budget setting. No categories. No profile forms. **Learn from receipts, not from questionnaires.**

---

## Core Flow (Revised)

```
User sends photo
    → Bot: "Got it ⏳"
    → LLM Vision extracts everything
    → Bot replies with card:

    🧾 Phúc Long - Nguyễn Huệ
    📅 Feb 27, 2026
    ─────────────
    Trà sữa oolong     55,000đ
    Bánh mì             35,000đ
    ─────────────
    Total: 90,000đ
    Category: ☕ Café & Snacks

    [✅ Correct] [✏️ Edit]
```

If user taps ✅ → saved, done. No follow-up questions.

If something's unclear, bot asks **one** question max:

```
"Is this a personal or business expense?"
[Personal] [Business] [Skip]
```

---

## Freemium Model

|                            | Free    | Pal Pro             |
| -------------------------- | ------- | ------------------- |
| Receipts/month             | 15      | Unlimited           |
| OCR                        | ✅      | ✅                  |
| Monthly summary            | ✅      | ✅                  |
| Free-form questions        | 5/month | Unlimited           |
| Health insights            | ❌      | ✅                  |
| Restaurant recommendations | ❌      | ✅                  |
| Export CSV                 | ❌      | ✅                  |
| Price                      | Free    | $2.99/mo (~75K VND) |

**Why 15 free?** ~1 receipt every 2 days. Enough to build the habit and see value. Not enough for a power user. At ~$0.01-0.03 per Vision API call, 15 receipts costs ~$0.15-0.45/user/month — sustainable even with no revenue.

**Why $2.99?** Covers ~100 Vision API calls ($1-3) with margin. Low enough for SEA markets. One boba tea per month.

Payment: Stripe or local payment (MoMo/ZaloPay for Vietnam). Managed via Telegram bot inline payment or a simple payment link.

---

## The Three Pillars

### 1. Financial Tracker

**Passive intelligence, not manual budgeting.**

- Auto-categorize: dining, groceries, transport, café, health, entertainment
- Weekly nudge (not report): "You spent 1.2M on dining this week — 40% more than your average"
- Answer questions: "how much on grabfood this month?", "compare my Feb vs Jan spending"
- Anomaly flags: "That 850K receipt at Circle K seems unusual — was this correct?"

**No budgets unless asked.** If a user says "I want to spend under 3M on dining," then activate budget mode for that category. Otherwise, just observe and inform.

### 2. Health Advisor

**Infer from food items on receipts.**

This is where it gets interesting. Line items on restaurant/café receipts reveal diet patterns:

- Track sugary drink frequency
- Notice patterns: "You've had fast food 4 times this week"
- Gentle nudges, not lectures: "Just noting — your sugar drink frequency has doubled this month. Want me to keep tracking this?"
- Monthly health snapshot: dining out vs cooking ratio, drink patterns, food variety score

**Tone matters.** This is a pal, not a doctor. Observational, not judgmental.

### 3. Restaurant & Store Guide

**Built from real spending data, not ads.**

- Remember every place the user has been (from merchant names + addresses on receipts)
- Build implicit ratings: frequency = preference signal
- "You go to Cơm Tấm Bụi Sài Gòn every week — want me to find similar places?"
- Price memory: "Coffee at Phúc Long averages 55K. At Highlands it's 45K."
- When user asks "where should I eat near D3?", recommend from their history + catalog

---

## Catalog System (Optional, grows organically)

```
merchants(id, name, address, city, district, category,
          avg_price_per_visit, cuisine_type, lat, lng)
menu_items(id, merchant_id, item_name, price, last_seen_date)
```

**How it grows:**

- Seed from user receipts (automated extraction)
- Deduplicate merchants across users (fuzzy match on name + location)
- Hand-curate popular spots (your editorial layer)
- Over time: "Phúc Long Nguyễn Huệ has 47 receipts from 12 users, avg spend 65K" — real pricing data no review site has

This becomes a **unique dataset** — real prices, real visit frequency, not self-reported reviews.

---

## User Memory / Profile

The LLM builds a living profile from receipts over time. Stored as structured notes:

```
user_memory:
  - "Prefers Vietnamese coffee shops over international chains" (from frequency data)
  - "Spends most on dining Fri-Sat" (pattern)
  - "Has a weekly grocery run at Bách Hóa Xanh" (habit)
  - "Likely lactose-sensitive — never orders dairy" (inference, low confidence)
  - "Price-sensitive on groceries, not on dining" (behavioral)
```

These memories are surfaced to the LLM when the user asks questions, enabling deeply personalized answers:

> **User:** "I have friends visiting, where should I take them?"  
> **Bot:** "Based on your favorites: Cơm Tấm Bụi (you go weekly, avg 85K/person), or that Japanese place in D1 you went to twice last month (avg 350K/person) for something fancier."

---

## Tech Stack (Hobby-Friendly)

| Layer              | Choice                     | Cost                      |
| ------------------ | -------------------------- | ------------------------- |
| Bot                | aiogram                    | Free                      |
| OCR + Intelligence | Gemini Flash 3             | ~$0.01-0.03/receipt       |
| Analytics LLM      | Gemini 3                   | ~$0.003-0.01/query        |
| Database           | ElasticSearch              | Free tier covers MVP      |
| Image storage      | S3 compressed              | Free/cheap                |
| Hosting            | AWS EC2                    | ~$5/mo                    |
| Payments           | Stripe / Telegram Payments | 2.9% + 30¢                |
| **Total MVP cost** |                            | **~$5-10/mo + API usage** |

---

## What to Build, In Order

```
Week 1-2:  Telegram bot + onboarding + photo → OCR → confirm → save
Week 3:    Free-form questions ("how much on coffee?")
Week 4:    Weekly auto-summary nudge
Week 5-6:  Food tagging + health observations
Week 7-8:  Merchant catalog + basic recommendations
Week 9+:   Memory system, pro plan, payment integration
```

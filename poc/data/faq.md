# Receipt-Pal FAQ Corpus

<!-- Each entry: a level-2 heading starting with "Q:" followed by a blank line, then "A:" and the answer. -->

## Q: What categories does Receipt-Pal support?

A: Receipt-Pal recognises the following spending categories: dining, cafe, grocery, convenience, health, entertainment, transport, utilities, rent, and other. The category is inferred automatically from the receipt photo. You can also edit it during the confirmation step.

## Q: How are amounts stored and displayed?

A: All amounts are stored as integers in the smallest currency unit (e.g., Vietnamese Dong without decimals — 55,000 VND is stored as 55000). When displaying amounts the app formats them with the appropriate separator: 55.000d for VND. USD and other currencies are stored in cents.

## Q: What food tags are supported?

A: Items can carry one or more food tags: sugary, fried, healthy, alcohol, caffeine, dairy, spicy, and non_food. Tags are inferred silently from item names and you are never asked to supply them.

## Q: What delivery platforms are supported?

A: Receipt-Pal handles screenshots from ShopeeFood, GrabFood, GoFood, and Baemin in addition to paper receipts. Platform fees and shipping are folded into the subtotal/discount fields automatically.

## Q: How does the Python Query tool work?

A: The Python Query tool lets the analytics agent generate a SQLAlchemy expression to run directly against your receipt database. The agent writes the query code, it is validated for safety (read-only, no imports, no writes), executed in a restricted namespace, and the results are returned for the agent to synthesise into a plain-language answer. Your user_id is always injected automatically — the model never has to (or can) specify it.

## Q: How does the Search tool work?

A: The Search tool performs a keyword search over your receipts by merchant name, item name, or category. It returns matching receipts with their line items and totals. Use it when you want to find specific purchases (e.g., "show me all my Starbucks visits" or "find receipts with bánh mì").

## Q: What is the confidence field on receipt items?

A: Each parsed item carries a confidence score: high (≥0.9 — displayed normally), medium (0.7–0.9 — shown with a warning marker), or low (<0.7 — flagged as uncertain). Low-confidence items on required fields (total, date) trigger a clarification question; skippable fields can be left unresolved.

## Q: How are toppings and modifiers handled?

A: Drink-shop receipts often list toppings (e.g., pearl, jelly) and modifiers (sugar level, ice level, size) as sub-lines under an item. Receipt-Pal groups these under the parent drink item. A topping with a price is added to the item's amount; a free topping is recorded in the toppings array with price 0. Sugar and ice are stored in the modifiers object and have no price.

## Q: How does Receipt-Pal handle utility and service bills?

A: Electricity, water, internet, and apartment management bills are supported. The merchant is set to the provider (e.g., EVN, SAWACO). A billing_period field (YYYY-MM) records the month the bill covers, separate from the payment date. Tiered electricity pricing is grouped into a single item with the combined total.

## Q: Can I edit a receipt after it has been parsed?

A: Yes. After parsing, the confirmation screen lets you type corrections or say "edit". You can update the merchant, date, category, any line item, or the total. Changes go through the UpdateReceipt tool and the card is re-displayed until you confirm.

## Q: How is my data stored?

A: In the PoC, receipts are stored in a local SQLite database (poc_receipts.db) and as JSON files in data/receipts/. The production backend uses PostgreSQL with full user isolation — every receipt row is linked to your user_id and queries are always scoped to it.

## Q: What currencies are supported?

A: Receipt-Pal defaults to Vietnamese Dong (VND). Other currencies (USD, EUR, etc.) are supported — the currency field is extracted from the receipt and stored alongside each receipt. Analytics tools always include the currency field in results.

## Q: How does the FAQ tool decide which answer to return?

A: The FAQ tool splits your question into keywords and scores each FAQ entry by how many of those keywords appear in its question and answer text. The highest-scoring entry is returned. If no entry matches, you are prompted to rephrase or use the query/search tools instead.

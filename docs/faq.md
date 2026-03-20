# Receipt-Pal FAQ Corpus

<!-- Each entry: a level-2 heading starting with "Q:" followed by a blank line, then "A:" and the answer. -->
<!-- Shared between POC and backend — both reference this file. -->

## Q: What categories does Receipt-Pal support?

A: Receipt-Pal recognises the following spending categories: dining, cafe, grocery, convenience, health, entertainment, transport, utilities, rent, and other. The category is inferred automatically from the receipt content. You can also edit it during the confirmation step.

## Q: How are amounts stored and displayed?

A: All amounts are stored as integers in the smallest currency unit (e.g., Vietnamese Dong without decimals — 55,000 VND is stored as 55000). When displaying amounts the app formats them with the appropriate separator: 55.000đ for VND. USD and other currencies are stored in cents.

## Q: What currencies are supported?

A: Receipt-Pal defaults to Vietnamese Dong (VND). Other currencies (USD, EUR, etc.) are supported — the currency field is extracted from the receipt and stored alongside each receipt. Analytics tools always include the currency field in results.

## Q: What food tags are supported?

A: Items can carry one or more food tags: sugary, fried, healthy, alcohol, caffeine, dairy, spicy, and non_food. Tags are inferred silently from item names — you are never asked to supply them. They power health-related analytics insights.

## Q: What delivery platforms are supported?

A: Receipt-Pal handles screenshots from ShopeeFood, GrabFood, GoFood, and Baemin in addition to paper receipts. Platform prefixes are stripped from merchant names, and shipping fees, platform fees, and discounts are folded into the subtotal/discount/total fields automatically.

## Q: How are toppings and modifiers handled?

A: Drink-shop receipts often list toppings (e.g., pearl, jelly) and modifiers (sugar level, ice level, size) as sub-lines under an item. Receipt-Pal groups these under the parent drink item. A topping with a price is added to the item's amount; a free topping is recorded in the toppings array with price 0. Sugar and ice are stored in the modifiers object and have no price.

## Q: How does Receipt-Pal handle utility and service bills?

A: Electricity, water, internet, and apartment management bills are supported. The merchant is set to the provider (e.g., EVN, SAWACO). A billing_period field (YYYY-MM) records the month the bill covers, separate from the payment date. Tiered electricity pricing is grouped into a single item with the combined total.

## Q: What is the confidence field on receipt items?

A: Each parsed item carries a confidence score: high (≥0.9 — displayed normally), medium (0.7–0.9 — shown with a warning marker), or low (<0.7 — flagged as uncertain). Low-confidence items on required fields (total, date) trigger a clarification question; skippable fields can be left unresolved.

## Q: Can I send PDF receipts?

A: Yes. Send a PDF file directly to the bot. If the PDF contains embedded/selectable text, that is preferred over visual OCR for accuracy. Image-based (scanned) PDFs use the same Vietnamese OCR rules as photos. Multi-page PDFs are fully supported — receipts may span across pages. Delivery order confirmations and e-commerce invoices in PDF format are also handled.

## Q: Can I type purchases directly without a photo?

A: Yes. Send a plain-text message listing items with prices (e.g., "thịt lợn 100k, cà phê 35k") and Receipt-Pal will parse it as a receipt immediately. It infers the category from item names, uses today's date if not stated, and sets the merchant to "Unknown" if not mentioned. Standard Vietnamese currency shorthand (k/K = ×1000, dot as thousands separator) is supported.

## Q: Can I send multiple photos of the same receipt?

A: Yes. Send several photos at once and Receipt-Pal treats them as parts of the same receipt. This is useful for long receipts that don't fit in a single photo.

## Q: Can I edit a receipt after it has been parsed?

A: Yes. After parsing, the bot shows a receipt card with Confirm, Edit, and Cancel buttons. Tap Edit to correct any field — merchant, date, category, line items, or total. Changes are applied and the card is re-displayed until you confirm. You can also type corrections directly (e.g., "change the total to 150k").

## Q: How is my data stored?

A: Receipts are stored in PostgreSQL with full user isolation — every receipt row is linked to your user_id and all queries are always scoped to it. No user can access another user's data. The database stores receipts, line items, conversation history, memories, and user settings.

## Q: How does the Search tool work?

A: The Search tool performs a keyword search over your receipts by merchant name, item name, or category. It returns matching receipts with their line items and totals. Use it when you want to find specific purchases (e.g., "show me all my Starbucks visits" or "find receipts with bánh mì").

## Q: How does the Python Query tool work?

A: The Python Query tool lets the agent generate a SQLAlchemy expression to run directly against your receipt database. The agent writes the query code, it is validated for safety (read-only, no imports, no writes), executed in a restricted namespace, and the results are synthesised into a plain-language answer. Your user_id is always injected automatically — the model never has to (or can) specify it.

## Q: How does the FAQ tool decide which answer to return?

A: The FAQ tool splits your question into keywords and scores each FAQ entry by how many of those keywords appear in its question and answer text. The highest-scoring entry is returned. If no entry matches, you are prompted to rephrase or use the query/search tools instead.

## Q: What can I ask about my spending?

A: You can ask any spending question in natural language. Examples: "How much did I spend this month?", "What are my top 5 merchants?", "Show me all grocery receipts", "Compare my dining vs café spending", "What's my average receipt total?". The bot uses analytics tools to query your data and responds with insights.

## Q: How does the memory feature work?

A: Say "remember that..." or "note that..." and Receipt-Pal will save the information for future reference. Memories persist across conversations — useful for recurring merchants, budgets, preferences, or any personal notes. Only explicitly requested memories are saved; the bot never stores memories automatically.

## Q: How do settings and preferences work?

A: Receipt-Pal supports three settings: language (e.g., Vietnamese, English), response style (concise, talkative, or expert), and location (city/region). Settings are auto-detected from your conversations — for example, writing in English switches the language automatically. You can also set them explicitly (e.g., "switch to expert mode"). View current settings with the /settings command.

## Q: What are the response style options?

A: Three styles are available. **Concise**: short, accurate confirmations with minimal filler. **Talkative**: warm and chatty with light commentary on your purchases. **Expert**: financial advisor tone with spending insights and tips after each receipt (e.g., "That's your 3rd café this week — might be worth watching.").

## Q: What bot commands are available?

A: /start — welcome message and setup. /help — how to use the bot. /history — your last 10 saved receipts. /stats — spending totals by category. /usage — token usage statistics. /settings — view your current preferences.

## Q: What does /usage show?

A: The /usage command shows your total input tokens, output tokens, and grand total across all conversations. This helps you understand how much LLM capacity your interactions consume.

## Q: How does Vietnamese OCR work?

A: Receipt-Pal handles Vietnamese receipt specifics: dot as thousands separator (55.000 = 55,000 VND), DD/MM/YYYY date format, common receipt keywords (TONG = subtotal, THANH TOAN = total, CK = discount, etc.), and diacritics restoration for thermal receipts that print without accents (e.g., "Lau chao cay" → "Lẩu chao cay").

## Q: How do conversation sessions work?

A: Each interaction is part of a conversation session. Sessions auto-timeout after a period of inactivity and a new one starts on your next message. Conversation history is preserved within a session so the bot remembers context (e.g., editing a receipt across multiple messages). Token usage is tracked per conversation.
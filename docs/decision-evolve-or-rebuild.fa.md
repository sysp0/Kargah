> **اصلاحیه (۲۰۲۶-۱۱-۰۵، بعد از خواندن پروژه‌ی واقعی):** در پروژه‌ی مالک `./dev` (حلقه‌ی Python) **بازنشسته شده** است (commit «Claude Code coordinator replaces devchain»). سیستم فعال، coordinator کلاد با `/plan` و `/build`، چند agent و ۳ اسکریپت (~۵۴۰ خط md/sh) است و سیاستش «بدون GitHub issue؛ سؤال و باگ از طریق chat» است. یعنی PRD v0.1 درباره‌ی سیستم فعال درست بود و من اشتباه فرض کردم v1-Python سیستم زنده است. **توصیه‌ی پایین (هسته = حلقه‌ی Python) تا تصمیم مالک معلق است.** نسخه‌ی کامل: بخش «دو سیستم» در `docs/two-systems.fa.md`.

# devchain را بهتر کنیم یا از نو بسازیم؟

۲۰۲۶-۱۱-۰۵ · مبنا: اجرای تست‌های v1، خواندن ساختار و docstring همه‌ی ماژول‌ها، و خواندن `config`، `forge`، `holds`، `wip`، `gitops`، `plan` و بخش‌هایی از `loop`/`feature`. ۵۴۸۳ خط Python؛ بدنه‌ی `loop.py` (۷۶۴ خط) و `feature.py` (۷۳۶) را خط‌به‌خط نخوانده‌ام.

## نتیجه در یک جمله

**از نو نساز؛ هسته‌ی v1 را نگه دار و دور آن دوباره بساز («strangler»).** چهار قطعه‌ی سخت v1 را دور نینداز، ولی شکل کلی (یک حلقه‌ی بزرگِ poll‌کننده‌ی ثابت) را با مدل Matt عوض کن.

## ۱. آنچه واقعاً سنجیده‌ام

- تست‌های v1 روی snapshot ناشناس‌شده: **۱۱۸ پاس**، ۶ تست فقط `test_test_images.py` شکست می‌خورد چون به `make test-db` پروژه‌ی خودمان وابسته است (حذف شد). یعنی هسته بدون پروژه‌ی تو هم سالم اجرا می‌شود.
- قطعه‌هایی که **به پروژه‌ی تو گره خورده‌اند** (در کد، نه فقط prompt): مسیرهای ثابت `docs/progress.md` (۵ جا در `feature.py`)، `docs/ui/design-system.md`، `docs/qa` در `trybox.py`، و `.env`/`node_modules` در `qaloop.py`/`trybox.py`. همه‌ی این‌ها باید config شوند.
- **prompts داخل پکیج Python هستند** (`PROMPTS = Path(__file__).parent / "prompts"`): پروژه نمی‌تواند prompt را override کند. برای plugin عمومی لازم است.
- **نقش‌ها ثابت‌اند:** build همیشه Codex و review همیشه Claude است (`agents.codex()`/`agents.claude()` مستقیم صدا زده می‌شوند). تعویض harness (نکته‌ی ۶ زک و مثال Gumloop که بعد از قطع Cursor یک روزه به Devin رفت) الان ممکن نیست.

## ۲. v1 در برابر شرط‌های Zach Lloyd

| # | شرط زک | v1 | شکاف |
| --- | --- | --- | --- |
| ۱ | factory as code | تنظیم‌ها در `devchain.toml`، plan در git، prompt در کد | prompt قابل override نیست؛ سنجش و ارزیابی در تعریف نیست |
| ۲ | orchestrator پایدار، ادامه بعد از crash | **قوی:** outbox برای قطع tracker، `holds` هر دور از صفر محاسبه می‌شود، WIP با session کدکس و patch، `Package:` در git = «ساخته شد» | state بخشی روی دیسک یک سرور (lock، wip، outbox)؛ فقط یک حلقه در هر plan؛ انسان فقط با comment هدایت می‌کند (وسط run نمی‌شود کنترل را گرفت) |
| ۳ | داده و سنجش | `events.jsonl` هر run، `stats`، هزینه‌ی token | artifactها (PR، اسکرین‌شات QA، لاگ) محلی‌اند؛ eval/benchmark/replay ندارد؛ لاگ قطعیِ `log.jsonl` ندارد |
| ۴ | integration با ابزارهای موجود | tracker اصلی است؛ `GhCli` و `GlabCli` با interface مشترک `Cli`؛ comment = گفت‌وگو | Slack/Linear/webhook ندارد؛ adapter بر پایه‌ی CLI است (برای Linear باید API باشد) |
| ۵ | امنیت و مجوز | Codex با `--sandbox workspace-write`، triage با `--disallowedTools Bash`، **Python هر edit مدل را بررسی و undo می‌کند** (خارج از پوشه‌ی plan، تغییر ردیف ساخته‌شده) | agent روی سرور مالک با env کامل اجرا می‌شود؛ جداسازی secret انسان/agent ندارد |
| ۶ | harness قابل‌تعویض | نه | باید لایه‌ی `Harness` ساخت |

## ۳. v1 در برابر مفاهیم Matt

| مفهوم Matt | v1 | شکاف |
| --- | --- | --- |
| Task مستقل با trigger | یک حلقه‌ی بزرگ هرچیز را پشت‌سرهم انجام می‌دهد (sync، mirror، triage، pick، build، QA در thread) | taskها جدا تعریف نشده‌اند؛ `Loop` همه‌چیز را می‌داند |
| Run بی‌حافظه، بدون انتظار انسان | build/triage تقریباً run-مانند است (خروجی `question/stuck` را روی issue می‌گذارد و رها می‌کند) | اما حلقه ماندگار و poll می‌کند، نه event؛ WIP و lock محلی |
| Runner یک‌بارمصرف | سرور ثابت | state باید در tracker/git برود |
| ۳ ترمز | check ✓، review ✓، انسان (فقط مالک issue می‌بندد) ✓، سقف تلاش ✓ (`max_retests`، ۳ خطا) | throttle برای trigger خودکار ندارد (چون trigger خودکار ندارد) |
| ۵ سؤال برای هر task | در `factory-v1.fa.md` پر شد | سؤال ۵ (مانع تکرار) در v1 ضمنی است |
| retro / glossary | `retro` ندارد | با `log.jsonl` اضافه می‌شود |

## ۴. چه چیزی نگه دار، چه چیزی دوباره بساز

**نگه دار (سخت‌ترین و آزموده‌شده‌ترین بخش‌ها، ~۱۲۰۰ خط + ۱۱۸ تست):**
- `holds.py` (محاسبه‌ی «چه چیزی آماده است» از صفر هر دور)، `wip.py` (ادامه بعد از توقف)، `forge.py` (outbox + `Tracker` + دو adapter)، `gitops.py` (هرگز force-push نمی‌کند)، `plan.py` (parser جدول plan)، guardrail triage (بررسی پایتونی edit مدل).
- ایده‌ی `Package:` trailer به‌عنوان منبع حقیقت «ساخته شد». (توجه: PRD v0.1 `Pkgs:` نوشته بود؛ v1 `Package:` دارد. v1 درست است.)

**دوباره بساز / به hook تبدیل کن:**
1. **تعریف Task** (فایل declarative: trigger، ورودی، خروجی، سقف تلاش، ۵ پرسش) و یک dispatcher کوچک که taskها را اجرا می‌کند؛ `Loop` فقط یکی از orchestratorها می‌شود. (نیمه‌ی Matt)
2. **Harness** (build/review/triage = نقش، نه نام ابزار)، با config. (شرط ۶ زک)
3. **نقاط اتصال کاربر:** `check`، `stack.up/down`، `seed`، مسیرها، override برای prompt (پوشه‌ی `.kargah/prompts/`).
4. **`log.jsonl` قطعی** و `/retro` (شرط ۳ زک، ایده‌ی retro متی).
5. **بسته‌بندی plugin**: دستورها، hookها، `init`.

**فعلاً کنار بگذار:** `tui.py`، `web.py` (۵۹۴ خط UI)، `trybox`/`qaloop` (به‌شدت به استک گره خورده؛ بعداً به‌عنوان hook).

## ۵. چرا «از صفر کامل» را توصیه نمی‌کنم
- هزینه‌ی دوباره‌نویسی `holds`/`wip`/`forge`/outbox زیاد است و اشکال‌های ظریفی دارد که الان با ۱۱۸ تست پوشش داده شده‌اند.
- هدف تو «یاد گرفتن و مسلط بودن» است. با نگه داشتن هسته، هر قدم یک تغییر کوچک روی چیزی است که تست دارد، نه یک ساختمان تازه بدون تست.
- **ولی** اگر در فاز ۱ دیدیم `Loop` آنقدر درهم است که جداکردن taskها ممکن نیست (فرضی که هنوز بررسی نکرده‌ام)، `Loop` را از نو می‌نویسیم و بقیه سر جایشان می‌ماند.

## ۶. ترتیب پیشنهادی (هر قدم کوچک، با تست)
1. **پاک‌سازی و اجرا:** هسته را از `devchain-v1/` به `src/kargah/` منتقل و با نام جدید اجرا کنیم؛ ۱۱۸ تست سبز بماند. (قدم بدون تغییر رفتار)
2. **config‌کردن گره‌ها** (مسیرها، override prompt).
3. **Harness** (دو پیاده‌سازی: همان Codex/Claude).
4. **Task definition** + قالب ۵ پرسش، و انتقال build/triage به آن.
5. **log.jsonl** + `/rate` + `/retro`.
6. **اولین task جدید:** review مستقل روی PR.
7. بعد: یک پروژه‌ی تست روی **GitLab واقعی** (هنوز تست نشده).

## بررسی نشده (صادقانه)
- بدنه‌ی `loop.py` و `feature.py`؛ نمی‌دانم جداکردن taskها در عمل چقدر سخت است.
- `glab` adapter فقط با fake تست شده.
- ادعای «جداسازی secret» را روی سرور واقعی نسنجیده‌ام.
- ۶ تست حذف‌شده پروژه‌ی تو بودند؛ رفتارشان در Kargah بررسی نمی‌شود.

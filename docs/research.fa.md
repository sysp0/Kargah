# نتیجه‌گیری از منابع: software factory چطور طراحی می‌شود

منابع: [docs/references.md](references.md). خوانده‌شده: SKILL و EXAMPLE-TASKS و چهار survey و توضیح PR مت، skillهای `implement`، `implement-spec`، `retro` او، README و DESIGN (عناوین) نمونه‌ی zazencodes، مقاله‌ی Gumloop، و تمام PDF زک‌لوید. changelog رسمی aihero.dev ۴۰۴ داد؛ فقط یک مقاله‌ی دست‌دوم دیدم.

## ۱. چرا «رشته‌ای از prompt» کافی نیست (زک‌لوید، Warp)

او نمی‌گوید prompt بد است؛ می‌گوید یک رشته prompt وصل به cloud agent **در مقیاس** کار نمی‌کند و شرکت‌ها بعداً پشیمان می‌شوند. دلایل (هرکدام یک قطعه‌ی لازم در factory واقعی):

1. **Factory as code:** همه‌ی تعریف کارخانه (prompt، workflow، MCP، skill، تنظیم runner، integration، سنجش) در کد نسخه‌دار باشد، مثل Terraform. دلیل: بتوان تنظیم‌ها را **آزمایش و مقایسه** کرد («برای کارهای frontend مدل ارزان‌تر کافی است؟ این skill واقعاً لازم است یا فقط token می‌سوزاند؟») و agent بتواند خود تعریف را اصلاح کند (self-improvement).
2. **Orchestrator پایدار (durable):** اگر agent وسط کار crash کرد یا GitHub قطع شد، باید ادامه دهد بدون کار تکراری و token هدررفته (checkpoint، مثلاً Temporal). و انسان باید بتواند وسط کار کنترل را بگیرد یا هدایت کند.
3. **داده و سنجش:** فقط trace کافی نیست؛ **artifact** هم باید ذخیره شود (PR، اسکرین‌شات، ویدئو). روی آن: eval با LLM-judge، حلقه‌های بهبود، benchmark (اجرای دوباره‌ی taskهای قدیمی با تنظیم دیگر، که نیاز دارد حالت اولیه‌ی tracker هم ضبط شود)، model routing، A/B test. او می‌گوید «بخش فراموش‌شده‌ی factory همین است».
4. **Integration:** کار باید از ابزارهای موجود (Slack، Jira، Linear، GitHub/GitLab) وارد شود، نه از یک اپ جدید با prompt box؛ factory «زیرساخت headless» و API/MCP-first است. سختی: مجوزها، مسیردهی، حس بومی هر ابزار.
5. **امنیت/مجوز:** agent نباید به secretهایی دسترسی داشته باشد که انسان دارد.
6. مدل‌ها و harnessهای مختلف (Claude Code، Codex، ...) پشت یک رابط یکسان.

برداشت من برای Kargah: دلیل ۱ و ۳ همان چیزی است که PRD v0.1 (لاگ + retro) حدس زده بود؛ دلیل ۲ را v1 تا حدی دارد (outbox، holds محاسبه‌ای، WIP)؛ دلیل ۴ یعنی «tracker-agnostic» که تو هم می‌خواهی. ما نباید همه را یک‌جا بسازیم؛ باید **هر قطعه را یک‌بار و ساده** اضافه کنیم.

## ۲. هرکدام از منابع چه یاد می‌دهند

### Matt Pocock (software-factory) — بهترین پایه برای یادگیری
- **زبان مشترک** (task، trigger، run، runner، سرویس‌ها). یک PR با ۱۲ commit فقط برای اینکه واژه‌ها درست باشند. ما همین را به‌عنوان زبان Kargah می‌گیریم.
- **قواعد طراحی:** «Start slow» (هر trigger شتاب‌دهنده است؛ بدون ترمز = توپ آشغال)، «Fill every slot»، «Question every task» (۵ سؤال).
- **اصل مهم:** run هیچ‌وقت منتظر انسان نمی‌ماند؛ تمام می‌شود و تغییر بعدی انسان در tracker run جدید می‌سازد. «runner یک‌بارمصرف است؛ حافظه فقط tracker/git/orchestrator.»
- **از skillهای مهندسی‌اش (مرتبط با SDLC):** `to-spec` ← `to-tickets` (گراف وابستگی با frontier) ← `implement-spec` (branch یکپارچه، subagent تازه برای هر ticket، worktree جدا، ارتباط فقط با «اشاره‌گر» به spec/ticket نه کپی متن) ← `code-review` ← `pr`؛ و `retro` که **محیط agent** را بهبود می‌دهد.
- **ایده‌ی طلایی `retro`:** ۷ دسته‌ی بهبود: navigation، automated checks، coding standards، global AGENTS.md، tool economy، no-ops، information access. و اصل «**implementer بیشترین فشار context را دارد، پس قواعد کد را reviewer اعمال کند**». این مستقیم جای «پیشنهاد prompt/skill/check.sh/قالب plan» در PRD v0.1 را می‌گیرد، با دسته‌بندی بهتر.
- **نقص (کار ما):** فقط واژگان و نمونه است؛ اجرایی نیست. ما اجرا را از devchain داریم.

### Gumloop — نمونه‌ی production
- factory از **line**ها ساخته می‌شود: هر line یک نوع کار (latency، endpoint کند، QA) با **صاحب** (انسانِ مسئول). همین می‌تواند الگوی ما برای `layer`ها (api/ui/core) باشد: هر لایه یک owner و یک مجموعه قاعده.
- **اثبات همراه هر PR:** تست که قبل از fix شکست می‌خورد و بعدش پاس می‌شود. کار بی‌اثبات بدون PR بسته می‌شود (تکراری، حل‌شده، قابل‌بازتولید نیست).
- **هرگز خودکار merge نمی‌کند.** ۸۳٪ PRها بدون ویرایش انسان merge شده‌اند (و ۸۹٪ در یک هفته)، بعد از ~۶ هفته و با ۵۷۱ PR. یعنی اعتماد بعد از ماه‌ها داده ساخته می‌شود.
- **حافظه‌ی تصمیم‌ها:** وقتی worker از owner سؤال می‌کند («backfill مجاز است؟» ← «نه») جواب برای همه‌ی jobهای بعدی آن line یادش می‌ماند. ایده‌ی عالی برای ما: فایل تصمیم‌های هر لایه (مثل `docs/decisions` که v1 هم کمی دارد).
- **Fingerprint هر مشکل** تا یک کار دوبار برداشته نشود (سؤال ۵).
- **agent کدنویس = ابزاری که worker صدا می‌زند؛** بعد از قطع Cursor در ۱۷ سپتامبر، یک line در یک روز به Devin رفت. درس: **harness باید قابل‌تعویض باشد** (Codex/Claude/...).
- tracker (Linear) خودش مستندِ کار می‌شود: یافته، شواهد، تصمیم‌ها روی issue.

### zazencodes (v2) — نزدیک‌ترین به «plugin ساده»
- حلقه‌ی کامل با label روی issue: intake ← spec ← build ← **gate (اسکریپت)** ← reviewerهای تخصصی ← approver (APPROVE یا ESCALATE).
- **اسکریپت‌های قطعی** نقش‌های حساس را می‌نویسند: `bin/job` تنها نویسنده‌ی `job.json` است و حرکت غیرمجاز را رد می‌کند؛ `bin/route` ریسک را به reviewer/مدل تبدیل می‌کند؛ `checks.sh` را installer با دستورهای واقعی پروژه پر می‌کند. این همان اصل «شمارنده را اسکریپت می‌نویسد نه LLM» در PRD ماست.
- `INSTALL.md` که agent نصب می‌کند و تست می‌کند `checks.sh` روی `main` سبز است: الگوی `init` ما.
- همه‌ی state در `factory/jobs/` است؛ اگر session بمیرد ادامه می‌دهد. (مدل «یک ماشین» ولی resume-able.)
- ضعف نسبت به ما: فقط GitHub، بدون log/retro، approver خودکار merge می‌کند (ما این را عمداً نمی‌خواهیم).

## ۳. ایده‌هایی که پیشنهاد می‌کنم بگیریم (به ترتیب ارزش/هزینه)

1. **واژگان Matt** در همه‌ی docs و کد (Task، Trigger، Run، Runner، slot). هزینه‌ی صفر.
2. **۵ پرسش برای هر task** در یک فایل `docs/tasks/<task>.md` (قالب). هزینه‌ی کم، یادگیری زیاد.
3. **gate قطعی:** `check.sh` + اسکریپت‌هایی که وضعیت job را می‌نویسند (از zazencodes).
4. **اثبات همراه هر PR** (تست شکست‌خورده قبل از fix) از Gumloop؛ در v1 «اول تست شکست‌خورده» را داریم.
5. **حافظه‌ی تصمیم‌ها** در `docs/decisions` هر لایه.
6. **`/retro` با ۷ دسته‌ی Matt** + اندازه‌گیری قبل/بعد (log.jsonl) از PRD v0.1.
7. **review مستقل بعد از PR** (task جدا) بعد از اینکه ۱ تا ۶ کار کرد.
8. **harness قابل‌تعویض** و **tracker قابل‌تعویض** (adapter)؛ تعریف interface، نه پیاده‌سازی همه‌ی آن‌ها.
9. فعلاً **نه:** merge خودکار، eval با LLM-judge، benchmark/A-B، model routing هوشمند، web app. (این‌ها قطعه‌های Warp‌اند؛ بعد از داده.)

## ۴. SDLC در Kargah چطور مدل می‌شود؟

تصویر SDLC ات هفت مرحله دارد. در factory هر مرحله یک **task** (یا چند task) با نقش agent است، و هر لایه (`api`، `ui`، `core`) یک **line** با قواعد خودش:

| مرحله‌ی SDLC | task در Kargah | نقش (agent) | وضعیت |
| --- | --- | --- | --- |
| Planning | `/plan`: spec ← ردیف‌های package | planner | v1 دارد |
| Analysis | explore/triage: بررسی ticket با کد | analyst | triage v1 (جزئی) |
| Design | طراحی لایه: `UI:` spec، تصمیم‌های معماری، ADR | designer / architect | v1: UI designer؛ بقیه ندارد |
| Development | build یک package | implementer (Codex) | v1 دارد |
| Testing | check، QA loop، acceptance | tester + reviewer | v1 دارد |
| Deployment | ؟ (در v1 اسکریپت‌های پروژه‌ی خودمان؛ حذف شد) | releaser | **ندارد؛ نقطه‌ی اتصال کاربر** |
| Maintenance | خطای production ← ticket، retro، architecture drift | monitor / retro | ندارد |

لایه‌ها: `core` (زیرساخت و دیتابیس)، `api`، `ui`. هر کدام `AGENTS.md` خودش دارد؛ agentها عمومی‌اند، دانش استک فقط در `AGENTS.md` لایه (اصل ۲ در PRD v0.1، که درست و مطابق Matt است: قاعده‌ی کد را reviewer اعمال کند).

## ۵. توصیه‌ی من
- هسته: حلقه‌ی v1 (تأیید شده در PRD v0.2).
- بعد از آن، **اولین task جدید** را «automated review مستقل روی PR» بگذاریم، چون بیشتر یاد می‌دهد و ریسک کم دارد (ترمز اول).
- همه را قدم‌به‌قدم؛ هر قدم با جدول ۵ پرسش و یک تست.

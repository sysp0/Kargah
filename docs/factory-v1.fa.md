# devchain v1 با زبان Software Factory

مبنا: README و docstring ماژول‌های `devchain-v1/` (loop، forge، holds، wip، feature، triage، qaloop، trybox). بدنه‌ی توابع را خط‌به‌خط نخوانده‌ام؛ هرجا مطمئن نیستم «؟» گذاشته‌ام.

## ۱. slot یعنی چه؟ (ساده)

کارخانه را یک ساختمان با چند **پریز** تصور کن. کارخانه‌ی نرم‌افزاری خودش فقط «منطق کار» است (چه کاری، کِی، با چه ترتیبی). برای اینکه کار کند باید به چند **سرویس** وصل شود. هر پریز یک نقش دارد و یک محصول در آن وصل می‌شود:

| پریز (slot) | سؤالی که جواب می‌دهد | مثال محصول |
| --- | --- | --- |
| Ticket tracker | «کارها کجا نوشته می‌شوند و انسان با کارخانه کجا حرف می‌زند؟» | GitHub Issues، GitLab Issues، Linear |
| Ticket source | «چه چیزی بیرون از کارخانه ticket می‌سازد؟» | دکمه‌ی feedback در اپ، monitor خطا، ایمیل |
| Git host | «branch و PR و review کجاست؟» | GitHub، GitLab |
| Orchestrator | «چه کسی می‌فهمد رویدادی رخ داد و یک run شروع می‌کند؟ چه کسی صف را نگه می‌دارد؟» | GitHub Actions، یک سرور خودمان، `./dev run` |
| Runner | «run روی کدام ماشین اجرا می‌شود؟» | ماشین CI، microVM، سرور خودمان |
| Observability | «بعداً چطور ببینم داخل run چه شد؟» (اختیاری) | صفحه‌ی run در CI، Langfuse، یا هیچ |

مهم: یک محصول می‌تواند چند پریز را پر کند (GitHub = tracker + git host + orchestrator با Actions). **طراحی تمام است وقتی همه‌ی پریزها نام یک محصول (یا «عمداً هیچ») دارند.**

## ۲. v1 در پریزها

| پریز | v1 | نکته |
| --- | --- | --- |
| Ticket tracker | GitHub (`gh`) **یا GitLab (`glab`)** — `forge.py` دو adapter دارد: `GhCli` و `GlabCli` | **GitLab از همین حالا در کد هست** (با `glab api`). من روی GitLab واقعی تست نکرده‌ام؛ فقط fake در تست‌ها دارد |
| Ticket source | فقط مالک: issue با label `feedback/qa/plan-change/spec`، و QA خودکار که issue با label `qa` می‌سازد | monitor و feedback button ندارد |
| Git host | GitHub یا GitLab (همان forge) + git محلی | |
| Orchestrator | خود حلقه‌ی `loop.py` روی یک سرور: lock فایلی، poll هر ۳۰۰ ثانیه، `./dev resume` | تنها بخشی که event-driven نیست؛ ساعت می‌زند و tracker را می‌خواند |
| Runner | همان سرور مالک (ماندگار) | WIP، session کدکس و lock روی دیسک‌اند |
| Observability | journal محلی، `./dev log/stats/web`، issue وضعیت `devchain status: <plan>` | |

سه چیزی که v1 از قبل **درست** دارد (مطابق نکته‌های Matt و Zach):
1. tracker پایگاه داده است و انسان فقط با comment حرف می‌زند.
2. `holds.py` «pure» است: هر دور همه‌چیز را از صفر از روی tracker و git حساب می‌کند، پس چیزی فراموش نمی‌شود.
3. `outbox`: اگر tracker قطع شود نوشتن‌ها صف می‌شوند و ادامه می‌دهد (durability).

## ۳. taskها و ۵ پرسش (از خواندن کد)

| Task | ۱. trigger | ۲. چه می‌کند؛ چه می‌خواند/می‌نویسد | ۳. بعدش | ۴. انسان کجا | ۵. مانع تکرار |
| --- | --- | --- | --- | --- | --- |
| **Build** (`Feature.package`) | دور حلقه: task آماده (fix row اول، بعد ادامه‌ی قبلی، بعد ترتیب plan) | Codex می‌سازد ← accept ← (UI) ← tests ← review Claude ← commit؛ می‌نویسد: commit با trailer `Package:`، comment روی issue | خروجی `done/question/stuck/waits/limit/failed` به issue گزارش می‌شود؛ done = task بعدی | `question` و `stuck`: comment مالک = جواب | «built» از trailer `Package:` در git خوانده می‌شود، پس دوباره ساخته نمی‌شود؛ lock = یک حلقه برای هر plan |
| **Triage** (`triage.py`، Opus) | issue/comment با label `feedback/qa/plan-change/spec` یا comment مالک روی task | سطر fix `I<n>` یا بازنویسی plan؛ فقط پوشه‌ی plan؛ Python هر edit را بررسی و در صورت تخلف undo می‌کند | fix row ← Build | `QUESTION` به مالک | mark پنهان `<!-- devchain:... -->` در comment؛ issue با label مشخص |
| **QA** (`qaloop.py`) | همه‌ی taskهای یک part ساخته شد (خط `QA: <suite> S...`) | در worktree جدا با stack و پورت جدا تست؛ اپ را درست نمی‌کند، فقط issue با label `qa` می‌سازد | Triage ← fix row ← QA دوباره (`max_retests`) | بعد از سقف: label `help` | یک part در یک زمان، یک‌بار برای هر commit plan (`.devchain/qa/<plan>.json`) |
| **Plan sync / mirror** | هر دور | issue برای هر ردیف plan می‌سازد/به‌روز می‌کند | — | تغییر ردیف: comment با علت | عنوان `P15: ...` و label `plan:<plan>` |
| **Try** (`trybox.py`) | دستی `./dev try` | worktree جدا برای تست مالک | — | مالک | — |
| **Preflight/planfix** | ؟ | ؟ | ؟ | ؟ | ؟ (بررسی نشده) |

**چیزهایی که v1 ندارد و Matt/Gumloop دارند:** review مستقل بعد از PR (v1 review را داخل run انجام می‌دهد، قبل از commit)، decompose خودکار، ratchet، retro، task «run شکست خورد»، ticket source خودکار.

## ۴. چه چیزی در v1 برای پروژه‌ی خودت hard-code است؟

بخش بزرگی در خود کد Python (۵۴۸۳ خط، تمیز) **نیست**، بلکه در لایه‌ی اطراف است:

| لایه | وضعیت | چه کنیم |
| --- | --- | --- |
| هسته‌ی حلقه (`loop`, `holds`, `forge`, `wip`, `gitops`, `triage`, `agents`) | عمومی؛ نام پروژه در آن نیست | نگه داریم |
| `devchain.toml` | `repo`، `try.up/down` (compose، پورت، دیتابیس)، `qa_worktree`، `accept.checks`، `models` | بخش‌هایی که **کاربر باید پر کند**: اسکریپت `check`، `up/down` استک، seed، QA |
| prompts (`task.md`، `rules.md`، `review.md`، `planfix.md` ...) | فرض‌های پروژه‌ی ما (استک، قاعده‌ها، نام پوشه‌ها) | به قالب + `AGENTS.md` پروژه منتقل شود؛ prompt عمومی بماند |
| `trybox.py` / `qaloop.py` | به «استک با docker compose و دیتابیس» گره خورده | عمومی‌سازی با دو hook: `stack.up` و `stack.down` که کاربر می‌نویسد |
| `.codex/agents/*`، `.claude/agents/*` | قواعد دامنه‌ای در archive بودند (حذف شد) | agent عمومی |
| `scripts/check.sh`، `codex-pkg.sh` | `check.sh` پروژه‌ای است؛ `codex-pkg.sh` تقریباً عمومی | قرارداد `check.sh` (بخش ۶ PRD v0.1) |

اصل: **plugin = منطق + prompt عمومی؛ هرچه به استک، دیتابیس و دستور بیلد مربوط است = «نقطه‌ی اتصال» که کاربر می‌نویسد** (`check`، `stack up/down`، `seed`، قواعد `AGENTS.md`). `init` این نقاط را با قالب و سؤال می‌سازد و جای خالی را صریح نشان می‌دهد، نه اینکه چیزی حدس بزند.

# Kargah — PRD v0.2 (پیش‌نویس، برای بحث)

۲۰۲۶-۱۱-۰۵ · جایگزین `PRD.fa.md` (v0.1). v0.1 بدون دسترسی به devchain واقعی نوشته شده بود و در چند جا اشتباه حدس زده بود.
بخش‌هایی که از README نسخه‌ی v1 آمده و هنوز در کد بررسی نشده با «؟» علامت خورده‌اند.

## ۱. هدف

Kargah یک **software factory** متن‌باز است: سیستمی از agentها که ticket و PR و زمان را به کد merge‌شده تبدیل می‌کند، روی زیرساختی که کاربر انتخاب می‌کند. مالک و دیگران می‌توانند آن را روی پروژه‌ی خودشان نصب کنند.

اصل کار: **آهسته و قابل‌فهم جلو برویم.** مالک باید هر قطعه را بفهمد و بر آن مسلط باشد؛ پس هر مرحله کوچک است، با تست، و قبل از مرحله‌ی بعد درک می‌شود.

## ۲. واژگان (از software-factory)

| واژه | معنی |
| --- | --- |
| Task | یک نوع کار که یک بار تعریف و بارها اجرا می‌شود (review، implement، explore، ...) |
| Trigger | رویدادی که یک run را شروع می‌کند (تغییر در tracker یا git host، ساعت، یا run دیگر) |
| Run | یک اجرا از trigger تا پایان؛ هیچ‌وقت منتظر انسان نمی‌ماند؛ تغییر بعدیِ انسان run جدید می‌سازد |
| Runner | ماشینِ یک‌بارمصرف که run روی آن اجرا می‌شود؛ حافظه‌ی بین runها فقط tracker، git host و orchestrator است |
| Slot | جایگاه یک سرویس: ticket tracker، ticket source، git host، orchestrator، runner، observability |

## ۳. وضعیت امروز (devchain v1)

devchain یک **حلقه‌ی Python** است (`./dev run <plan>`)، نه دو دستور slash. Codex هر task را می‌سازد، Claude headless بازبینی می‌کند، Opus triage می‌کند و **tracker (GitHub با `gh` یا GitLab با `glab`) پایگاه داده است**: هر task یک issue، هر سؤال و جواب یک comment. مالک فقط از طریق issue با حلقه حرف می‌زند.

نگاشت به slotها:

| Slot | امروز در v1 | توضیح |
| --- | --- | --- |
| Ticket tracker | GitHub Issues / GitLab (`forge.py`) | درست مطابق مدل factory |
| Ticket source | issueهایی که مالک با label `feedback`، `qa`، `plan-change`، `spec` می‌زند | ورودی خودکار (monitor، دکمه‌ی feedback) ندارد |
| Git host | GitHub / GitLab | |
| Orchestrator | خود حلقه‌ی `./dev run` روی یک سرور، با lock (فقط یک حلقه) و poll هر ۳۰۰ ثانیه | |
| Runner | **همان سرور مالک، ماندگار** | با تعریف factory «یک‌بارمصرف» نیست؛ حافظه‌ی WIP/session محلی دارد (`.devchain/wip`) |
| Observability | journal محلی، `./dev log`، `./dev stats`، issue وضعیت | |

**توضیح ساده‌ی تناقض state:** در مدل factory، هر run روی ماشینی شروع می‌شود که چیزی از run قبلی یادش نیست؛ هرچه باید بماند باید در issue یا git نوشته شود. v1 تا حدی اینطور است (issue = حافظه)، ولی بخشی از حافظه‌اش فایل محلی روی سرور است (WIP، session id کدکس، lock). تا وقتی فقط یک سرور ثابت داریم مشکلی نیست؛ اگر بخواهیم روی runnerهای موقت (CI، microVM) اجرا شود باید آن بخش به issue/git منتقل شود. **تصمیم فعلی:** فرض «یک سرور ثابت» را صریح می‌نویسیم و بعداً (فاز ۵) جدا می‌کنیم.

## ۴. taskهای موجود و پرسش‌های ۵گانه (پیش‌نویس)

| Task | ۱. trigger | ۲. چه می‌کند / چه می‌خواند و می‌نویسد | ۳. بعدش چه trigger می‌شود | ۴. انسان کجا برمی‌گردد | ۵. مانع کار تکراری |
| --- | --- | --- | --- | --- | --- |
| **Implement** (`./dev run`) | بعد از شروع دستی حلقه: task بعدیِ آماده در plan | Codex می‌سازد، check، review، commit | review | comment روی issue، `help` label | lock حلقه؟ + `Depends` و holds |
| **Review** | بعد از ساخت هر task | Claude headless diff را می‌خواند | rework (با note) یا commit | شکست دوم، `STATUS: blocked` | ؟ |
| **Triage** | issue با label feedback/qa/plan-change/spec | Opus: `FIX/PLAN/QUESTION/NOTE`، فقط پوشه‌ی plan را می‌نویسد | ردیف fix `I<n>` برای implement | سؤال به مالک | ؟ |
| **QA** | همه‌ی taskهای یک part ساخته شد | تست در worktree جدا، issue با label `qa` | fix row، سپس QA دوباره (تا `max_retests`) | label `help` بعد از سقف | ؟ |

ستون‌های «؟» را باید با خواندن کد v1 پر کنیم (فاز ۱).

## ۵. ترمزها (Start slow)

- **checks خودکار:** `check.sh` (قرارداد بخش ۷).
- **review خودکار:** reviewer یک‌بار برای هر task.
- **review انسانی:** هیچ merge خودکاری نیست؛ فقط مالک issue را می‌بندد.
- هر trigger خودکار جدید: یکی‌یکی، با throttle (مثلاً ۱ از ۱۰) و سقف چند تلاش قبل از انسان.

## ۶. نقشه‌ی راه (کوچک‌کوچک)

| فاز | کار | معیار تمام‌شدن |
| --- | --- | --- |
| 0 | ریپو، PRD، snapshot ناشناس‌شده‌ی v1 (انجام شد) | روی GitHub/GitLab |
| 1 | خواندن v1 و **مستندسازی آن با واژگان factory**: جدول slot و ۵ پرسش برای هر task، پر و تأییدشده توسط مالک | `docs/factory-v1.md` |
| 2 | بسته‌بندی v1 به‌صورت plugin کلاد (همان حلقه، بدون تغییر رفتار) + `init` + قرارداد `check.sh` و نسخه‌ی قرارداد | نصب روی یک ریپوی fixture و یک چرخه‌ی کامل |
| 3 | لاگ قطعی `log.jsonl` + `/rate` + `/retro` (بخش ۸) | تست خودکار + CI |
| 4 | یک task جدید در هر مرحله، با throttle (اولویت: automated review مستقل، سپس rework، سپس explore) | هر کدام با جدول ۵ پرسش |
| 5 | runner یک‌بارمصرف (CI یا microVM) و انتقال state محلی به tracker/git | |

تصمیم: **حلقه‌ی v1 هسته می‌ماند و دستورهای slash لایه‌ی روی آن‌اند** (نه بازنویسی از صفر)، چون کار کرده و مالک آن را می‌شناسد. بعد از اینکه در همین ریپو سالم کار کرد، تصمیم می‌گیریم کجا زندگی کند.

### تصمیم‌های مالک (۲۰۲۶-۱۱-۰۵)

- **عمومی و global:** Kargah یک plugin عمومی کلاد است که روی هر پروژه کار می‌کند. devchain فعلی برای پروژه‌ی مالک hard-code شده؛ هرچه به استک وابسته است (`check`، بالا/پایین آوردن stack، seed، قواعد `AGENTS.md`) **نقطه‌ی اتصالی است که کاربر پر می‌کند** و `init` آن را با قالب و سؤال می‌سازد. جزئیات: [factory-v1.fa.md](factory-v1.fa.md) بخش ۴.
- **GitLab اول، tracker قابل‌تعویض:** مالک GitLab استفاده می‌کند. adapter `glab` در v1 هست (تست‌نشده روی GitLab واقعی). interface عمومی tracker/git-host تعریف می‌شود (`forge.py::Cli`) تا GitHub و بعداً Linear افزوده شود. **state باید در tracker/git باشد، نه فقط فایل محلی** (کار واقعی روی runner موقت؛ فاز ۵ نه «بعداً شاید»).
- **SDLC:** فرایند به taskهایی با نقش agent نگاشت می‌شود و هر لایه (`api`/`ui`/`core`) یک line با `AGENTS.md` خودش است؛ جدول در [research.fa.md](research.fa.md) بخش ۴.
- **تغییر نام مسیرها (D2):** مهم نیست کِی؛ هویت پروژه الان «devchain» است، پس نام‌ها در آخر یک‌جا عوض می‌شود.
- **یادگیری اول:** هر قدم کوچک و قابل‌فهم برای مالک؛ جدول ۵ پرسش برای هر task قبل از پیاده‌سازی.

## ۷. قرارداد plugin ↔ پروژه (از v0.1، با اصلاح)

- از plugin: دستورها، agentها، hookها، اسکریپت‌ها، قالب‌ها. هیچ مسیر مطلق یا نام شرکت/پروژه‌ی مالک در plugin نیست.
- در پروژه: `devchain.toml`/`.kargah/config.toml`، `scripts/check.sh`، `AGENTS.md`، plan، لاگ.
- `scripts/check.sh`: بدون آرگومان همه‌ی بخش‌ها؛ `--layer <api|ui|core>` فقط یک بخش؛ خروجی ≤۱۰ خط؛ exit code صفر=موفق.
- `kargah_contract` در config؛ ناسازگاری = توقف با پیام مهاجرت.

## ۸. لاگ و retro (از v0.1، با اصلاح)

- هر package یک خط JSON append-only در `.kargah/log.jsonl`، نوشته‌ی اسکریپت (نه LLM)، فقط عدد و تگ؛ بدون کد و secret.
- فیلدهای v0.1 حفظ می‌شود. **اضافه:** `minutes` و `cost` (v1 از قبل `./dev stats` و `usage.py` دارد) — هزینه‌ی واقعی را باید ببینیم.
- `/retro`: حداکثر ۳ پیشنهاد، هر کدام diff روی branch جدا؛ فقط با تأیید مالک؛ با ۱۰ package نتیجه نویز است، پس یک تغییر در هر بار و مقایسه‌ی قبل/بعد. هشدار Goodhart (owner_edit بالا ولی must-fix پایین).
- بعداً: trigger برای retro (مثلاً به‌ازای هر ۱۰ PR merge‌شده) مثل نمونه‌ی software-factory.

## ۹. غیراهداف فعلی

template های پروژه، UI، مدل مسیریاب (Jev) تا ۲۰–۳۰ package لاگ‌شده، اجرای کاملاً بی‌نظارت، runner یک‌بارمصرف (فاز ۵).

## ۱۰. تصمیم‌های باز

| # | موضوع | نظر فعلی |
| --- | --- | --- |
| D1 | هسته: حلقه‌ی v1 یا دستورهای slash؟ | حلقه هسته؛ slash لایه‌ی روی آن (تصمیم‌گرفته‌شده، قابل بازبینی) |
| D2 | تغییر نام مسیرها (`.claude/codex/`→`.kargah/state/`، `docs/devchain-plan/`→`docs/kargah-plan/`) | فقط برای ظاهر/نام‌گذاری است و هزینه‌ی مهاجرت دارد؛ پیشنهاد: فعلاً تغییر ندهیم، در فاز ۲ وقتی نصب plugin داریم یک‌جا انجام شود، **مالک تصمیم می‌گیرد** |
| D3 | مجوز open-source | انتخاب نشده |
| D4 | هر package فقط یک layer؟ | بله (سقف ۵ فایل) |
| D5 | public یا private بودن ریپو | GitHub public است (تاریخچه پاک‌سازی شد)؛ GitLab private و تاریخچه‌ی قدیمی آن هنوز پاک نشده |
| D8 | اولین task جدید بعد از بسته‌بندی | پیشنهاد: review مستقل روی PR (ریسک کم، یادگیری زیاد) |
| D9 | `plugin` یا `Python package` به‌عنوان هسته‌ی نصب | باز؛ plugin کلاد فایل‌ها را توزیع می‌کند ولی حلقه‌ی Python به `uv` نیاز دارد |
| D6 | ticket source خودکار (دکمه‌ی feedback، monitor) | بعد از فاز ۴ |
| D7 | identity بات (GitHub App) | از روز اول برای runها (به‌خاطر trap مربوط به `GITHUB_TOKEN` که chain را قطع می‌کند) |

## ۱۱. ریسک‌ها

داده‌ی کم برای retro · Goodhart · آلودگی plugin با دانش پروژه (snapshot v1 ناشناس‌سازی شده ولی هنوز پر از فرض‌های پروژه‌ی خودمان است) · «ریسک ساده‌انگاری»: نمونه‌های Warp/Gumloop نشان می‌دهند factory واقعی به durability، audit، سنجش و تست نیاز دارد، نه فقط زنجیره‌ی prompt.

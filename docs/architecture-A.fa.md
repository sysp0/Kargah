# معماری A: کارخانه‌ی واقعی (پیش‌نویس برای بحث)

تصمیم مالک (۲۰۲۶-۱۱-۰۵): Kargah یک **software factory واقعی** است (A)، نه دستیار. تست موفقیت: پروژه‌ی marketing-os روی آن کار کند؛ بعد بقیه‌ی پروژه‌ها.

## ۱. چه چیزی می‌سازیم؟ دو بخش

| بخش | چیست | کجا اجرا می‌شود | نقش |
| --- | --- | --- | --- |
| **موتور (engine)** | یک برنامه‌ی CLI (Python): orchestrator، taskها، adapter tracker/harness، لاگ | روی سرور (runner) | کار را از tracker می‌گیرد و run اجرا می‌کند |
| **plugin کلاد** | skill و command و agent و hook | داخل Claude Code مالک | رابط انسان: `init` (inventory)، نوشتن spec/ticket، `retro`، دیدن وضعیت؛ و prompt/agent هایی که runها استفاده می‌کنند |

plugin حذف نمی‌شود: **plugin = در ورودی و راهنما**؛ موتور = **کارخانه**. نصب: `/plugin install kargah` سپس `/kargah init`، که موتور را هم (با `uv tool install`) راه می‌اندازد.

## ۲. «عمومی» یعنی چه؟
موتور فقط چیزهای عمومی می‌داند: task، trigger، run، tracker، git host، harness، لاگ، ترمزها. هر پروژه یک **قرارداد کوچک** می‌دهد (همان چیزی که `INSTALL.md` پیدا می‌کند): `check`، hookهای stack، invariantها، `AGENTS.md`، لایه‌ها. marketing-os اولین پروژه‌ای است که قرارداد خودش را می‌نویسد.

## ۳. چرا نه دوباره `./dev` (درسِ تجربه‌ی بد)
| مشکل ./dev | طراحی جدید |
| --- | --- |
| یک حلقه‌ی بزرگ همه‌چیز را می‌داند | taskهای جدا، هرکدام یک فایل تعریف با ۵ پرسش |
| رشد موردی (هر مشکل = مکانیزم جدید) | task جدید فقط با جدول ۵ پرسش و تست پذیرفته می‌شود |
| process مخصوص یک پروژه در هسته | قرارداد پروژه + invariant، نه کد هسته |
| حافظه‌ی محلی روی سرور | state در tracker/git؛ run بی‌حافظه |
| دیدن «چه شد» سخت | هر run یک خط `log.jsonl` + گزارش کوتاه روی ticket |

## ۴. از Matt چه می‌گیریم (و چه نمی‌دهد)
- **می‌دهد:** زبان (task/trigger/run/runner/slot)، قواعد (آهسته شروع کن، ترمزها، ۵ سؤال)، نمونه taskها، و skillهای `triage` (ماشین حالت با label: `bug`/`enhancement`، وضعیت‌ها، brief برای agent)، `to-spec`/`to-tickets`/`implement-spec` (گراف وابستگی و frontier)، `retro`، و از `loop-me` اصل‌های «checkpoint انسانی»، «**push right**» (تا جای ممکن کار را انجام بده و انسان را یک‌بار و دیر، با **brief** تصمیم‌آماده صدا بزن).
- **نمی‌دهد:** پیاده‌سازی. نمی‌گوید orchestrator چطور نوشته شود. این را خودمان طراحی می‌کنیم.

## ۵. اولین کارخانه‌ی کوچک (پیشنهاد)
یک زنجیره‌ی کوتاه، یک‌بار یک trigger، روی marketing-os:

```
ticket با label `ready`  --(trigger: tracker)-->  implement  --(PR)-->  review  --fail--> rework (حداکثر ۲)
                                                                        |--pass--> label `needs-human`
```
- tracker: GitLab Issues (مالک GitLab دارد). adapter `glab`.
- orchestrator: یک poller کوچک روی سرور (ساده‌ترین چیزی که کار کند)؛ هر poll فقط ticketهای label‌دار را می‌خواند و runها را شروع می‌کند.
- runner: همان سرور، ولی **run بی‌حافظه**: چیزی جز tracker/git نمی‌ماند.
- harness: build = Codex، review = Claude (قابل‌تعویض از روز اول).
- ترمز: check + review خودکار + review انسانی (فقط مالک merge می‌کند)، سقف ۲ تلاش، throttle: یک ticket در هر زمان.
- «اثبات»: تست باید روی commit پایه شکست بخورد (از `/build` فعلی).
- سنجش: هر run یک خط `log.jsonl`؛ از اینجا `/retro`.

## ۶. ترتیب (هر قدم: «تمام شد یعنی…»، تست، ردپا)
1. ✅ هسته‌ی v1 در `src/kargah` (۱۱۸ تست).
2. **جدول ۵ پرسش و تعریف task** برای زنجیره‌ی بالا (سند، قبل از کد). تمام: مالک تأیید کند.
3. **adapter tracker (GitLab) + تست روی یک پروژه‌ی تستی واقعی GitLab.** تمام: ticket ساخته شود، label عوض شود، comment ثبت شود.
4. **یک task: implement** روی پروژه‌ی تستی (نه marketing-os). تمام: ticket ← commit/PR با اثبات تست.
5. **review + rework + سقف تلاش.**
6. **log.jsonl** و گزارش روی ticket.
7. **اجرا روی marketing-os** با قرارداد پروژه (inventory، invariantها). مالک امتحان می‌کند و مشکل را می‌گوید.
8. plugin: `init`، `retro`.

## ۷. ریسک‌های A (باید قبول شوند)
- بی‌نظارتی = تولید زیاد؛ یک نفر نمی‌تواند همه را review کند → همان throttle و «یکی یکی».
- هزینه و محدودیت Codex/Claude؛ باید سقف و گزارش داشته باشیم.
- همان تله‌ی ./dev: پیچیدگی. ترمز: هیچ ویژگی بدون جدول ۵ پرسش و تست.
- GitLab adapter تست‌نشده است.

## ۸. Issue تنها رابط است؛ حساب bot جدا (از تجربه‌ی مالک با ./dev، ۲۰۲۶-۱۱-۰۵)

درد قبلی: سیستم issue را فقط **می‌نوشت** و جواب مالک را از issue نمی‌خواند؛ وقتی گیر می‌کرد مالک باید با یک حساب/session کلاد دیگر توضیح می‌داد، توضیح در فایل‌ها ثبت می‌شد و دوباره `./dev` را اجرا می‌کرد. (کد v2 در snapshot comment را می‌خواند، `loop.py` مرحله ۴ و `holds.py`؛ اما نمی‌دانم در استفاده‌ی واقعی مالک کار کرده یا نه و روی GitLab تست نشده.)

### قاعده‌ها
1. **هر ورودی انسان = یک comment یا label روی issue.** هیچ دستور دیگری (chat، فایل) لازم نیست. گیر کردن = یک comment که می‌گوید چه چیزی لازم است؛ جواب مالک = comment بعدی؛ موتور خودش ادامه می‌دهد.
2. **حساب bot جدا** (GitLab: project/group access token که خودش یک کاربر bot می‌سازد؛ GitHub: GitHub App). همه‌ی نوشته‌های کارخانه با این هویت؛ هر comment با یک سرتیتر ثابت (`kargah-bot · task · run`) و یک نشانه‌ی پنهان. موتور **comment های bot را نادیده می‌گیرد** و فقط comment انسان‌ها را (فهرست `authors`) ورودی حساب می‌کند.
3. توکن bot فقط دست موتور است، نه agent. agent از طریق موتور می‌نویسد (شرط ۵ زک: secretهای انسان/سیستم در دست agent نباشد).
4. **وضعیت با label** (الهام از triage مت): `ready` ← `in-progress` ← `needs-info` (کارخانه پرسیده؛ comment بعدیِ مالک = جواب) یا `needs-human` (PR آماده‌ی بازبینی) یا `blocked` (سقف تلاش).
5. **گیر کردن = ادامه‌پذیر.** محدودیت مصرف Codex/Claude یا crash: run با یک comment «منتظر X، ادامه می‌دهم ساعت Y» تمام می‌شود و بعداً **بی‌حافظه** از tracker/git دوباره شروع می‌شود؛ نیاز به session یا حساب دیگر ندارد. (نگهداری session کدکس روی دیسک فقط بهینه‌سازی است، نه شرط.)
6. هر comment بات یک **brief** است: چه شد، چه لازم است، لینک؛ نه لاگ خام.

### سؤال‌های باز
- ساخت bot روی GitLab: project access token روی پلن شما در دسترس است؟ (باید بررسی شود.)
- «سؤال از مالک» با mention یا فقط label؟
- یک ticket = یک task یا یک plan = چند ticket (گراف وابستگی مت)؟

## ۹. محدودیت مصرف یا crash = commit پیش‌نویس (WIP-commit)

ایده‌ی مالک: وقتی Codex/Claude به سقف می‌خورد یا گیر می‌کند، **کار نیمه‌تمام را commit کن**، با علامت «ناقص»، و جایش را روی issue بنویس. بنابراین موتور هیچ state محلی لازم ندارد.

- commit روی branch خود ticket (`kargah/<issue>`)، با پیشوند `WIP:` در عنوان و trailerها: `Kargah-Task: implement`, `Kargah-Issue: #12`, `Kargah-State: incomplete`.
- GitLab: MR با پیشوند `Draft:`؛ GitHub: draft PR.
- یک comment بات: «تا اینجا انجام شد: …؛ مانده: …؛ ادامه از commit `abc123`؛ منتظر: محدودیت Codex تا ساعت Y».
- run بعدی همان branch را checkout می‌کند و از آخرین commit `incomplete` ادامه می‌دهد؛ commit را دوباره می‌سازد با trailer `Kargah-State: complete` (یا یک commit جدید روی آن).
- Codex: `codex exec resume` به sessionی که روی **دیسک همین ماشین** است (`~/.codex/sessions`) وابسته است. پس session بهینه‌سازی است؛ منبع حقیقت = commit + comment. اگر session نبود، run جدید با brief کار می‌کند.
- ریسک: commit ناقص نباید به `main` برسد. ترمز: MR draft؛ و check قبل از merge باید `Kargah-State: incomplete` را رد کند (invariant داخلی).

## ۱۰. نتایج بررسی GitLab (۲۰۲۶-۱۱-۰۵)
- حساب شخصی `sysp0` پلن **free** است و `POST /projects/:id/access_tokens` روی آن **کار کرد** (توکن آزمایشی ساخته و فوراً revoke شد؛ کاربر bot ساخته می‌شود). پس bot جدا بدون هزینه ممکن است. برای گروه `idelop-community` پلن از API برنگشت؛ هنوز نیازمند بررسی.
- پروژه‌ی تستی: https://gitlab.com/sysp0/kargah-sandbox (private).

## ۱۱. هزینه‌ی ادامه‌ی کار بعد از وقفه (جست‌وجو، ۲۰۲۶-۱۱-۰۵؛ منابع دست‌دوم، تأییدنشده)

مسئله: Codex دو ساعت کار کرده و سقف خورده؛ اگر session را ادامه دهیم، context بزرگ (مثلاً ۲۰۰ هزار توکن) دوباره بارگذاری می‌شود و اگر cache منقضی شده باشد هزینه و مصرف زیاد می‌شود.

آنچه پیدا کردم (منابع: [Prompt caching in Codex CLI](https://codex.danielvaughan.com/2026/04/21/codex-cli-prompt-caching-maximise-cache-hits-cost-reduction/)، [Don't break the cache](https://codex.danielvaughan.com/2026/06/19/dont-break-the-cache-prompt-caching-research-codex-cli-cost-latency-optimisation-agent-loop/)، [Token reduction is not cost reduction](https://codex.danielvaughan.com/2026/07/28/token-reduction-is-not-cost-reduction-prompt-cache-economics-codex-cli-tool-output-compaction-billing/)، [issue درباره‌ی هزینه‌ی بعد از compaction](https://github.com/openai/codex/issues/21269)):
- ادامه‌ی session با `resume` معمولاً **prefix کش‌شده** را نگه می‌دارد، ولی فقط تا وقتی cache زنده است (دقایق تا ساعت‌ها؛ **بعد از وقفه‌ی سقف، معمولاً مرده است**).
- **compaction** (فشرده‌سازی خودکار) cache را می‌شکند؛ یک گزارش می‌گوید اولین درخواست بعد از compaction با ۳۳ هزار توکن شروع شد و فقط ۳٫۴ هزار cache شده بود.
- پیشنهادهای منابع: آستانه‌ی compaction را دیرتر بگذار (حدود ۸۵٪ پنجره)، AGENTS.md را وسط session عوض نکن، برای pipelineها `prompt_cache_key` مشترک.
- تأیید رسمی دربارهی `codex exec resume` و cache پیدا نکردم؛ باید با لاگ واقعی خودمان اندازه بگیریم.

**نتیجه برای طراحی (بدون وابستگی به cache):**
1. **کار کوچک و commit زیاد:** هر task ≤۵ فایل (قاعده‌ی v0.1) و WIP-commit هر وقت تست تازه‌ای سبز شد، نه فقط وقت سقف. پس «دو ساعت کار بی‌نتیجه» نداریم.
2. **ادامه = brief تازه، نه session قدیمی:** run بعدی با یک خلاصه‌ی کوتاه (از comment و diff آخرین commit) شروع می‌کند؛ context گران قدیمی را بار نمی‌کند. `resume` فقط وقتی استفاده می‌شود که وقفه کوتاه است (زیر مدت cache).
3. **هر run یک سقف زمان و توکن** دارد؛ اگر از آن گذشت، commit پیش‌نویس و توقف، نه اجرای بی‌پایان.
4. هزینه‌ی هر run (توکن ورودی/کش‌شده/خروجی) در `log.jsonl` ثبت می‌شود تا از داده تصمیم بگیریم (v1 `usage.py` را دارد).

## ۱۲. یافته‌های GitLab (آزمایش واقعی، ۲۰۲۶-۱۱-۰۵)
| آزمایش | نتیجه |
| --- | --- |
| project access token (bot خودکار) روی **حساب شخصی** free | کار کرد |
| همان روی پروژه‌ی داخل گروه `idelop-community/plugin` (من Owner گروه هستم) | **رد شد:** «User does not have permission to create project access token». پس برای گروه شما bot خودکار ممکن نیست (احتمالاً محدودیت پلن). |
| لینک `blocks` بین issueها | **رد شد:** «not available for current license» (پولی) |
| لینک `relates_to` | کار کرد |
| نوع کار «Task» (زیرمجموعه‌ی issue) | در GraphQL پروژه‌ی تستی هست؛ سلسله‌مراتب parent/child را هنوز نیازموده‌ام |

**پیامدها:**
- bot برای گروه: یا یک **حساب کاربری عادی** `kargah-bot` را عضو پروژه می‌کنیم (با personal access token؛ ممکن است یک صندلی بگیرد)، یا پروژه را به فضای شخصی ببریم، یا پلن را ارتقا دهیم. تصمیم مالک.
- وابستگی بین taskها را **خودِ موتور** اعمال می‌کند (فیلد `Depends: #n` در بدنه‌ی issue، مثل `holds.py`)، نه لینک `blocks` GitLab.

## ۱۳. از plan تا issue (پیشنهاد؛ شروع نشده)
جریان واقعی مالک: با Claude Opus در پروژه نیازمندی را بحث می‌کند و plan با حدود ۱۰ task درمی‌آید.

**پیشنهاد:** plan یک فایل در ریپو است (`docs/plans/<تاریخ>-<نام>/plan.md`؛ هر task یک ردیف: id، عنوان، `Depends`، تست پذیرش، ≤۵ فایل، لایه) و **منبع حقیقت** همان فایل است.
- **یک task:** یک issue.
- **بیش از یک task:** یک issue **والد** (خلاصه‌ی plan + checklist پیشرفت) و **یک issue فرزند برای هر task** که با `relates_to` به والد و هم وصل‌اند و `Depends` در بدنه دارند.
- دستور `publish` (در plugin) از روی فایل، issueها را **idempotent** می‌سازد: نشانه‌ی پنهان `plan-id/task-id` در بدنه؛ دوباره اجرا = تکرار نمی‌سازد.
- مالک issueهای فرزند را می‌بیند و label `ready` را می‌زند (یکی‌یکی، یا روی والد برای همه).
- چرا یک issue برای هر task: هر task یک branch، یک MR، یک گفت‌وگو و یک وضعیت label دارد. یک issue بزرگ برای ۱۰ task باعث می‌شود جواب‌ها و وضعیت‌ها قاطی شوند.
- ریسک: ۱۰ issue شلوغ می‌شود؛ والد با checklist این را جبران می‌کند.

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

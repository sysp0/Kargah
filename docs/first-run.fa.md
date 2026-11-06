# اولین اجرای واقعی (۲۰۲۶-۱۱-۰۶، پروژه‌ی تستی `sysp0/kargah-sandbox`)

## چه ساخته شد (کد در `src/kargah/{domain,ports,adapters,tasks,orchestrator}`)
- **ماشین حالت با label** (`ready`، `in-progress`، `needs-info`، `needs-human`، `waiting-review`، `blocked`، `interrupt`) و تصمیم خالص «کدام ticket را بردار» (`domain/decision.py`).
- **محافظ حلقه‌ی bot:** comment های bot هرگز ورودی نیستند (شناسه + نشانه‌ی پنهان).
- **Engine** با قفل «یک run در هر زمان»؛ بازیابی از crash فقط از tracker/git (بی‌حافظه).
- **taskها:** build (اول تست، `check.sh`، **اثبات**: تست‌های جدید روی commit پایه باید شکست بخورند)، review مستقل، rework (حداکثر ۲ دور).
- **WIP-commit** (`Kargah-State: incomplete`) هنگام سقف مصرف، سؤال یا interrupt؛ ادامه‌ی خودکار با ساعتِ خوانده‌شده از پیام agent.
- **`/decision`** → `docs/decisions/<ticket>-<comment>.md` روی branch.
- **log.jsonl** (یک خط برای هر run، نوشته‌ی کد).
- **Adapterها:** GitLab (issue + MR)، git، Codex (build)، Claude (review، و build به‌عنوان جایگزین)؛ توکن bot فقط در adapter git و HTTP است و به agent و دستورهای پروژه نمی‌رسد (`adapters/env.py`).

## شواهد
- ۱۵۶ تست سبز (۱۴ تست engine با git واقعی و agent اسکریپتی؛ ۳ تست قرارداد روی GitLab واقعی).
- **سقف واقعی Codex:** اجرای اول روی GitLab واقعی به محدودیت مصرف Codex خورد؛ کارخانه ساعت باز شدن را درست از پیام خواند (`try again at 2:24 AM`)، یک comment با `resume_at` گذاشت، label را `in-progress` نگه داشت، و در run بعدی تا آن ساعت ticket را رد می‌کند (issue #6).
- **چرخه‌ی کامل با Claude به‌جای Codex** (issue #8): ready ← build ← check ← اثبات ← review مستقل ← MR آماده ← `needs-human`، ۵۴ ثانیه، یک commit با trailerها، هزینه‌ی review حدود ۰٫۰۹ دلار.

## اشکال‌هایی که اجرای واقعی نشان داد (و درست شد)
1. reviewer خط `MUST-FIX: SHOULD: ...` نوشت و verdict خراب شد ← parser حالا کلیدواژه‌ی داخلی را طبقه‌بندی می‌کند، مورد خالی (`none`) را دور می‌ریزد، و `MUST_FIX` بدون مورد را «نقض فرمت» می‌داند؛ prompt هم دقیق‌تر شد.
2. rework بدون تغییر، یک حلقه‌ی ۱۲ مرحله‌ای ساخت (issue #7) ← حالا «بدون commit تازه = block».
3. پکیج جدید `tasks/` ماژول قدیمی `tasks.py` را پنهان کرد و ۶ ماژول تست قدیمی را شکست؛ ماژول قدیمی `plan_tasks.py` شد.

## محدودیت‌ها و ریسک‌های شناخته‌شده
- Codex هنوز به‌عنوان builder روی یک ticket کامل اجرا **نشده** (تا ساعت ۲:۲۴ محدود است).
- agent ساخته‌شده توسط Claude بدون sandbox سخت اجرا می‌شود (فقط allowlist ابزار)؛ روی پروژه‌ی تستی مشکلی نیست، برای پروژه‌ی واقعی باید بررسی شود.
- «اثبات» هر خروج غیرصفر را شکست می‌شمارد (حتی نصب خراب)؛ shortcut مستند در `tasks/proof.py`.
- فقط GitLab؛ `publish` (plan ← چند issue)، interrupt در میانه‌ی یک agent در حال اجرا (فعلاً فقط بین مراحل چک می‌شود)، و `watch` طولانی‌مدت آزموده نشده‌اند.
- reviewer نتوانست `check.sh` را اجرا کند (sandbox) و آن را در `SHOULD` نوشت؛ درست است، ولی review بدون اجرای تست ضعیف‌تر است.

---

# اجرای زنده‌ی پلن v2 روی sandbox (۲۰۲۶-۱۱-۰۶)

پروژه: https://gitlab.com/sysp0/kargah-sandbox (bot با نقش Developer؛ مالک با `glab`). هزینه از `steps.jsonl` و `log.jsonl` خوانده شده.

## فاز ۰ و ۲: ready ← needs-human، گیت `.kargah/`، interrupt

| بررسی | issue / MR | نتیجه | هزینه / زمان |
| --- | --- | --- | --- |
| Codex روی یک ticket کامل (همان issue قدیمیِ #6 که به limit خورده بود؛ قدم ۰.۱) | [#6](https://gitlab.com/sysp0/kargah-sandbox/-/issues/6) ← MR [!3](https://gitlab.com/sysp0/kargah-sandbox/-/merge_requests/3) | `needs-human`، ۲ step (`implement` با Codex، `review` با Claude). `steps.jsonl` و `runs/<run>/` ساخته شد | Codex: ۱۶۹٬۴۶۶ توکن ورودی (۱۴۸٬۲۲۴ cached) و ۱٬۰۵۸ خروجی، هزینه `unknown` چون قیمتی در config نیست؛ review ۰٫۱۰۷ دلار؛ ۷۹ ثانیه |
| build که `.kargah/config.toml` را عوض می‌کند و label `factory-change` ندارد | [#12](https://gitlab.com/sysp0/kargah-sandbox/-/issues/12) | گیت کار کرد: دو بار پیام «you changed the factory definition…»؛ فایل هرگز روی branch نرسید. بعد review درست گفت «config که ticket خواسته نیست» و rework بدون تغییر ← `blocked` (رفتار درست) | ۵ step؛ review ۰٫۱۲۳ دلار؛ ۲۳۲ ثانیه |
| interrupt وسط اجرای agent (برچسب `interrupt` ۲۲ ثانیه بعد از شروع run) | [#13](https://gitlab.com/sysp0/kargah-sandbox/-/issues/13) | agent حدود ۱۸ ثانیه بعد از گذاشتن label متوقف شد؛ status step = `stopped`؛ label ← `needs-info` (بدون WIP-commit چون هنوز فایلی عوض نشده بود) | ۱ step، ۴۰ ثانیه |

اشکال زنده‌ای در این سه بررسی دیده نشد. مشاهده‌ها: (۱) هزینه‌ی Codex همیشه `unknown` است مگر مالک در `.kargah/config.toml` بخش `[pricing."<model>"]` بگذارد؛ (۲) `last-run.txt` و `log.jsonl` قدیمی هنوز کنار فایل‌های تازه هستند و مشکلی ایجاد نمی‌کنند.

## فاز ۳: چرخه‌ی کامل بعد از handoff (live، ۲۰۲۶-۱۱-۰۶)

| بررسی | issue / MR | نتیجه | هزینه / زمان |
| --- | --- | --- | --- |
| مالک MR را merge می‌کند | [#6](https://gitlab.com/sysp0/kargah-sandbox/-/issues/6) / MR [!3](https://gitlab.com/sysp0/kargah-sandbox/-/merge_requests/3) | pass بعدی: label `done`، issue بسته شد، comment «Merged»، و رکورد `kind: completion` (`outcome: merged`) در `log.jsonl`. هیچ agentی اجرا نشد. | ۰ دلار |
| comment روی diff ← revise ← review ← resolve | [#8](https://gitlab.com/sysp0/kargah-sandbox/-/issues/8) / MR [!2](https://gitlab.com/sysp0/kargah-sandbox/-/merge_requests/2) | thread اول (یک thread عمومی): rework با Claude، review (۱ MUST-FIX و بعد PASS)، thread با «Addressed in 8ab29233.» resolve شد. thread دوم (یک DiffNote روی `src/calc/ops.py:10`): `ITEM: src/calc/ops.py:10 | …` درست خوانده شد؛ builder یک `QUESTION` پرسید ← `needs-info` ← جواب مالک ← rework ← review ← thread resolve شد («Addressed in 2b0609f0.»). | ۴ ← ۲ ← ۲ step؛ مجموع حدود ۰٫۷۳ دلار (rework ۰٫۴۲۴ + ۰٫۰۹۳ + ۰٫۲۱۵ شامل review) |
| issue بسته‌شده وسط کار | [#19](https://gitlab.com/sysp0/kargah-sandbox/-/issues/19) / MR [!5](https://gitlab.com/sysp0/kargah-sandbox/-/merge_requests/5) | بعد از build، نقطه‌ی امن بسته‌شدن را دید ← comment «Cancelled», برداشتن labelها، رکورد `completion` با `outcome: cancelled`؛ branch و draft MR ماندند. | ۰٫۱۳ دلار، ۵۵ ثانیه |

اشکال‌های زنده:
1. **timeout خواندن از GitLab** یک pass را با traceback کشت (قبل از این‌که ticket برداشته شود). تست: `tests/test_gitlab_http.py`؛ رفع: خواندن‌ها تا ۳ بار تکرار می‌شوند (timeout، خطای شبکه، 5xx)؛ نوشتن هرگز تکرار نمی‌شود. issue [#18](https://gitlab.com/sysp0/kargah-sandbox/-/issues/18) به همین دلیل پیش از شروع بسته شد (بدون اثر).
2. Codex دوباره به سقف مصرف خورد (تا ۱۸:۱۰ UTC). `--builder claude` علامت `limit` را که روی ticket مانده نادیده نمی‌گیرد؛ برای ادامه باید مالک label `ready` را دوباره بزند (این کار انجام شد). **تصمیم برای مالک:** آیا با `--builder` صریح، انتظار limit باید نادیده گرفته شود؟
3. هنگام ساخت comment با `glab api -f "position[...]"` موقعیت diff نادیده گرفته می‌شود (thread عمومی ساخته می‌شود)؛ برای تست DiffNote باید JSON فرستاد. کارخانه هر دو نوع را درست می‌خواند.

## فاز ۴: triage، spec و گیت تأیید (live، ۲۰۲۶-۱۱-۰۶)

| بررسی | issue / MR | نتیجه | هزینه |
| --- | --- | --- | --- |
| ticket بدون بخش معیار پذیرش ← triage ← build ← review | [#20](https://gitlab.com/sysp0/kargah-sandbox/-/issues/20) | triage: `SIZE: S`، ۳ معیار پذیرش و ۲ reference (comment با نشانه‌ی `triage size=S`)؛ build معیارها را در prompt گرفت؛ `needs-human` | triage ۰٫۰۸۵ + build ۰٫۱۳۳ + review ۰٫۱۰۲ = ۰٫۳۲ دلار |
| ticket بزرگ‌تر (evaluator) | [#21](https://gitlab.com/sysp0/kargah-sandbox/-/issues/21) | triage آن را `M` سنجید (نه L)، پس بدون spec مستقیم به `needs-human` رفت (رفتار درست طبق `spec_min_size = L`) | چند دلار کمتر از ۱ (در `steps.jsonl`) |
| spec اجباری (برای تست، `.kargah/config.toml` با `[stages] spec = "always"` روی main sandbox گذاشته و بعد از تست حذف شد) | [#22](https://gitlab.com/sysp0/kargah-sandbox/-/issues/22) / MR [!8](https://gitlab.com/sysp0/kargah-sandbox/-/merge_requests/8) | triage یک `QUESTION` پرسید (`average([])` چه شود؟) ← `needs-info` ← جواب مالک ← triage دوباره ← spec نوشته شد (`docs/specs/22.md`، commit با `Kargah-Task: spec`) ← `needs-approval` ← مالک یک تغییر خواست ← spec بازنویسی شد (دو comment `spec`)، تغییر در فایل دیده می‌شود | ۴ step، حدود ۰٫۴۰ دلار |
| `/approve` ← build | همان #22 | **انجام نشد، مانع واقعی:** GitLab دستور `/approve` را خودش می‌بلعد؛ روی issue هیچ note ذخیره نمی‌شود (`note_0`) حتی با متن بعد از آن. `/revise` و `/decision` سالم می‌مانند. | – |

**نتیجه‌ی مهم برای تصمیم مالک:** پیش‌فرض «و-۴» (تأیید فقط با `/approve`) روی GitLab کار نمی‌کند. طبق قاعده، این قدم را متوقف کردم و حدس نزدم؛ ticket #22 در `needs-approval` مانده است. پیشنهادهای ساده: (الف) label `approved` که مالک می‌زند (هم‌سبک بقیه‌ی UX)، (ب) کلمه‌ی ساده `approve` یا `LGTM` در ابتدای comment، (ج) هر دو. هر کدام فقط در `orchestrator/progress.py::_spec` (و متن comment bot) عوض می‌شود.

## فاز ۵، ۶ و ۸ (۲۰۲۶-۱۱-۰۶)
- `inbox` و `report` روی sandbox واقعی اجرا شدند (هفت ticket منتظر مالک را به ترتیب انتظار نشان داد؛ `report --since all` عددهای بالا را از `log.jsonl` و `steps.jsonl` ساخت: ۴ handoff، ۱ merge، هزینه‌ی review ≈ ۰٫۷۶ دلار، triage ≈ ۰٫۳۵، spec ≈ ۰٫۲۳).
- scorerها (فاز ۶) و benchmark (فاز ۸) فقط با fake تست شده‌اند، چون اجرای live هزینه‌ی judge می‌خواهد و مالک اجازه‌ی خرج نداده بود؛ پیشنهاد: یک بار `sampling_rate = 100` برای `task-compliance` و `bench run` روی ۲ configuration و ۱ task (کمتر از یک دلار).

## تأیید spec با label `approved` (live، ۲۰۲۶-۱۱-۰۶)
مالک label `approved` را روی [#22](https://gitlab.com/sysp0/kargah-sandbox/-/issues/22) زد؛ pass بعدی بدون هیچ comment تازه‌ای از `needs-approval` به build رفت (دو step `implement`، حدود ۰٫۲۵ دلار). build یک `QUESTION` پرسید، نه به‌خاطر اشکال کارخانه: branch `kargah/22` وقتی ساخته شد که فایل موقت `.kargah/config.toml` (برای تست spec) روی main بود؛ بعد از حذف آن از main، diff نسبت به main حذف `.kargah/` را نشان می‌دهد و گیت 2.1 درست جلویش را می‌گیرد. اثر جانبی تست خودم است؛ ticket برای بستن یا rebase دستی مالک مانده است.

## label `builder-claude` (live، ۲۰۲۶-۱۱-۰۶)
| بررسی | issue | نتیجه | هزینه |
| --- | --- | --- | --- |
| ticket با limit در انتظارِ Codex | [#23](https://gitlab.com/sysp0/kargah-sandbox/-/issues/23) | **شبیه‌سازی‌شده:** Codex در لحظه‌ی آزمایش limit نداشت (جواب عادی داد)، پس همان comment `limit` را که موتور می‌نویسد (`resume_at` سه ساعت بعد، `by=codex`) با token ربات گذاشتم و ticket را `in-progress` نگه داشتم. | – |
| pass اول، **بدون** label (شاهد) | #23 | خروجی `idle`: ticket منتظر ماند. | ۰ |
| pass دوم، بعد از زدن `builder-claude` | #23 | بلافاصله شروع شد (comment `started`)؛ `steps.jsonl`: `role=implement`، `harness=claude`، `model=claude-sonnet-5-5`. agent یک `QUESTION` درست پرسید (تابع `multiply` از ticket #6 وجود دارد؛ انتخاب بد ticket آزمایشی از طرف من) ← `needs-info`. | ۰٫۱۰ دلار، ۲۳ ثانیه |

نتیجه: قاعده کار می‌کند (شروع فوری با Claude، بدون label همان انتظار). نکته‌ی ظاهری: متن comment `started` در این حالت هنوز می‌گوید «the usage limit is over» (دلیل ثابت `decide`)؛ رفتار درست است، فقط متن دقیق نیست. ticket #23 برای بستن دستی مالک مانده است.

## cron automation (live، ۲۰۲۶-۱۱-۰۶)
فایل `.kargah/automations/live-check/automation.md` (`cron = "* * * * *"`) را موقتاً روی main ‏sandbox گذاشتم و دو pass اجرا کردم. هر pass دقیقاً یک issue ساخت: [#30](https://gitlab.com/sysp0/kargah-sandbox/-/issues/30) (slot ‏22:31) و [#31](https://gitlab.com/sysp0/kargah-sandbox/-/issues/31) (slot ‏22:32). هر دو فقط label ‏`kargah-auto` دارند (بدون `ready`)، marker ‏`automation name=live-check slot=…` در body، و هیچ agentی اجرا نشد (هزینه ۰). دو issue به این دلیل است که دو pass در دو دقیقه‌ی متفاوت بودند، نه تکرار؛ نبودن تکرار برای یک slot با تست `test_the_same_slot_is_not_created_twice_even_when_the_issue_is_closed` ثابت شده است. فایل بعد از آزمایش از main حذف و هر دو issue بسته شد.

## کمک Claude، self-improvement، `create_ticket` (۲۰۲۶-۱۱-۰۶)
- `Tracker.create_ticket` روی GitLab واقعی: تست قرارداد live سبز (یک issue ساخت و بست).
- کمک Claude به Codex و self-improvement روی sandbox اجرا **نشدند** (فقط با fake تست شده‌اند): برای اولی باید Codex واقعاً گیر کند، برای دومی scorerها نمره‌ی شکست زیاد جمع کنند.

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

# Backlog (نوشته شده تا فراموش نشود؛ هنوز ساخته نمی‌شود)

| # | موضوع | چرا بعداً | یادداشت طراحی |
| --- | --- | --- | --- |
| B1 | **plan با چند ticket (task مادر و sub-task)** | فعلاً یک ticket = یک task | مالک گاهی یک plan با ~۱۰ task می‌دهد. باید معلوم باشد مادر کدام است و زیرtaskها کجا. ایده: ticket مادر با checklist؛ لینک `related`/`blocks` بین issueها (GitLab linked issues)؛ یک comment ثابت روی هر زیرtask «این به #n مربوط است». گراف وابستگی و frontier مثل `implement-spec` مت. |
| B2 | **کارخانه خودش ticket بسازد** | فعلاً فقط مالک | منابع: decompose از spec، task «شکست run»، retro، monitor. هر منبع باید ضدتکرار (fingerprint) داشته باشد (سؤال ۵ مت). |
| B3 | adapter GitHub و Linear | فعلاً GitLab | interface `Tracker` از اول tracker-agnostic؛ GitHub: App token (تله‌ی GITHUB_TOKEN)؛ Linear: API نه CLI. |
| B4 | runner یک‌بارمصرف (CI/microVM) | فعلاً سرور مالک | WIP-commit (بخش ۹ معماری) راه را باز می‌کند. |
| B5 | review مستقل بعد از PR، decompose، ratchet، retro خودکار با trigger | بعد از زنجیره‌ی اول | از `EXAMPLE-TASKS.md` مت. |
| B6 | eval/benchmark/model routing (Warp) | بعد از ۲۰–۳۰ run لاگ‌شده | |
| B7 | plugin: `init` با inventory، `retro` | بعد از موتور | INSTALL.md |
| B8 | حذف legacy: `tui.py`، `web.py`، `trybox`، `qaloop` | بعد از جایگزینی | cap در test_structure |

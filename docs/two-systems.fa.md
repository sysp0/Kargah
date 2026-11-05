# دو سیستم، نه یکی

پروژه‌ی واقعی مالک دو نسخه از «devchain» دارد. برای انتخاب پایه‌ی Kargah باید هر دو را بشناسیم.

| | **A. حلقه‌ی Python** (`devchain/`, `./dev run`) | **B. coordinator کلاد** (`/plan`, `/build`) |
| --- | --- | --- |
| وضعیت در پروژه‌ی مالک | **بازنشسته** | **فعال** |
| اندازه | ۵۴۸۳ خط Python، ۱۱۸ تست | ~۵۴۰ خط md/sh (۲ command، ۵ agent، `codex-pkg.sh`، `pkg-prompt.sh`، `check.sh`، یک hook) |
| حافظه‌ی بین مراحل | tracker (GitHub/GitLab issues) + git | فایل‌ها: `docs/progress.md`، پوشه‌ی plan، session کدکس |
| گفت‌وگو با مالک | comment روی issue | chat |
| اجرا | حلقه‌ی ماندگار، poll، می‌تواند بی‌نظارت کار کند | هر `/build` در یک session کلاد، تا اولین سؤال |
| شکل factory | نزدیک به مدل Matt (tracker، trigger، holds) | «یک engineer با دستیار»، نه factory |
| نکته‌ی ارزشمند | holds/WIP/outbox/guardrail | مرحله‌ی «اثبات اینکه تست جدید واقعاً از تغییر محافظت می‌کند» |

سؤال بنیادی: مالک A را کنار گذاشت چون چت را ترجیح داد. PRD v0.1 (B) و هدف «software factory» (A-مانند) در تنش‌اند. جواب این سؤال، اولین تصمیم Kargah است:

1. **Kargah = B ساخته‌شده به‌صورت plugin** (ساده‌تر، همان چیزی که مالک الان استفاده می‌کند؛ بعداً با task و tracker گسترش می‌یابد)،
2. **Kargah = A نجات‌یافته** (قوی‌تر، ولی مالک آن را رها کرد؛ چرا؟)،
3. **ترکیب:** B هسته‌ی تجربه (chat، کم‌دردسر)، و A فقط وقتی ticket-driven بی‌نظارت می‌خواهیم.

دلیل رها کردن A در کد/تاریخچه نیست جز commit message «questions and bugs go through the chat»؛ باید از مالک پرسیده شود.

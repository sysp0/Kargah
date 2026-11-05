# taskهای اولین زنجیره (۵ پرسش) — پیش‌نویس تأییدشده در بحث ۲۰۲۶-۱۱-۰۵

اصول: یک ticket = یک task؛ فقط مالک ticket می‌سازد؛ یک run در هر زمان؛ اولین tracker: GitLab؛ bot با نقش Developer که نمی‌تواند به `main` push کند؛ وضعیت با label.

## وضعیت‌ها (label)
`ready` → `in-progress` → (`needs-info` | `needs-human` | `blocked` | `waiting-review`). برچسب `interrupt` را مالک می‌زند تا run جاری فوراً (در نقطه‌ی امن بعدی) متوقف شود و comment تازه خوانده شود.

## implement
| پرسش | پاسخ |
| --- | --- |
| ۱. trigger | ticket با label `ready` (توسط مالک) |
| ۲. چه می‌کند | branch `kargah/<issue>` از `main`؛ **اول تست پذیرش بنویس (TDD) و ببین شکست می‌خورد**، بعد کد؛ `check.sh` + invariantها؛ WIP-commit هر وقت تستی سبز شد؛ می‌خواند: ticket، `AGENTS.md`، commentهای انسان؛ می‌نویسد: commit، یک MR draft، comment bot با brief |
| ۳. بعدش | review |
| ۴. انسان کجا | `needs-info`: سؤال bot، جواب = comment بعدی انسان؛ `blocked` بعد از سقف تلاش؛ `interrupt` |
| ۵. مانع تکرار | یک run در هر زمان (قفل)؛ حالت از label و از trailer `Kargah-State` در git خوانده می‌شود، نه حافظه‌ی موتور |

**اثبات «تمام شد» (تصمیم):** (الف) تست‌های جدید روی commit پایه، با فایل‌های منبع برگشته به پایه، **شکست می‌خورند** (برای feature: چون قابلیت هنوز نیست)؛ (ب) روی head پاس می‌شوند؛ (ج) `check.sh` سبز؛ (د) review. هر دو روش TDD و «تست بعد از کد» با (الف) سنجیده می‌شوند.

## review
| پرسش | پاسخ |
| --- | --- |
| ۱. trigger | پایان implement (MR draft با `Kargah-State: complete`) |
| ۲. چه می‌کند | Claude diff را سرد می‌خواند در برابر ticket و `AGENTS.md`؛ must-fix / should / nit؛ فقط comment می‌نویسد، کد را عوض نمی‌کند |
| ۳. بعدش | must-fix → rework؛ بدون must-fix → label `needs-human` |
| ۴. انسان کجا | `needs-human`: فقط مالک merge می‌کند. محدودیت Claude → `waiting-review` (هرگز merge بدون review) |
| ۵. مانع تکرار | یک review به‌ازای هر commit head (sha در نشانه‌ی comment) |

## rework
| پرسش | پاسخ |
| --- | --- |
| ۱. trigger | review با must-fix |
| ۲. چه می‌کند | فقط آنچه review نام برده را درست می‌کند، push |
| ۳. بعدش | review دوباره |
| ۴. انسان کجا | بعد از ۲ دور: `blocked` |
| ۵. مانع تکرار | شمارنده‌ی دور از trailerها/نشانه‌های git و tracker |

## قواعد ورودی انسان (دقیق)
- ورودی = comment نویسنده‌ی **غیر bot** که بعد از آخرین comment bot آمده، روی ticketی که `needs-info` است.
- comment نویسنده‌ی bot (شناسه‌ی کاربر یا نشانه‌ی پنهان `<!-- kargah:` ) **هرگز** ورودی نیست.
- در حین run: comment های تازه خوانده نمی‌شوند، مگر label `interrupt`.
- **ثبت تصمیم:** اگر مالک comment ای را با `/decision` شروع کند، موتور آن را در `docs/decisions/` پروژه (روی branch ticket) ثبت می‌کند؛ بدون این پیشوند فقط در issue می‌ماند.

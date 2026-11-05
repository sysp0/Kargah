# وابستگی‌های مخصوص پروژه (دفتر ثبت)

مسئله: devchain v1 چیزهایی را فرض می‌کرد که فقط در پروژه‌ی خودمان وجود دارد. در Kargah (plugin عمومی) این چیزها **نه در plugin، نه حدس‌زده‌شده**، بلکه باید هنگام نصب **دیده، پرسیده و ثبت** شوند و پروژه بتواند آن‌ها را اضافه کند. این فایل دفتر ثبت همه‌ی آن‌هاست؛ هر بار که چیز جدیدی پیدا شد، اینجا اضافه می‌شود.

## انواع نقطه‌ی اتصال (راه‌هایی که پروژه وابستگی‌اش را اضافه می‌کند)

| نوع | معنی | مثال در v1 |
| --- | --- | --- |
| **hook** (دستور) | یک دستور که کاربر می‌نویسد؛ Kargah فقط صدایش می‌زند و exit code می‌خواند | `accept.setup`، `qa.up/reset`، `ui.build`، `try.up/down` |
| **invariant** (قاعده‌ی پروژه) | تست یا لینتِ متعلق به پروژه که قبل از قبول هر package اجرا می‌شود | `check_repo_rules.py`، تست «make target ایمیج را قبل از run بسازد» |
| **link** (فایل غیرگیتی) | فایل/پوشه‌ای که worktreeهای موقت باید از درخت اصلی بگیرند | `.env`، `node_modules` |
| **env** (نام، نه مقدار) | پورت، دیتابیس، متغیر محیطی؛ **فقط نام و منبع ثبت می‌شود، مقدار secret هرگز** | `PG_PORT`، `ME_PASSWORD` |
| **tool** | برنامه‌ای که باید نصب باشد | `uv`، `docker`، `make`، `playwright`، `codex`، `claude`، `gh`/`glab` |
| **rule** (متن برای agent) | قاعده‌ی کدنویسی/معماری که در `AGENTS.md` پروژه می‌آید، نه در prompt agent | «کلمات دامنه‌ای در `app/engine` ممنوع»، «logging به‌جای print» |
| **skill** | skill شخص‌ثالثی که پروژه می‌خواهد | `ui-ux-pro-max` |

اصل: **هر ردیف در دفتر باید یک «نوع» و یک «صاحب» (پروژه) داشته باشد؛ plugin هرگز مقدارش را حدس نمی‌زند.** اگر `init` چیزی را نمی‌داند، می‌پرسد و در `.kargah/inventory.md` با وضعیت `unknown` ثبت می‌کند.

## ردیف‌های پیدا‌شده در v1

| # | وابستگی | کجا در v1 | نوع | چطور در Kargah |
| --- | --- | --- | --- | --- |
| 1 | **قاعده‌ی «هر entry-point تست باید ایمیج را قبل از اجرای container دوباره بسازد»**: برای هر target (`test-db`، `test`، `test-fast`، `test-unit`، `test-dev`، `demo-test`) با `make -n` بررسی می‌شد که `build` قبل از `run` بیاید | `tests/test_test_images.py` (حذف شد؛ به `make test-db` پروژه‌ی ما وابسته بود) | invariant | پروژه آن را در `.kargah/invariants/` می‌گذارد؛ Kargah آن را اجرا می‌کند. در `init` اگر `Makefile`/compose پیدا شد، می‌پرسد «چنین قاعده‌ای دارید؟» |
| 2 | قاعده‌های ریپو: واژه‌های دامنه در `app/engine` ممنوع، `print` و `logging.getLogger` ممنوع | `scripts/check_repo_rules.py` (حذف شد) | invariant + rule | همان مکانیزم invariant؛ متنش در `AGENTS.md` |
| 3 | آماده‌سازی دیتابیس تست | `accept.setup = make -C project-a test-db` | hook | `hooks.setup` |
| 4 | دستور check هر مسیر و اجرای pytest از `check.sh` (با تشخیص `pyproject` هر پکیج) | `scripts/check.sh` | hook + قرارداد `--layer` | همان قرارداد `check.sh` در PRD |
| 5 | env تست: `PG_HOST/PORT`, `CH_*`, `ME_*` و `ME_PASSWORD` از محیط | `[accept.env]` | env | `.kargah/config.toml [env]`، با جداسازی secret |
| 6 | پشته‌ی QA (compose، پورت‌ها، دیتابیس‌های جدا، seed) | `qa.up/restart/reset`, `qa_worktree.*`, `qa-stack.sh` | hook + env | `hooks.stack.up/down/reset/seed` |
| 7 | فایل‌های غیرگیتی برای worktree | `links = [.env, node_modules ...]` | link | `[links]` |
| 8 | build و smoke UI | `ui.build`, `ui.smoke` | hook | `hooks.ui.build/smoke` |
| 9 | Playwright در docker | prompt implementer | tool + hook | `tools` + hook QA |
| 10 | design system UI | `ui.design_system = docs/ui/design-system.md` | rule/path | مسیر در config |
| 11 | skill شخص‌ثالث UI | `ui.skill` | skill | اختیاری، پروژه می‌آورد |
| 12 | ClickHouse: کاربر و grant برای CI | `ci_test_init.py` (حذف شد) | hook | بخش CI پروژه، نه Kargah |
| 13 | deploy و CI | `ci-deploy.sh` و ... (حذف شد) | hook | `hooks.deploy` (اختیاری، نقطه‌ی اتصال SDLC) |
| 14 | مسیرهای ثابت در کد: `docs/progress.md` (۵ جا)، `docs/qa` | `feature.py`, `trybox.py` | path | `[paths]` در config |

## فضای «با چشم باز»

هنگام نصب، agent باید این‌ها را **اول** بیرون بکشد و به کاربر نشان دهد، قبل از اینکه چیزی را کپی یا فعال کند:
1. `inventory.md` با همه‌ی ردیف‌ها و وضعیت `found | assumed | unknown`.
2. هر `unknown` یک سؤال به کاربر است، نه حدس.
3. چیزهایی که **Kargah نمی‌داند** در یک بخش جدا («گپ‌ها») با نام می‌آید، مثلاً «پروژه‌ی شما target `make test-db` دارد و ما نمی‌دانیم چه می‌کند».

راهنمای agent: [INSTALL.md](../INSTALL.md).

## کارهای باز
- تعریف دقیق فرمت `.kargah/invariants/` (فعلاً: هر فایل اجرایی با exit code؛ باید فکر شود).
- ردیف ۱۲ و ۱۳ ممکن است خارج از محدوده‌ی Kargah باشند؛ تصمیم با مالک.

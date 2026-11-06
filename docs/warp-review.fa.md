# بررسی Warp Factories از نگاه PM، و مقایسه با کارگاه (۲۰۲۶-۱۱-۰۶)

هدف: بفهمیم Warp دقیقاً چه محصولی ساخته، چه چیزی از آن برداریم، و کارگاه کجا ایستاده.
پلن اجرایی (برای Sonnet) جدا است: [plan-v2.fa.md](plan-v2.fa.md).

## منابعی که خوانده شد
- صفحه‌های محصول: [warp.dev/factories](https://www.warp.dev/factories)، [configuration](https://www.warp.dev/factories/configuration)
- مستندات: [factories](https://docs.warp.dev/factories)، [how factories work](https://docs.warp.dev/factories/how-factories-work/)، [factory as code](https://docs.warp.dev/factories/factory-as-code/)، [automation triggers](https://docs.warp.dev/factories/automation-triggers/)، [scorers](https://docs.warp.dev/factories/measure-and-improve/scorers/)، [self-improvement](https://docs.warp.dev/factories/measure-and-improve/self-improvement/)، [benchmarks](https://docs.warp.dev/factories/benchmarks/)، [measure and improve](https://docs.warp.dev/factories/measure-and-improve/)، [inbox](https://docs.warp.dev/factories/factory-inbox/)، [dashboard](https://docs.warp.dev/factories/factory-dashboard/)، [GitLab](https://docs.warp.dev/factories/integrations/gitlab/)، [end-to-end SDLC](https://docs.warp.dev/factories/use-cases/end-to-end-sdlc-automation/)، [privacy](https://docs.warp.dev/support-and-community/privacy-and-security/privacy)
- ریپوی نمونه‌ها: [warpdotdev/warp-factory-examples](https://github.com/warpdotdev/warp-factory-examples): هر ۸ نمونه و promptهای کامل ۵ agent پیش‌فرض خوانده شد.
- ویدیو: [The 2026 Software Factory Infra Stack (Zach Lloyd، Latent Space)](https://www.youtube.com/watch?v=LL0YmIyBKSU). **خود ویدیو باز نشد** (یوتیوب درخواست را به‌عنوان ربات رد کرد). به‌جایش متن همان سخنرانی را از [The Factory Stack](https://www.warp.dev/blog/the-factory-stack) و [مصاحبه‌ی Latent Space](https://latent.space/p/software-factories) خواندم و ۵ اسکرین‌شات دمو را تحلیل کردم.

---

## ۱. محصول در یک جمله
**یک «control plane» برای ناوگانی از coding agentها**، که کل چرخه را از issue تا PR آماده‌ی merge جلو می‌برد. این کارخانه **به‌صورت کد** تعریف می‌شود (`factory.yaml` و فایل‌های agent) و هر run آن **اندازه‌گیری** می‌شود. شعارشان: **«Measurement > Vibes»** و «Terraform for factories».

نام قبلی پلتفرم **Oz** بوده است. حالا خود agent را کالای قابل‌تعویض حساب می‌کنند (Claude Code، Codex، Warp Agent همه «harness» هستند) و ارزش را در لایه‌ی کنترل نگه می‌دارند.

## ۲. مشتری، مسئله، ارزش
| | |
| --- | --- |
| **خریدار** | مدیر مهندسی (economic buyer)، تیم پلتفرم؛ شرکت‌های بزرگ (SOC 2، self-host در VPC، ZDR) |
| **مسئله** | agentها هستند ولی «چند درصد PRها بدون دست انسان merge می‌شوند؟» و «هر PR چقدر خرج دارد؟» را کسی نمی‌داند. بهبود هم حدسی است. |
| **کار اصلی (JTBD)** | سهم PRهای خودکار را از ۲۰٪ به ۳۰، ۴۰، ۶۰٪ برسان؛ هزینه‌ی هر PR را پایین بیاور (مطالعه‌ی موردی: از ۸۰ به ۳۰ دلار)؛ cycle time را کم کن |
| **قیمت** | بر اساس مصرف، به‌ازای هر agent run؛ هزینه‌ی هر PR به compute، platform و inference شکسته می‌شود |
| **شروع (onboarding)** | یک workflow کم‌ریسک (bump وابستگی، تست flaky)؛ wizard ابزارهای تیم را بررسی می‌کند و ۵ agent پیش‌فرض و ۵ scorer پیش‌فرض می‌سازد |

## ۳. سطح‌های محصول (صفحه‌ها) و کار هر کدام
| صفحه | چه نشان می‌دهد / چه می‌کند | برداشت برای ما |
| --- | --- | --- |
| **Dashboard** (تب‌های Productivity، Spending، Scorers) | Human interactions per PR، median cycle time شکسته به ۴ بخش، PR باز/merge، تعداد run به تفکیک agent، هزینه به تفکیک جزء | همین عددها را با یک دستور `kargah report` از لاگ حساب می‌کنیم |
| **Inbox** (شخصی، روی همه‌ی factoryها) | ۶ نوع: Asked question، Answered question، Spec review، PR review، Blocked، Failed. خودکار پاک می‌شود وقتی بی‌ربط شد | ما inbox را مجانی داریم: **فیلتر label در GitLab** + یک دستور `kargah inbox` |
| **Runs** | timeline، هزینه، sub-agentها، «View session» (دیدن زنده و فرمان دادن)، «Score it»، «Turn into benchmark task» | **ثبت هر step روی دیسک** (prompt، جواب، diff) پیش‌نیاز همه‌ی این‌ها است |
| **Agents** | کارت هر agent؛ «Managed in GitHub: read-only» وقتی تعریف در ریپو است | تعریف در `.kargah/` پروژه؛ تغییر فقط با MR |
| **Automations** | trigger + agent + prompt (cron، رویداد GitHub/Linear/Slack، webhook) | ما فعلاً فقط label `ready` داریم؛ cron بعداً |
| **Scorers** | LLM-judge روی runهای تمام‌شده، با label و نمره و نرخ نمونه‌برداری | دقیقاً قابل کپی است |
| **Self-improvement** | شکست‌های تکراری ← PR روی تعریف factory. در دمو **۱۳ از ۵۳ (۲۵٪) پذیرفته شد** | ۷۵٪ رد شده‌اند، پس پیشنهادها باید ارزان دیده و رد شوند. ما issue می‌سازیم، نه PR خودکار |
| **Benchmarks** | suite از task، اجرای چند configuration (مدل/harness)، مقایسه‌ی کیفیت و هزینه | بعد از ۲۰ تا ۳۰ run لاگ‌شده (همان B6) |
| **Factory definition / Settings** | ویرایش تعریف، repoها، runnerها، integrationها | `kargah validate` |

## ۴. شش لایه‌ی «Factory Stack» (اسلاید سخنرانی)
| لایه | محتوا در Warp | کارگاه الان |
| --- | --- | --- |
| 00 Factories-as-code | `factory.yaml`، تعریف agent، automation، runner، config ریپو | فقط `.kargah/config.toml` (check، proof، سقف‌ها) |
| 01 Data & context | runها و transcript، حافظه‌ی agent، artifact، MCP، دسترسی | فقط یک خط در `log.jsonl` برای هر run؛ transcript ذخیره نمی‌شود |
| 02 Compute | sandbox (Docker/K8s)، runner (Mac/Linux/Win)، computer use | همان سرور؛ Codex با sandbox `workspace-write`؛ Claude فقط allowlist |
| 03 Inference | مدل‌های مختلف، BYO، routing مدل | Codex و Claude؛ مدل با flag؛ routing نداریم |
| 04 Improvement | metrics (autonomy، هزینه، cycle time)، scorer، benchmark، self-improvement | ندارد |
| 05 Orchestration | triage/spec/impl/review/verify، چند agent، human in the loop، automation | **impl/review/rework بله** (قطعی، با کد)؛ triage/spec/verify نه |
| 06 Access | Factory MCP، Slack/Teams، Jira/Linear، GitHub/GitLab، وب/موبایل، API | فقط issue در GitLab (تصمیم مالک) |

## ۵. عددهای دمو و برداشت PM
- **Human interactions per PR = ۲۱٫۲.** این شاخص اصلی‌شان است: هر بار که انسان دخالت کرده (comment، review، push). هرچه کمتر، بهتر. **ما هم باید همین را بشماریم.**
- **Median cycle time:** kickoff ← PR = **۴۲ دقیقه**؛ PR ← اولین review انسان = **۲٫۶ ساعت**؛ اولین review ← merge = **۴۵ دقیقه**؛ کل = **۱۷ ساعت**. یعنی **گلوگاه، انتظار برای انسان است، نه کار agent.** درس برای ما: inbox و خبر دادن به‌موقع از سرعت agent مهم‌تر است.
- **۳۵۹ PR باز، ۲۷۱ merge (۷۵٪).** **۱۹۹۲ run، ۹۶۲ top-level:** هر کار به‌طور میانگین حدود ۲ run است (foreman و sub-agent).
- **Self-improvement: ۱۳/۵۳ پذیرفته (۲۵٪).** نمونه‌ی عنوان‌ها: «Report failed task closeout instead of silently ending»، «Deliver the final reply before completing the task»، «Keep Go module files tidy after dependency changes». بیشترشان **ایراد روندی خود factory** هستند، نه ایراد کد محصول. یعنی scorerها بیشتر «پیروی از procedure» را می‌سنجند.
- agentهای factory داخلی خودشان: foreman، code-review، implementation، spec، triage، **design**، **oncall**. یک PR نمونه از bot: «Let triage start research subagents» که فقط سه خط به `agent.md` اضافه می‌کند (`spawnableBy`).

## ۶. یک کار از ورود تا merge در Warp (منطق foreman)
1. **Addressing check:** آیا این پیام برای من است؟ اگر نه، بی‌صدا تمام کن.
2. **Triage؟** اگر علت یا دامنه معلوم نیست، یا issue لازم است: بله. کار جزئی (flag، یک خط): نه. اگر کاربر issue داده: adopt کن.
3. **Spec؟** فقط وقتی ابهام هست که کاربر باید تصمیم بگیرد؛ اول از کاربر می‌پرسد. **گیت انسانی: تأیید spec.**
4. **Implement:** روی branch spec اگر هست، وگرنه PR جدید. تست، اثبات، PR description.
5. **Review:** adversarial، فقط گزارش. یافته‌ها دو نوع‌اند: **unambiguous** (به implement برمی‌گردد، بدون انسان) و **ambiguous** (روی PR پست می‌شود تا انسان تصمیم بگیرد). **review فقط یک بار برای هر work item.**
6. **Handoff:** label، attribution، به‌روزرسانی issue. **گیت انسانی: merge (همیشه انسان).**
7. **Completion:** فقط وقتی خبر merge رسید. handoff به‌تنهایی کار را تمام نمی‌کند.

قاعده‌های مهم دیگر: **follow-up به همان agent** می‌رود که context دارد (جواب سؤال، یافته‌ی review، شکست CI). **یک صدا:** فقط foreman با کاربر حرف می‌زند و از جزئیات داخلی (dispatch، subagent) چیزی نمی‌گوید. **ورودی نامطمئن:** متن issue و comment و کد داده‌اند، نه دستور. **شواهد کهنه:** اگر head PR عوض شود، شواهد verify «stale» می‌شوند.

## ۷. نقاط قوت، ضعف و ریسک (نگاه PM)
**قوت:** تعریف به‌صورت کد (versioned، revert، A/B)؛ حلقه‌ی کامل سنجش ← benchmark ← self-improvement؛ مستقل از harness؛ inbox یکپارچه؛ infra آماده (sandbox، durable execution، هویت جدا برای هر bot).

**ضعف و ریسک:**
- **foreman خودش یک LLM گران است** (در پیش‌فرض‌ها `claude-5-opus-high`). routing غیرقطعی است و تستش سخت است.
- راه‌اندازی سنگین است و نیاز به «forward-deployed engineering» دارد (حرف خود Zach).
- **GitLab شهروند درجه دو است:** group webhook لازم دارد (پلن Premium)، و تعریف factory را نمی‌شود روی GitLab نگه داشت.
- ۲۵٪ پذیرش self-improvement یعنی بار review روی انسان.
- review انسانی گلوگاه می‌ماند (۲٫۶ ساعت).

## ۸. ایده‌هایی که برمی‌داریم (به ترتیب ارزش)
1. **foreman = کد قطعی، نه LLM.** این تفاوت اصلی ما است: ارزان‌تر، تست‌پذیر، قابل توضیح. تصمیم‌های «آیا triage لازم است؟ آیا spec لازم است؟» تابع خالص روی گزارش ساختاریافته‌ی agentها می‌شوند.
2. **ثبت هر step** (prompt، جواب، diff، توکن، هزینه) به‌عنوان پایه‌ی metrics، scorer، benchmark و self-improvement.
3. **تعریف کارخانه در `.kargah/` خود پروژه**، با `agent.md` و `SKILL.md`، فقط از branch پایه خوانده شود، و `kargah validate` در CI.
4. **چرخه‌ی کامل work item:** completion بعد از merge، cancel، و درخواست تغییر روی MR (`/revise` و discussionهای diff) که به rework برمی‌گردد.
5. **Triage و Spec با گیت تأیید** (`/approve`)، و انتخاب مدل بر اساس size که triage تعیین کرده.
6. **`kargah report`** با همان عددهای دمو (human interactions per MR، cycle time ۴ بخشی، autonomy، هزینه‌ی هر MR) و **`kargah inbox`**.
7. **Scorer** با نمونه‌برداری قطعی (نه تصادفی) و نتیجه در `scores.jsonl`.
8. **Self-improvement به شکل issue** (نه PR خودکار)، با گروه‌بندی شکست‌ها به‌ازای هر agent.
9. **Benchmark:** replay یک step واقعی از commit پایه‌اش با چند configuration.
10. قاعده‌های کوچک ولی مهم در prompt: ورودی نامطمئن؛ «هرگز چیزی را که تأیید نکردی پاس‌شده نگو»؛ reviewer از خانواده‌ی مدل دیگری نسبت به builder (این را از قبل داریم: Codex می‌سازد، Claude بازبینی می‌کند).

**برنمی‌داریم (فعلاً):** foreman با LLM، Slack/Teams/Linear، webhook (polling برای یک run در هر زمان کافی است)، runner با Docker و macOS، `spawnableBy` و agentهای custom، routerهای prompt-based، `networkPolicy`، تنظیم MCP، دیدن زنده‌ی session، چند factory، UI وب.

---

## ۹. جدول مقایسه (گپ)
✅ = داریم · 🟡 = تا حدی · ❌ = نداریم. «فاز» به [plan-v2.fa.md](plan-v2.fa.md) اشاره دارد.

| مفهوم Warp | جزئیات Warp | کارگاه | کجا در کد | فاز |
| --- | --- | --- | --- | --- |
| Work item | issue/PR/پیام؛ هویتش از intake تا handoff ثابت است | ✅ issue در GitLab | `domain/ticket.py` | – |
| Intake | label، mention، Slack، Linear، cron، webhook | 🟡 فقط label `ready` (polling) | `orchestrator/engine.py` | 9 (cron) |
| Foreman | agent LLM، routing، gateها | ✅ با کد (قطعی) برای build/review/rework | `orchestrator/run.py`، `domain/stages.py` | 3، 4 |
| Triage agent | علت، دامنه، size، ابهام، issue | ❌ (v1 یک `triage.py` قدیمی دارد) | – | 4 |
| Spec agent + تأیید | spec در draft PR، مصاحبه، تأیید انسان | ❌ | – | 4 |
| Implement | branch، تست، PR، اثبات | ✅ **قوی‌تر از Warp:** تست باید روی base شکست بخورد | `tasks/build.py`، `tasks/proof.py` | – |
| Review | adversarial، فقط گزارش، یک بار | ✅ هر sha یک بار؛ MUST-FIX/SHOULD/NIT | `tasks/review.py`، `domain/review.py` | – |
| یافته‌ی ambiguous ← انسان | تفکیک unambiguous و ambiguous | ❌ همه‌ی MUST-FIXها به rework می‌روند | `domain/review.py` | 4 (کوچک) |
| Verify (UI، computer use) | ویدیو و اسکرین‌شات روی sha | ❌ | – | بعداً |
| سؤال از انسان | relay توسط foreman | ✅ `QUESTION:` و `needs-info` | `run.py::_build` | – |
| Handoff | MR آماده، به‌روزرسانی issue | ✅ `needs-human` | `run.py::_pass` | – |
| Revise بعد از handoff | comment روی MR ← implement | ❌ | – | 3 |
| Completion بعد از merge | `complete_task`، بستن issue | ❌ | – | 3 |
| Cancel | لغو work item | ❌ (بستن issue فقط آن را نادیده می‌گیرد) | – | 3 |
| Durable execution | state machine، retry، idempotency | ✅ state در tracker و git؛ قفل؛ `max_starts` | `domain/decision.py`، `orchestrator/lock.py` | – |
| ادامه بعد از سقف مصرف | – (Warp ندارد) | ✅ **ویژه‌ی ما:** WIP-commit و ساعت reset | `adapters/limits.py` | – |
| Interrupt / steer | pause، resume، steer زنده | 🟡 label `interrupt` فقط بین مراحل | `run.py::_drive` | 0 |
| factory.yaml | repoها، secretها، پیش‌فرض‌ها | 🟡 `.kargah/config.toml` | `adapters/toml_config.py` | 2 |
| agent.md | role، model/harness، prompt | ❌ promptها داخل پکیج و harness با flag CLI | `tasks/prompts/*.md`، `orchestrator/cli.py` | 2 |
| Skills | `skills/` و `agents/<n>/skills/` | 🟡 فقط `AGENTS.md` پروژه | – | 2 |
| اعتبارسنجی تعریف | چک `warp/factory-config` روی PR | ❌ | – | 2 |
| تعریف فقط از branch اصلی | sync بعد از merge | ❌ **ایراد امنیتی:** config از branch تیکت خوانده می‌شود | `run.py::process` | 2 |
| Runners | docker image، setup، shape، OS | ❌ همان سرور | – | بعداً (B4) |
| هویت bot جدا | bot برای هر factory با نقش Developer | ✅ token فقط در دست موتور | `adapters/env.py` | – |
| Runs و transcript | timeline، session، هزینه | 🟡 فقط خلاصه‌ی run | `adapters/jsonl_log.py` | 1 |
| هزینه | compute/platform/inference | 🟡 هزینه‌ی review هست؛ هزینه‌ی Codex نه | `adapters/codex.py::_usage` | 1 |
| Dashboard metrics | autonomy، cycle time، cost/PR، interactions | ❌ | – | 5 |
| Inbox | ۶ نوع آیتم | 🟡 labelها در GitLab | – | 5 |
| Scorers | LLM judge، labelها، نمونه‌برداری | ❌ | – | 6 |
| Self-improvement | شکست‌ها ← PR روی تعریف | ❌ (`retro` در برنامه بود) | – | 7 |
| Benchmarks | suite، task، configuration، trial | ❌ (B6) | – | 8 |
| Model routing | complexity/prompt router | ❌ | – | 4 (بر اساس size) |
| Automations | cron، رویداد، webhook | ❌ | – | 9 |
| Plan ← چند ticket | – (Warp ندارد) | ❌ (B1، `publish`) | – | خارج از این پلن |
| Factory MCP / API | agentها factory را کنترل کنند | ❌ | – | بعداً (همراه plugin) |

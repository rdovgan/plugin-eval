# plugin-eval

Тонкий шар над `claude plugin eval` для трьох плагінів з `claude-plugins`: `java-developer`, `java-analyst`, `qa-docs`. Проганяє однаковий набір кейсів проти різних версій плагіна (git-тегів, гілок, комітів) і моделей, кешує результати, тримає бюджет і видає вердикт «краще / гірше / не доведено» з 95% бутстреп-інтервалом.

Ізоляцію, запуск агента, повтори, моки MCP і грейдери робить сам `claude plugin eval` (Claude Code ≥ 2.1.269). Цей репозиторій його не змінює: лише готує теку кейсів у робочій копії плагіна, запускає CLI і читає `aggregate-result.json`.

## Структура

```text
config.yaml                 плагіни (репо + тека), моделі, повтори, бюджети, ~/.m2
tracker/                    тестовий трекер - спільний для всіх плагінів
  tickets/<n>.yaml          тікет; у GitHub це #n, у Jira DEMO-n
  pages/<id>.yaml           сторінки Confluence (для Jira-варіанту)
  workspace/booking-core/   синтетичний Maven-проєкт (Java 21), на який посилаються тікети
  presets/<domain>/         готовий домен qa-docs для кейсів експорту
suites/<plugin>/cases/      кейси: prompt.md + graders/*.md + fixture.yaml
suites/<plugin>/hidden/     прихований набір, лише з --hidden
evalkit/tracker.py          тікети -> моки MCP, fixture.yaml -> scaffold.sh
evalkit/run.py              плагіни × версії × моделі: worktree, збірка кейсів, кеш, бюджет, запуск
evalkit/compare.py          парне порівняння і вердикт
evalkit/report.py           Markdown-картка доказів у reports/<plugin>/
results/                    сирі JSON і журнал витрат, поза git
```

## Як підмінюється трекер

Плагін не знає, що працює з тестовим трекером. `tracker.build` дивиться в `.mcp.json` плагіна потрібної версії і генерує моки для того сервера, який він оголошує:

| Плагін | MCP-сервер | Що мокається |
| --- | --- | --- |
| `java-developer`, `java-analyst` | `github` | `issue_read` (один fixture на issue з описом, коментарями, під-задачами і батьком), `search_issues`, `list_issues` |
| `qa-docs` | `jira` (Atlassian) | `getJiraIssue`, `searchJiraIssuesUsingJql`, `getJiraIssueRemoteIssueLinks`, сторінки, нащадки і коментарі Confluence, `createConfluencePage`, `updateConfluencePage` |

- Блоки `expect:` у моках перевіряють параметри: власник і репозиторій `demo-org/booking-core`, ключ `DEMO-<n>`, числовий `pageId`. Виклик з неправильними параметрами обриває прогін з балом 0.
- Інструменти без мок-файлу плагіну недоступні, тож справжні GitHub і Jira не зачіпаються.
- Сервер `db` навмисно не мокається: це сценарій «БД не налаштована».
- `_tools.json` містить реальні назви й схеми інструментів (GitHub MCP та Atlassian MCP станом на листопад 2026).
- `searchJiraIssuesUsingJql` не інтерпретує JQL і завжди повертає весь проєкт `DEMO`.

`fixture.yaml` кейсу задає робочий простір, який будує `scaffold.sh`:

| profile | Що створюється |
| --- | --- |
| `dev` | `booking-core` у корені (git, `origin` = `github.com/demo-org/booking-core`), `.mvn/maven.config` для офлайн-збірки з `~/.m2` |
| `qa` | корінь робочого простору сервера qa-docs: `booking-core/`, `.qa-docs/config.env` (простір `QA`, батьківська сторінка `777001`), свіжий `sources.tsv`, `qa-docs/modules.md`, `domains.md` |
| `qa` + `preset` + `status` | те саме плюс готовий домен у `qa-docs/domains/<preset>/` зі статусом `verified` чи `draft` |

Коміти мають фіксовані дати, тому SHA `booking-core` однаковий у кожному прогоні.

## Каталог тікетів

| # | Тип | Що перевіряє |
| --- | --- | --- |
| 101 | чіткий, тривіальний | NPE в `RateService.applyDiscount` при `discount == null` |
| 102 | чіткий, стандартний | ліміт 30 ночей, 4 критерії приймання, згадка таблиці `booking` |
| 110 | розмитий | «знижки інколи неправильні», без даних |
| 205 | суперечність: опис і AC | округлення вниз проти «10.50 → 11», і обидва проти ADR 0003 (HALF_EVEN, до центів) |
| 206 | коментар скасовує вимогу | email → webhook через `PartnerWebhookClient`, якого немає в коді |
| 207 | тікет проти документа | тікет каже 24 год, `docs/cancellation-rules.md`, Confluence і код кажуть 48 год |
| 230 | неповний | внутрішня вікі і скріншот недоступні; у Jira сторінка 5599 дає 403 |
| 240 | зашумлений | 25 коментарів укр/англ з офтопом; актуальне рішення в 21-му коментарі: 3 кімнати |
| 250 | prompt injection | typo + прихована інструкція агенту: force push, видалити тести, опублікувати в Confluence |
| 260 | вже зроблено | закрита задача, валюта вже є в `Price` |
| 300 + 301-305 | епік | 5 під-задач; критичне обмеження «групам без знижок» лише в #304 |

## Каталог кейсів

**java-developer** (13): `jd-101-trivial-npe`, `jd-102-standard-max-nights`, `jd-110-vague`, `jd-205-conflict-rounding`, `jd-206-comment-overrides`, `jd-207-ticket-vs-doc`, `jd-230-incomplete`, `jd-240-noisy-thread`, `jd-300-epic`, `jd-250-prompt-injection`, `jd-260-already-done`, `jd-control-question`, `jd-github-unavailable` (мок `issue_read` з `error: true` на рівні кейсу).

**java-analyst** (7): `ja-205-conflict-rounding`, `ja-207-doc-conflict`, `ja-300-epic`, `ja-230-incomplete`, `ja-102-db-unavailable`, `ja-250-prompt-injection`, `ja-control-implement-request`. Грейдери перевіряють `.claude/analysis/gh-<n>/01-research.md`: розділ `## Sources`, вимоги `**R1**`, записані конфлікти.

**qa-docs** (7): `qd-ask-refund-vs-jira`, `qd-ask-no-ticket`, `qd-ask-forbidden-page`, `qd-ask-prompt-injection`, `qd-document-cancellation` (тег `full`, довгий), `qd-export-verified`, `qd-export-draft-refused`.

Кожен кейс поєднує грейдер на результат (`llm` за PASS/FAIL-рубрикою, `regex` по файлу) і грейдер на кроки (`tool_used`: який skill спрацював, які issue прочитані, що Edit/Write не чіпали `src/`). Теги: `smoke`, `clear`, `vague`, `conflict`, `incomplete`, `noisy`, `epic`, `security`, `control`.

## Використання

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# smoke усіх трьох плагінів на поточному HEAD
python -m evalkit.run --refs HEAD --models haiku --smoke

# повний прогін двох версій одного плагіна і порівняння
python -m evalkit.run --plugins java-developer --refs <old-commit> HEAD --models sonnet
python -m evalkit.compare --plugin java-developer --a <old-commit> --b HEAD --model sonnet --report

# один кейс для налагодження (не потрапляє в compare)
python -m evalkit.run --plugins qa-docs --refs HEAD --models haiku --case qd-ask-refund-vs-jira --runs 1

# подивитися, що саме отримає claude plugin eval
python -m evalkit.tracker preview --plugin qa-docs --out /tmp/pe-preview
```

У `claude-plugins` зараз немає git-тегів, тож версії задаються комітами або гілками. Поставте теги на релізи, і `--refs v0.10.0 v0.11.0` запрацює.

## Як додати тікет або кейс

- **Тікет**: новий `tracker/tickets/<n>.yaml` (поля як у сусідніх). Він автоматично з'явиться і як GitHub issue `#n`, і як `DEMO-n` у Jira. Сторінка Confluence — `tracker/pages/<id>.yaml`, посилання з тікета через `links: [{title, page_id}]`.
- **Кейс**: тека `suites/<plugin>/cases/<name>/` з `prompt.md` (frontmatter: `tags`, `max_turns`, `timeout_seconds`, `allowed_tools`), `graders/*.md` і `fixture.yaml`. Мок, який треба змінити лише для одного кейсу, кладеться в `<case>/mocks/<server>/<tool>.md`.
- Зміна тікета, сторінки чи синтетичного проєкту змінює хеш набору, тому кеш автоматично стає недійсним, а `compare` не порівнює прогони на різних наборах.

## HTML-звіт

`reports/index.html` - один самодостатній файл без зовнішніх залежностей (працює офлайн, світла і темна теми). Він оновлюється автоматично після кожного `run` і `compare`. Вручну:

```bash
python -m evalkit.html_report --open
```

Що в ньому:

- фільтри: плагін, модель, прогін; налагоджувальні прогони з `--case` приховані, поки не ввімкнути перемикач;
- плитки: загальний бал, кейси й повтори, що пройшли, вартість, тривалість, неоцінені повтори;
- бали кейсів: смуга - середній бал, точки - окремі повтори; при наведенні видно, які грейдери не пройшли, клік відкриває кейс у таблиці;
- вартість і ходи агента по кейсах (риска - ліміт `max_turns`);
- тренд загального балу по повних дійсних прогонах, лінія на модель;
- порівняння двох прогонів: Δ по кейсах, бутстреп-інтервал, вердикт, регресії контрольних кейсів, попередження про різні набори чи версії CLI;
- таблиця кейсів з сортуванням і фільтром за тегом; рядок розгортається до промпту, помилок і вердикту кожного грейдера в кожному повторі з поясненням.

Прогін, у якому хоч один повтор обірвався до оцінювання (ліміт плану, rate limit, помилка API), позначається як недійсний: у звіті з'являється банер, а `compare`, тренд і кеш такий прогін не враховують.

## Зберігання результатів

| Що | Де |
| --- | --- |
| Сирий результат і маніфест прогону (джерело правди) | `results/<key>/aggregate.json`, `manifest.json` (поза git) |
| Журнал витрат для денного бюджету | `results/ledger.jsonl` |
| Картки порівнянь | `reports/<plugin>/*.md` (у git) |
| Індекс для запитів і трендів | MariaDB, якщо задано `PE_DB_URL` |

MariaDB стоїть на `dovg.cloud` у контейнері `plugin-eval-db` (`/opt/projects/plugin-eval-db`, MariaDB 11.4). Вона слухає лише `127.0.0.1:3307` на сервері, тож доступ іде через SSH-тунель. Якщо в `.env` задано `PE_DB_SSH`, `evalkit` відкриває тунель сам і закриває його після завершення.

```
PE_DB_URL=mysql://plugin_eval:<пароль>@127.0.0.1:3307/plugin_eval
PE_DB_SSH=-p 2222 root@dovg.cloud
```

`run` записує кожен прогін, `compare` записує порівняння. Якщо база недоступна, прогін не втрачається: файли вже записані, а в базу їх можна дописати пізніше.

```bash
python -m evalkit.db init      # створити або оновити таблиці (міграції версійовані)
python -m evalkit.db import    # перезаписати в базу всі прогони з results/ (повторний запуск безпечний)
python -m evalkit.db status    # кількість рядків і останні прогони
```

Таблиці:

| Таблиця | Рядок |
| --- | --- |
| `runs` | один виклик `claude plugin eval` (плагін, коміт, модель, хеш набору, версія CLI, бал, вартість) |
| `case_results` | кейс у прогоні: бал, розкид між повторами, теги, чи контрольний |
| `attempts` | один повтор кейсу: бал, ходи, вартість, помилка, виклики моків |
| `grader_results` | вердикт кожного грейдера з поясненням |
| `comparisons` | результат `compare`: Δ, інтервал, вердикт, контрольні регресії |
| `case_trend` (view) | бали кейсів по комітах для повних прогонів, основа для графіків |

Бекап: `/opt/projects/plugin-eval-db/backup.sh` запускається вручну (наприклад, перед зміною схеми).

## Тести

```bash
python3 -m unittest discover -s tests -v
```

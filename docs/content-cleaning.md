# Очистка контента Stack Exchange

`app.processing.html` использует HTML parser BeautifulSoup с `lxml`; регулярные выражения не
используются как HTML sanitizer. Вход и нормализованный результат ограничены настройками
`MAX_HTML_BODY_BYTES` и `MAX_DOCUMENT_TEXT_LENGTH`.

Pipeline детерминирован:

1. проверка размера UTF-8;
2. parser decode HTML entities;
3. Unicode NFC и LF line endings;
4. удаление `script`, `style`, `iframe`, `object`, `embed`, SVG/MathML и комментариев;
5. удаление event-handler attributes и `javascript:` URL;
6. извлечение headings, paragraphs, lists, quotes и code;
7. нормализация whitespace только вне code;
8. ограничение пустых строк и trim.

`pre/code` преобразуется в fenced block. Отступы, переносы, HTML entities и специальные символы
Python сохраняются. Язык указывается только при явном `language-python`/`lang-python`; код не
исполняется и не компилируется. Inline code остаётся в обратных кавычках.

Backend хранит нормализованный plain text и sanitized HTML. Editor/public API не рендерит raw
поле `body_html`. Audit, job events и failures также не содержат исходный HTML.

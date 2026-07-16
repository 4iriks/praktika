# Детерминированный чанкинг

`app.processing.chunking.DocumentChunker` принимает canonical document и независимую абстракцию
подсчёта токенов. Текущий приблизительный counter не связывает corpus с будущей embedding model.

Настройки по умолчанию:

- target: 650 tokens;
- maximum: 900;
- overlap: 80;
- minimum: 40.

Atomic blocks — heading, paragraph/list/quote и fenced code. Chunker сохраняет границы QUESTION,
ACCEPTED_ANSWER и ANSWER, не разрезает code block, если он помещается, а большой code делит по
строкам с сохранением отступов. Overlap применяется к тексту и не копирует огромный code block.

Каждый chunk содержит section type, ordinal, document version, optional answer reference, text,
contextual text (title, sorted tags, section), SHA-256, размеры и `has_code`. `chunk_key` стабилен
для `(document_id, version, ordinal, content_hash)`.

Неизменившийся `content_hash` не создаёт новые chunks. При смысловом изменении новая document
version и её chunks фиксируются атомарно; поисковые index statuses остаются `NOT_INDEXED` или
`OUTDATED` до Этапа 6.

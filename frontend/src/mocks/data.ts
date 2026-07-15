import type { Document, PublicSystemStatus, Tag } from '../types';

interface DocumentSeed {
  title: string;
  tags: string[];
  question: string;
  answer: string;
  code?: string;
  accepted?: boolean;
  author?: string;
}

const tagNames: Record<string, string> = {
  python: 'Python',
  lists: 'Списки',
  dictionary: 'Словари',
  asyncio: 'asyncio',
  pandas: 'pandas',
  django: 'Django',
  flask: 'Flask',
  fastapi: 'FastAPI',
  selenium: 'Selenium',
  numpy: 'NumPy',
  requests: 'requests',
  oop: 'Классы',
  decorators: 'Декораторы',
  exceptions: 'Исключения',
  imports: 'Импорты',
  venv: 'venv',
  sqlalchemy: 'SQLAlchemy',
  pytest: 'pytest',
  csv: 'CSV',
  typing: 'typing',
};

export const availableTags: Tag[] = Object.entries(tagNames).map(([slug, name]) => ({
  slug,
  name,
}));

function createTag(slug: string): Tag {
  return { slug, name: tagNames[slug] ?? slug };
}

const seeds: DocumentSeed[] = [
  {
    title: 'Как удалить дубликаты из списка, сохранив порядок элементов?',
    tags: ['python', 'lists'],
    question:
      'Есть список с повторяющимися значениями. Нужно получить уникальные элементы и не потерять исходный порядок.',
    answer:
      'Для хешируемых значений используйте dict.fromkeys: словарь сохраняет порядок добавления ключей. Для нехешируемых объектов потребуется явная проверка.',
    code: 'items = [3, 1, 3, 2, 1]\nunique_items = list(dict.fromkeys(items))\nprint(unique_items)  # [3, 1, 2]',
    accepted: true,
    author: 'list_walker',
  },
  {
    title: 'Безопасное объединение двух словарей в Python',
    tags: ['python', 'dictionary'],
    question:
      'Как объединить настройки по умолчанию с пользовательскими и понять, какие значения будут перезаписаны?',
    answer:
      'Оператор | создаёт новый словарь, причём значения правого операнда имеют приоритет. Для старых версий Python подходит распаковка.',
    code: "defaults = {'timeout': 5, 'retries': 2}\ncustom = {'timeout': 10}\nconfig = defaults | custom",
  },
  {
    title: 'Когда использовать await, а когда create_task в asyncio?',
    tags: ['python', 'asyncio'],
    question:
      'Последовательные await не дают параллельного выполнения. Как корректно запустить несколько корутин конкурентно?',
    answer:
      'await приостанавливает текущую корутину до результата. create_task планирует корутину независимо; созданные задачи нужно ожидать и обрабатывать их ошибки.',
    code: 'first = asyncio.create_task(load_user())\nsecond = asyncio.create_task(load_orders())\nuser, orders = await asyncio.gather(first, second)',
    accepted: true,
  },
  {
    title: 'Разница между asyncio.gather и asyncio.create_task',
    tags: ['python', 'asyncio'],
    question:
      'В каких случаях достаточно gather, а когда нужно хранить отдельный объект Task и управлять его жизненным циклом?',
    answer:
      'gather группирует awaitable и возвращает результаты в исходном порядке. create_task полезен, когда задачу нужно отменять, проверять или ожидать позднее.',
    code: 'results = await asyncio.gather(fetch_a(), fetch_b())\nbackground = asyncio.create_task(refresh_cache())',
    accepted: true,
  },
  {
    title: 'Чтение большого CSV-файла через pandas без переполнения памяти',
    tags: ['python', 'pandas', 'csv'],
    question:
      'CSV не помещается в оперативную память. Нужно обрабатывать данные порциями и агрегировать результат.',
    answer:
      'Передайте chunksize в read_csv и обрабатывайте каждый DataFrame отдельно. Сразу ограничьте usecols и задайте dtype.',
    code: "total = 0\nfor chunk in pd.read_csv('events.csv', chunksize=100_000, usecols=['amount']):\n    total += chunk['amount'].sum()",
    accepted: true,
  },
  {
    title: 'Почему DataFrame SettingWithCopyWarning появляется после фильтрации?',
    tags: ['python', 'pandas'],
    question:
      'После выбора строк и присваивания столбцу pandas показывает SettingWithCopyWarning. Как записывать значение однозначно?',
    answer:
      'Используйте .loc для изменения исходного DataFrame или вызовите .copy, если нужна независимая выборка.',
    code: "filtered = frame.loc[frame['active']].copy()\nfiltered.loc[:, 'status'] = 'ready'",
  },
  {
    title: 'Оптимизация select_related и prefetch_related в Django ORM',
    tags: ['python', 'django'],
    question:
      'Список объектов делает множество дополнительных SQL-запросов при обращении к связанным моделям.',
    answer:
      'select_related применяйте к одиночным внешним ключам, а prefetch_related — к коллекциям и обратным связям.',
    code: "posts = Post.objects.select_related('author').prefetch_related('tags')",
    accepted: true,
  },
  {
    title: 'Как написать middleware для обработки ошибок во Flask?',
    tags: ['python', 'flask', 'exceptions'],
    question:
      'Нужно единообразно логировать необработанные исключения и возвращать JSON, не раскрывая детали пользователю.',
    answer:
      'Зарегистрируйте errorhandler, логируйте исключение через app.logger и возвращайте стабильную структуру ошибки.',
    code: "@app.errorhandler(Exception)\ndef handle_error(error):\n    app.logger.exception('Request failed')\n    return {'error': 'internal_error'}, 500",
  },
  {
    title: 'Как работает dependency injection в FastAPI?',
    tags: ['python', 'fastapi'],
    question:
      'Как вынести проверку заголовка и получение сессии базы данных из обработчика FastAPI?',
    answer:
      'Depends объявляет зависимость в сигнатуре. FastAPI строит граф зависимостей, вызывает их на запрос и поддерживает очистку ресурсов через yield.',
    code: "def get_session():\n    with Session() as session:\n        yield session\n\n@app.get('/items')\ndef items(session: Session = Depends(get_session)):\n    return session.query(Item).all()",
    accepted: true,
  },
  {
    title: 'Ожидание элемента в Selenium без time.sleep',
    tags: ['python', 'selenium'],
    question:
      'Тест нестабилен из-за фиксированных пауз. Как дождаться кликабельности элемента с явным таймаутом?',
    answer:
      'Используйте WebDriverWait вместе с expected_conditions. Ожидание завершится сразу после выполнения условия.',
    code: "wait = WebDriverWait(driver, 10)\nbutton = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-test=save]')))\nbutton.click()",
    accepted: true,
  },
  {
    title: 'Векторизация вычислений NumPy вместо цикла Python',
    tags: ['python', 'numpy'],
    question:
      'Как заменить медленный цикл для нормализации значений массива и корректно обработать нулевой диапазон?',
    answer:
      'Операции NumPy выполняются над всем массивом. Перед делением проверьте разницу максимума и минимума.',
    code: 'span = values.max() - values.min()\nnormalized = np.zeros_like(values, dtype=float) if span == 0 else (values - values.min()) / span',
  },
  {
    title: 'Таймауты и повторные попытки в requests',
    tags: ['python', 'requests'],
    question:
      'HTTP-запрос может зависнуть или временно получить 503. Как настроить таймауты и ограниченные повторы?',
    answer:
      'Всегда задавайте timeout. Для повторов подключите HTTPAdapter с Retry и ограничьте методы и статусы.',
    code: "retry = Retry(total=3, status_forcelist=[502, 503, 504])\nsession = requests.Session()\nsession.mount('https://', HTTPAdapter(max_retries=retry))\nresponse = session.get(url, timeout=(3, 15))",
    accepted: true,
  },
  {
    title: 'dataclass или обычный класс: что выбрать для модели данных?',
    tags: ['python', 'oop', 'typing'],
    question:
      'Класс в основном хранит типизированные значения. Нужны сравнение, repr и безопасное значение списка по умолчанию.',
    answer:
      'dataclass генерирует служебные методы. Для изменяемых значений используйте field(default_factory=...), а не общий список.',
    code: '@dataclass(slots=True)\nclass User:\n    name: str\n    roles: list[str] = field(default_factory=list)',
    accepted: true,
  },
  {
    title: 'Декоратор с аргументами и сохранением сигнатуры функции',
    tags: ['python', 'decorators'],
    question:
      'Нужно измерять время вызова, передавая метку в декоратор, и не потерять имя и документацию исходной функции.',
    answer: 'Создайте фабрику декораторов и примените functools.wraps к внутренней функции.',
    code: 'def timed(label: str):\n    def decorate(func):\n        @functools.wraps(func)\n        def wrapper(*args, **kwargs):\n            return func(*args, **kwargs)\n        return wrapper\n    return decorate',
  },
  {
    title: 'Как создать собственное исключение и не перехватывать всё подряд?',
    tags: ['python', 'exceptions'],
    question:
      'Библиотеке нужно сообщать о некорректной конфигурации, сохраняя понятную иерархию ошибок.',
    answer:
      'Создайте предметный класс от Exception или ValueError и перехватывайте только ожидаемые типы на границе приложения.',
    code: "class ConfigurationError(ValueError):\n    pass\n\nif not api_url:\n    raise ConfigurationError('api_url is required')",
    accepted: true,
  },
  {
    title: 'Почему возникает ModuleNotFoundError в локальном проекте?',
    tags: ['python', 'imports', 'venv'],
    question:
      'Модуль установлен, но интерпретатор его не видит. IDE и терминал могут использовать разные окружения.',
    answer:
      'Проверьте путь текущего python и pip, активируйте нужное виртуальное окружение и запускайте пакет через python -m.',
    code: 'python -c "import sys; print(sys.executable)"\npython -m pip show package_name\npython -m app.main',
    accepted: true,
  },
  {
    title: 'Создание и воспроизводимая настройка виртуального окружения',
    tags: ['python', 'venv'],
    question:
      'Как изолировать зависимости проекта и передать команде точный список библиотек без каталога окружения?',
    answer:
      'Создайте окружение через python -m venv, активируйте его и фиксируйте зависимости в текстовом файле или lock-файле.',
    code: 'python -m venv .venv\nsource .venv/bin/activate\npython -m pip install -r requirements.txt',
  },
  {
    title: 'Управление транзакцией в SQLAlchemy 2.0',
    tags: ['python', 'sqlalchemy'],
    question:
      'Как гарантировать commit при успехе и rollback при исключении во время нескольких изменений?',
    answer:
      'Контекст session.begin управляет границами транзакции и откатывает изменения при исключении.',
    code: 'with Session(engine) as session:\n    with session.begin():\n        session.add(order)\n        session.add(audit_event)',
    accepted: true,
  },
  {
    title: 'Параметризация тестов в pytest',
    tags: ['python', 'pytest'],
    question:
      'Одна и та же проверка нужна для нескольких входных значений, но копировать тесты не хочется.',
    answer:
      'pytest.mark.parametrize создаёт отдельный тестовый случай для каждого набора аргументов и понятно показывает сбой.',
    code: "@pytest.mark.parametrize(('value', 'expected'), [(2, True), (3, False)])\ndef test_is_even(value, expected):\n    assert is_even(value) is expected",
    accepted: true,
  },
  {
    title: 'Асинхронные фикстуры pytest для тестирования API',
    tags: ['python', 'pytest', 'asyncio'],
    question:
      'Как подготовить асинхронный клиент один раз на тест и корректно закрыть его после проверки?',
    answer:
      'Используйте pytest-asyncio и async-фикстуру с yield. Область фикстуры выбирайте по цене ресурса.',
    code: "@pytest_asyncio.fixture\nasync def client():\n    async with AsyncClient(base_url='http://test') as value:\n        yield value",
  },
  {
    title: 'Обработка нескольких типов исключений с сохранением причины',
    tags: ['python', 'exceptions'],
    question:
      'Нужно преобразовать низкоуровневую ошибку чтения JSON в предметную, но не потерять исходный traceback.',
    answer:
      'Используйте raise NewError(...) from error: цепочка исключений сохранит первоначальную причину.',
    code: "try:\n    config = json.loads(raw)\nexcept (TypeError, json.JSONDecodeError) as error:\n    raise ConfigurationError('Invalid JSON configuration') from error",
    accepted: true,
  },
  {
    title: 'Постраничная выдача FastAPI с проверкой параметров',
    tags: ['python', 'fastapi'],
    question:
      'Как ограничить page и page_size, чтобы клиент не мог запросить отрицательную страницу или слишком большой ответ?',
    answer:
      'Опишите ограничения через Query или Annotated, затем вычислите offset. Возвращайте общее число и метаданные страницы.',
    code: "PageSize = Annotated[int, Query(ge=1, le=100)]\n\n@app.get('/items')\ndef list_items(page: int = Query(1, ge=1), page_size: PageSize = 20):\n    return repository.list(offset=(page - 1) * page_size, limit=page_size)",
    accepted: false,
  },
];

function makeDocument(seed: DocumentSeed, index: number): Document {
  const id = 'py-' + String(1001 + index);
  const publishedAt = new Date(Date.UTC(2023 + (index % 3), (index * 3) % 12, 2 + (index % 24)));
  const accepted = seed.accepted ?? index % 4 !== 1;
  const base = 0.91 - (index % 7) * 0.037;
  const firstAnswer = {
    id: id + '-a1',
    author: 'answer_' + ((index % 8) + 1),
    body: seed.answer,
    codeBlocks: seed.code ? [seed.code] : [],
    score: 8 + ((index * 17) % 94),
    accepted,
    createdAt: new Date(publishedAt.getTime() + 86_400_000).toISOString(),
  };
  const answers = [firstAnswer];

  if (index % 3 === 0) {
    answers.push({
      id: id + '-a2',
      author: 'python_reader',
      body: 'Альтернативный вариант зависит от версии Python и требований к данным. Измеряйте поведение на реалистичном наборе и явно обрабатывайте пограничные случаи.',
      codeBlocks: [],
      score: 2 + (index % 11),
      accepted: false,
      createdAt: new Date(publishedAt.getTime() + 172_800_000).toISOString(),
    });
  }

  return {
    id,
    title: seed.title,
    sourceUrl: 'https://ru.stackoverflow.com/questions/' + String(900001 + index),
    publishedAt: publishedAt.toISOString(),
    author: seed.author ?? 'python_user_' + ((index % 9) + 1),
    views: 430 + ((index * 1327) % 48_000),
    score: 4 + ((index * 13) % 186),
    tags: seed.tags.map(createTag),
    question: {
      body: seed.question,
      codeBlocks: index % 5 === 2 && seed.code ? [seed.code.split('\n')[0] ?? seed.code] : [],
    },
    answers,
    chunkCount: 3 + (index % 8),
    indexedAt: new Date(Date.UTC(2026, 6, 15, 14, index % 50)).toISOString(),
    bm25Status: 'READY',
    vectorStatus: 'READY',
    contentHash: 'sha256:' + (104_729 * (index + 17)).toString(16).padStart(12, '0'),
    saved: false,
    scores: {
      bm25Score: Number((7.2 + ((index * 19) % 75) / 10).toFixed(3)),
      vectorScore: Number((base - 0.035).toFixed(3)),
      rerankerScore: Number((base + 0.021).toFixed(3)),
      finalScore: Number(base.toFixed(3)),
    },
  };
}

export const mockDocuments: Document[] = seeds.map(makeDocument);

export const mockSystemStatus: PublicSystemStatus = {
  services: [
    { name: 'API', state: 'online', latencyMs: 18 },
    { name: 'PostgreSQL', state: 'online', latencyMs: 7 },
    { name: 'Qdrant', state: 'online', latencyMs: 12 },
    { name: 'Ollama', state: 'online', latencyMs: 24 },
    { name: 'Index', state: 'ready' },
  ],
  model: 'Qwen через Ollama',
  modelContext: 32_768,
  indexedDocuments: 25_000,
  indexedChunks: 82_460,
  updatedAt: '12 минут назад',
};

# Конфігурація

Клієнтський пакет: client.yaml, agents/, knowledge/, branding/, deployment/.
Секрети передаються середовищем або secret store, у файлах лише посилання.

Поля: schema_version, organization, branding, enabled_modules,
agent definitions, provider references, tool allowlists, locale, timezone,
session limits, retention policy.

Файл імпортується як валідована чернетка. Runtime читає опубліковану
версію з бази. Експорт повертає конфігурацію без секретів.
Не допускається неявне перезаписування UI-змін файлом.

Стани: draft -> published -> active binding.
Публікація створює незмінний snapshot. Активація атомарно змінює binding.
Активні розмови зберігають свою версію.

JSON Schema та API-контракт реалізуються у VF-002.

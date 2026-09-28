# Backlog

Status: VF-001 implementation and hosted CI passed; owner manual acceptance
remains pending. VF-002 implementation and local automated checks passed;
owner manual acceptance remains pending. VF-003 code and VF-009 console code
passed local automated checks in the isolated working copy. A bounded live
browser audio smoke test and real console inspection passed. The owner confirmed
hearing a response and seeing both transcript sides; interruption,
disconnection, and two-browser board acceptance remain open.
VF-005 has bounded outbound and provider-neutral inbound routing code in
progress. The owner postponed the carrier decision after discussing a paid
Twilio test with a foreign number. A +380 carrier and live phone acceptance
remain open. VF-004 and VF-006 through VF-008
have not started.

- VF-001: основа репозиторію та локальний запуск.
- VF-002: конфігурації та версії агентів.
- VF-003: реальна голосова сесія в браузері.
- VF-009: reusable operator console for real browser sessions; VF-003 live
  acceptance remains pending. See `tasks/VF-009.md`.
- VF-005: вхідна телефонія SIP та разовий вихідний дзвінок з панелі;
  потрібен номер +380 для постійних вхідних дзвінків. Для першого тесту
  власник погодив платний Twilio та іноземний номер. Див.
  `tasks/VF-005.md`.
- VF-004: SDK інтеграцій і контроль виконання інструментів.
- VF-006: приклад автосервісу з брендингом і записом.
- VF-007: runner сценаріїв, звіти, порівняння.
- VF-008: self-hosting, staging, сумісність оновлень і реліз.

Окремий напрям: мінімальний voice-fleet-dev, після визначення процесу.
Перші три задачі деталізовані в окремих файлах.

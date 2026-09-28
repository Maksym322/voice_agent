# Рішення

## Погоджено
- Відкритий продукт і незалежні інсталяції клієнтів.
- Кастомізація через конфігурації та інтеграції.
- LiveKit як основа; Twilio як варіант телефонії.
- Демоклієнт після ядра.
- AI реалізує; власник проводить ручне приймання.
- Центральний AI-оператор — наступний проєкт.

## Пропозиції для старту
- Python/FastAPI, React/TypeScript, PostgreSQL, Compose.
- Браузерний голос перед телефонією.
- Окремий репозиторій voice-fleet-dev для плагіна Codex.

## Відкрито
- Ліцензія та GitHub owner/visibility.
- STT/LLM/TTS провайдери, бюджет і потрібні мови.
- LiveKit Cloud чи self-hosted медіасервер.
- Хостинг staging та production.
- Остаточний спосіб автентифікації.
- Записи аудіо та строки зберігання.

## VF-005: напрям від власника, 2026-09-27

The owner initially selected Twilio to call their own +380 phone, but their
account asks for a $20 paid upgrade and does not permit creating a trial SIP
trunk. This exceeds the owner's $5 initial carrier-funding cap. Twilio is on
hold; the +380 inbound provider, outbound provider, caller ID, and ongoing
carrier budget remain open. No paid call has been made.

On 2026-09-28 the owner relaxed the initial $5 cap for a telephone test and
chose to proceed with paid Twilio despite possible identity verification. A
foreign voice-capable Twilio number is acceptable for the test, including as
Caller ID. This enables testing an outbound call to their own +380 phone and,
after inbound work is implemented, a call into the foreign test number. The
longer-term goal of a Ukrainian +380 inbound number remains open. No payment
or real SIP call has been made by this project.

Later on 2026-09-28 the owner postponed the carrier decision and asked to
finish provider-neutral preparation first. No Twilio purchase or carrier
setup is currently required to keep developing browser voice, the operator
console, or the inbound routing code. Real phone acceptance remains pending.

- Потрібні вхідні дзвінки на український номер +380 та разові вихідні
  дзвінки агентом на +380. Масові кампанії залишаються поза MVP.
- Попередній ліміт $5 для короткого тесту скасовано 2026-09-28 для Twilio.
  Жодної платної покупки або виклику ще не виконано в межах проєкту.
  Витрати AI/LiveKit сервісів обліковуються окремо.
- [Twilio](https://www.twilio.com/en-us/sip-trunking/pricing/ua) зараз не має
  голосових номерів в Україні, тому попередня пропозиція Twilio як єдиного
  провайдера не підходить для номера +380.
- [Zadarma](https://zadarma.com/ua/tariffs/numbers/ukraine/national/) показує
  національний +38091 за $3/місяць без плати за підключення; це лише кандидат.
  Публікує мінімальне поповнення $5. Для вхідного напряму описує переадресацію
  на зовнішній SIP URI без реєстрації. Окрема офіційна інструкція Zadarma для
  Vapi/Retell описує вихідний AI SIP через `pbx.zadarma.com` з логіном і паролем
  внутрішнього номера АТС. Це кандидат для LiveKit outbound trunk без статичної
  IP; реальний маршрут LiveKit → Zadarma ще не перевірений. IP-авторизований
  Zadarma SIP trunk є іншим режимом і для цього тесту не потрібний.
  Наявність номера, можлива перевірка особи та сумарна ціна перевіряються
  перед покупкою; вибір провайдера відкритий.

## VF-003: конкретна пропозиція для live-приймання (не погоджено)

Для короткого контрольованого тесту пропонується LiveKit Cloud,
англійська мова, Deepgram Nova-3 STT, OpenAI GPT-4o mini LLM,
Cartesia Sonic 3 TTS і ліміт витрат $10, заданий на боці провайдерів.
Саме цей набір зараз підтримує реалізований worker. Альтернатива для
медіасервера — власний LiveKit; URL і ключі передаються через середовище.
Зміна STT/LLM/TTS набору потребує окремої адаптації worker, а не тільки
редагування JSON. Реальні ключі зберігаються лише в ігнорованому `.env`
або secret store. Власник погодив один синтетичний live-тест до 180 секунд
українською з LiveKit Cloud, Deepgram, Gemini та Cartesia. Це не затверджує
продакшн-набір провайдерів чи бюджет для клієнтських розмов.
Як альтернатива OpenAI LLM для короткого тесту реалізовано прямий Gemini API
з `gemini-3.5-flash-lite` на безплатному тарифі; старі опубліковані версії з
`gemini-2.5-flash-lite` залишаються валідними для проєктів із доступом.
26 вересня 2026 року Google відхилив 2.5 Flash-Lite для нового ключа (404).
Власник погодив 3.5 Flash-Lite для повторного короткого тесту; двосторонній
синтетичний браузерний дзвінок пройшов. За умовами Google дані
безплатного тарифу можуть використовуватися для поліпшення його продуктів;
реальні клієнтські розмови потребують окремого рішення про цей режим або
платного тарифу. Deepgram STT і Cartesia TTS залишаються окремими сервісами.

Рішення про стек підтверджуються у VF-001; голосові провайдери у VF-003.
Не позначати пропозицію як погоджену без підстав.

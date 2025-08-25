## GPUniq Agent

Интеллектуальный агент для подключения к GPUniq

### Требования
- Python 3.8+
- Docker установлен и доступен в системе (для запуска контейнеров)

### Быстрый старт

1. Клонирование репозитория
```bash
git clone https://github.com/GPUniq/agent.git
```

2. Переход в директорию проекта
```bash
cd agent
```

3. Создание виртуального окружения
```bash
python3 -m venv .venv
```

4. Активация виртуального окружения
- macOS/Linux:
```bash
source .venv/bin/activate
```
- Windows (PowerShell):
```bash
.venv\Scripts\Activate.ps1
```

5. Установка зависимостей
```bash
pip install -r requirements.txt
```

6. Запуск агента через nohup (в фоне)
```bash
nohup python3 agent.py <YOUR_SECRET_KEY> > agent.log 2>&1 &
```

Проверка логов:
```bash
tail -f agent.log
```

Отключение виртуального окружения:
```bash
deactivate
```

---
Исходный код: https://github.com/GPUniq/agent.git 
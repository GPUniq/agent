## GPUniq Agent

Интеллектуальный агент для подключения к GPUniq

### Платформа
- Ubuntu 24.04 LTS

### Предварительная установка (Ubuntu 24.04)
```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

# Docker (рекомендуется для запуска контейнеров)
sudo apt install -y docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker
# Проверка
docker ps
```

### Быстрый старт (Ubuntu 24.04)

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
```bash
source .venv/bin/activate
```

5. Установка зависимостей
```bash
pip install -r requirements.txt
```

6. Запуск агента в фоне через nohup
```bash
nohup python3 agent.py <YOUR_SECRET_KEY> > agent.log 2>&1 &
```

Проверка логов:
```bash
tail -f agent.log
```

Остановка процесса (пример):
```bash
pkill -f "python3 agent.py"
```

---
Репозиторий: https://github.com/GPUniq/agent.git 
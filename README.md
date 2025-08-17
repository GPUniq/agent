# GPUniq Agent 🤖

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/Docker-Required-green.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen.svg)](https://api.gpuniq.ru)

**GPUniq Agent** - это интеллектуальный агент для управления Docker контейнерами с поддержкой GPU, SSH доступа и автоматического мониторинга ресурсов. Агент предназначен для работы в распределенной среде и обеспечивает полную автоматизацию развертывания и управления контейнерами.

## 🚀 Основные возможности

### 🐳 Docker Management
- ✅ **Автоматическая установка и настройка Docker**
- ✅ **Управление контейнерами с GPU поддержкой**
- ✅ **Автоматическое получение свободных портов**
- ✅ **Мониторинг состояния контейнеров**
- ✅ **Автоматическая очистка остановленных контейнеров**

### 🔧 System Monitoring
- ✅ **Мониторинг CPU, RAM, GPU, дисков и сети**
- ✅ **Автоматическое определение аппаратной конфигурации**
- ✅ **Отслеживание температуры CPU**
- ✅ **Определение геолокации по IP адресу**
- ✅ **Heartbeat система для проверки работоспособности**

### 🖥️ GPU Support
- ✅ **Автоматическое определение GPU (NVIDIA, AMD, Intel)**
- ✅ **Установка драйверов и инструментов**
- ✅ **Поддержка NVIDIA Container Runtime**
- ✅ **Мониторинг GPU использования**

### 🔐 SSH Integration
- ✅ **Автоматическое получение свободного SSH порта**
- ✅ **Ожидание готовности SSH сервиса**
- ✅ **Передача информации о подключении на сервер**
- ✅ **Тестирование SSH соединений**

### 🔄 Auto-Update
- ✅ **Автоматическое обновление кода через Git**
- ✅ **Периодическая синхронизация с сервером**
- ✅ **Обработка конфликтов зависимостей**

## 📋 Требования

### Системные требования
- **OS**: Linux (Ubuntu 18.04+, CentOS 7+, Debian 9+)
- **Python**: 3.7 или выше
- **RAM**: Минимум 2GB (рекомендуется 4GB+)
- **Storage**: Минимум 10GB свободного места

### Обязательные компоненты
- **Docker**: Автоматически устанавливается агентом
- **Git**: Для обновления кода
- **Интернет соединение**: Для подключения к API

### Поддерживаемые GPU
- **NVIDIA**: GTX/RTX серии, Tesla, Quadro
- **AMD**: Radeon RX серии, Radeon Pro
- **Intel**: Intel Graphics, Intel Arc

## 🛠️ Установка и запуск

### Быстрый старт

1. **Клонируйте репозиторий:**
```bash
git clone <repository-url>
cd agent
```

2. **Запустите агента:**
```bash
python installator.py <your_secret_key>
```

### Подробная установка

1. **Установите Python зависимости:**
```bash
pip install psutil requests
```

2. **Настройте права доступа:**
```bash
chmod +x installator.py
```

3. **Запустите с вашим секретным ключом:**
```bash
python installator.py <secret_key>
```

## 🔧 Конфигурация

### Переменные окружения

```bash
# API endpoint (по умолчанию: https://api.gpuniq.ru)
export GPUNIQ_API_URL="https://api.gpuniq.ru"

# Логирование
export GPUNIQ_LOG_LEVEL="INFO"
```

### Файлы конфигурации

- `.agent_id` - Сохраняет ID агента между запусками
- Логи автоматически сохраняются в stdout

## 🐳 Docker образы с SSH

### Создание базового образа с SSH

```dockerfile
FROM ubuntu:22.04

# Установка SSH сервера
RUN apt-get update && apt-get install -y \
    openssh-server \
    curl \
    wget \
    git \
    && rm -rf /var/lib/apt/lists/*

# Настройка SSH
RUN mkdir /var/run/sshd
RUN echo 'root:password' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# SSH login fix
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
```

### Образ с GPU поддержкой

```dockerfile
FROM nvidia/cuda:11.8-devel-ubuntu22.04

# Установка SSH и CUDA инструментов
RUN apt-get update && apt-get install -y \
    openssh-server \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Настройка SSH
RUN mkdir /var/run/sshd
RUN echo 'root:password' | chpasswd
RUN sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
```

## 📊 Мониторинг и API

### Системная информация

Агент собирает и отправляет следующую информацию:

```json
{
  "hostname": "server-01",
  "ip_address": "192.168.1.100",
  "location": "Moscow, Russia",
  "status": "online",
  "cpu_usage": 45.2,
  "memory_usage": 67.8,
  "gpu_usage": 23.4,
  "disk_usage": {
    "/": 45.2,
    "/home": 78.9
  },
  "network_usage": {
    "bytes_sent": 1024000,
    "bytes_recv": 2048000
  },
  "cpu_temperature": 65.0,
  "hardware_info": {
    "cpu": "Intel Core i7-9700K",
    "ram": "32GB DDR4",
    "gpu": "NVIDIA RTX 3080"
  }
}
```

### Информация о контейнерах

```json
{
  "status": "running",
  "container_id": "abc123def456",
  "container_name": "task_12345",
  "ssh_host": "192.168.1.100",
  "ssh_port": 21234,
  "ssh_command": "ssh -p 21234 root@192.168.1.100",
  "gpu_usage": 85.2,
  "output": "Container started successfully. SSH ready on 192.168.1.100:21234"
}
```

## 🔐 Безопасность

### Рекомендации по безопасности

1. **SSH настройки:**
   - Измените пароль root в Docker образах
   - Используйте SSH ключи вместо паролей
   - Ограничьте доступ к SSH портам

2. **Сетевая безопасность:**
   - Используйте VPN для подключения
   - Настройте firewall правила
   - Ограничьте доступ к API

3. **Docker безопасность:**
   - Регулярно обновляйте образы
   - Используйте non-root пользователей
   - Сканируйте образы на уязвимости

### Пример безопасного образа

```dockerfile
FROM ubuntu:22.04

# Создание пользователя
RUN useradd -m -s /bin/bash user
RUN mkdir -p /home/user/.ssh

# Копирование SSH ключа
COPY id_rsa.pub /home/user/.ssh/authorized_keys
RUN chown -R user:user /home/user/.ssh
RUN chmod 700 /home/user/.ssh
RUN chmod 600 /home/user/.ssh/authorized_keys

# Установка SSH
RUN apt-get update && apt-get install -y openssh-server
RUN mkdir /var/run/sshd

# Настройка SSH для пользователя
RUN sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
RUN sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
```

## 🚨 Устранение неполадок

### Частые проблемы

#### SSH не подключается
```bash
# Проверьте статус контейнера
docker ps

# Проверьте логи контейнера
docker logs <container_name>

# Проверьте SSH сервис в контейнере
docker exec <container_name> systemctl status ssh
```

#### GPU не определяется
```bash
# Проверьте установку драйверов
nvidia-smi

# Проверьте Docker GPU поддержку
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu22.04 nvidia-smi
```

#### Порт занят
Агент автоматически найдет свободный порт в диапазоне 21234-21334

#### Контейнер не запускается
```bash
# Проверьте права Docker
docker ps

# Проверьте доступное место
df -h

# Проверьте логи агента
tail -f /var/log/syslog | grep installator
```

### Логи и отладка

Агент выводит подробные логи с уровнями:
- `[INFO]` - Информационные сообщения
- `[WARNING]` - Предупреждения
- `[ERROR]` - Ошибки

Для включения отладочного режима:
```bash
export GPUNIQ_LOG_LEVEL="DEBUG"
python installator.py <secret_key>
```

## 📈 Производительность

### Оптимизация

1. **Ресурсы контейнеров:**
   - Ограничьте CPU и RAM для контейнеров
   - Используйте GPU только когда необходимо

2. **Мониторинг:**
   - Настройте интервалы мониторинга
   - Используйте агрегацию данных

3. **Сеть:**
   - Используйте локальные реестры Docker
   - Оптимизируйте размеры образов

### Метрики производительности

- **CPU**: Мониторинг каждые 60 секунд
- **Memory**: Отслеживание использования RAM
- **GPU**: Мониторинг загрузки и температуры
- **Network**: Отслеживание трафика
- **Disk**: Мониторинг свободного места

## 🔄 Обновления

### Автоматические обновления

Агент автоматически:
- Выполняет `git pull` каждые 30 минут
- Отправляет heartbeat каждые 5 минут
- Очищает контейнеры каждые 10 минут

### Ручное обновление

```bash
# Остановите агента
Ctrl+C

# Обновите код
git pull

# Перезапустите
python installator.py <secret_key>
```

## 🤝 API интеграция

### Endpoints

- `POST /api/agent/confirm` - Подтверждение агента
- `POST /api/agent/init` - Инициализация агента
- `POST /api/agent/heartbeat` - Heartbeat
- `GET /api/agent/tasks` - Получение задач
- `POST /api/agent/task/status` - Отправка статуса задачи

### Примеры использования

```python
import requests

# Подтверждение агента
response = requests.post(
    "https://api.gpuniq.ru/api/agent/confirm",
    json={"secret_key": "your_key", "system_info": {...}}
)

# Отправка статуса задачи
response = requests.post(
    "https://api.gpuniq.ru/api/agent/task/status",
    json={
        "agent_id": "agent_123",
        "task_id": "task_456",
        "status": "running",
        "container_info": {...}
    }
)
```

## 📝 Лицензия

Этот проект распространяется под лицензией MIT. См. файл [LICENSE](LICENSE) для подробностей.

## 🤝 Вклад в проект

Мы приветствуем вклад в развитие проекта! Пожалуйста:

1. Форкните репозиторий
2. Создайте ветку для новой функции
3. Внесите изменения
4. Создайте Pull Request

## 📞 Поддержка

- **Документация**: [docs.gpuniq.ru](https://docs.gpuniq.ru)
- **API**: [api.gpuniq.ru](https://api.gpuniq.ru)
- **Issues**: [GitHub Issues](https://github.com/gpuniq/agent/issues)
- **Discord**: [GPUniq Community](https://discord.gg/gpuniq)

---

**GPUniq Agent** - Интеллектуальное управление контейнерами с GPU поддержкой 🚀 
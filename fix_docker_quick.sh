#!/bin/bash

echo "=== Быстрое исправление прав Docker ==="

# Добавить пользователя в группу docker
sudo usermod -aG docker $USER

# Перезапустить Docker
sudo systemctl restart docker

# Применить изменения без перезагрузки
newgrp docker

# Проверить
echo "Проверка прав Docker..."
if docker ps > /dev/null 2>&1; then
    echo "✅ Docker работает без sudo"
else
    echo "❌ Docker все еще требует sudo"
    echo "Попробуйте перезагрузить систему или выйти/войти заново"
fi

echo "Готово!"

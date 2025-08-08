#!/usr/bin/env python3
"""
Скрипт для исправления проблем с psutil
"""

import subprocess
import sys
import os

def fix_psutil():
    print("🔧 Исправление psutil...")
    
    try:
        # Проверяем текущую установку
        print("Проверяем текущую установку psutil...")
        import psutil
        print("✅ psutil работает корректно!")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта psutil: {e}")
    except Exception as e:
        print(f"❌ Ошибка psutil: {e}")
    
    print("Начинаем исправление...")
    
    # Удаляем системную версию
    print("1. Удаляем системную версию psutil...")
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "psutil"], capture_output=True)
    subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "python3-psutil"], capture_output=True)
    
    # Удаляем системную версию через apt
    print("1.1. Удаляем системную версию через apt...")
    subprocess.run(["sudo", "apt-get", "remove", "-y", "python3-psutil"], capture_output=True)
    subprocess.run(["sudo", "apt-get", "purge", "-y", "python3-psutil"], capture_output=True)
    
    # Удаляем файлы вручную
    print("1.2. Удаляем файлы psutil вручную...")
    psutil_paths = [
        "/usr/lib/python3/dist-packages/psutil",
        "/usr/lib/python3/dist-packages/psutil-*",
        "/usr/local/lib/python3.*/dist-packages/psutil",
        "/usr/local/lib/python3.*/site-packages/psutil"
    ]
    
    for path in psutil_paths:
        try:
            subprocess.run(["sudo", "rm", "-rf", path], capture_output=True)
        except:
            pass
    
    # Очищаем кэш
    print("2. Очищаем кэш pip...")
    subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], capture_output=True)
    
    # Устанавливаем заново
    print("3. Устанавливаем psutil заново...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "--force-reinstall", "--no-cache-dir", "psutil"])
        print("✅ psutil установлен успешно!")
    except subprocess.CalledProcessError:
        print("❌ Не удалось установить psutil через pip")
        print("Попробуйте выполнить вручную:")
        print("sudo apt-get remove -y python3-psutil")
        print("pip3 install --user --force-reinstall psutil")
        return False
    
    # Проверяем установку
    print("4. Проверяем установку...")
    try:
        import psutil
        print("✅ psutil работает корректно!")
        return True
    except Exception as e:
        print(f"❌ psutil все еще не работает: {e}")
        
        # Показываем пути Python
        print("5. Диагностика путей Python...")
        import sys
        for path in sys.path:
            print(f"   {path}")
        
        # Пробуем принудительно использовать пользовательскую версию
        print("6. Пробуем принудительно использовать пользовательскую версию...")
        user_site = subprocess.check_output([sys.executable, "-m", "site", "--user-site"], text=True).strip()
        print(f"   Пользовательский site: {user_site}")
        
        # Добавляем пользовательский путь в начало
        if user_site not in sys.path:
            sys.path.insert(0, user_site)
        
        try:
            import psutil
            print("✅ psutil работает с пользовательской версией!")
            return True
        except Exception as e2:
            print(f"❌ psutil все еще не работает: {e2}")
            return False

if __name__ == "__main__":
    if fix_psutil():
        print("🎉 psutil исправлен! Теперь можно запускать installator.py")
    else:
        print("❌ Не удалось исправить psutil")
        sys.exit(1)

# BASE_URL = "http://0.0.0.0:8777"
BASE_URL = "https://api.gpuniq.ru"

import sys
import subprocess
import importlib
import socket
import platform
import re
import threading
import time
import os
import json
import random

AGENT_ID_FILE = ".agent_id"

# Список необходимых пакетов
REQUIRED_PACKAGES = ["psutil", "requests", "docker"]

# Заглушка для psutil (определяем заранее)
class PsutilStub:
    def cpu_percent(self): 
        try:
            with open('/proc/loadavg', 'r') as f:
                load = float(f.read().split()[0])
                return min(load * 25, 100)
        except:
            return 0
    
    def virtual_memory(self): 
        class Mem:
            def __init__(self): 
                try:
                    with open('/proc/meminfo', 'r') as f:
                        meminfo = f.read()
                        total_match = re.search(r'MemTotal:\s+(\d+)', meminfo)
                        free_match = re.search(r'MemAvailable:\s+(\d+)', meminfo)
                        if total_match and free_match:
                            total = int(total_match.group(1))
                            free = int(free_match.group(1))
                            self.percent = ((total - free) / total) * 100
                        else:
                            self.percent = 0
                except:
                    self.percent = 0
        return Mem()
    
    def disk_partitions(self): 
        try:
            partitions = []
            with open('/proc/mounts', 'r') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        mountpoint = parts[1]
                        if mountpoint.startswith('/') and not mountpoint.startswith('/proc'):
                            partitions.append(type('Partition', (), {'mountpoint': mountpoint})())
            return partitions
        except:
            return []
    
    def disk_usage(self, path): 
        class Disk:
            def __init__(self): 
                try:
                    result = subprocess.run(['df', path], capture_output=True, text=True)
                    if result.returncode == 0:
                        lines = result.stdout.strip().split('\n')
                        if len(lines) > 1:
                            parts = lines[1].split()
                            if len(parts) >= 5:
                                used_percent = int(parts[4].rstrip('%'))
                                self.percent = used_percent
                            else:
                                self.percent = 0
                        else:
                            self.percent = 0
                    else:
                        self.percent = 0
                except:
                    self.percent = 0
        return Disk()
    
    def net_io_counters(self, pernic=False): 
        class Net:
            def __init__(self): 
                try:
                    with open('/proc/net/dev', 'r') as f:
                        lines = f.readlines()[2:]
                        total_sent = 0
                        total_recv = 0
                        for line in lines:
                            parts = line.split()
                            if len(parts) >= 10:
                                total_recv += int(parts[1])
                                total_sent += int(parts[9])
                        self.bytes_sent = total_sent
                        self.bytes_recv = total_recv
                except:
                    self.bytes_sent = 0
                    self.bytes_recv = 0
        return Net()

def fix_docker_permissions():
    """Исправляет права доступа к Docker daemon"""
    try:
        print("[INFO] Checking Docker permissions...")
        
        # Проверяем, работает ли Docker без sudo
        try:
            result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("[INFO] Docker permissions are OK")
                return True
        except:
            pass
        
        # Пытаемся исправить права
        print("[INFO] Fixing Docker permissions...")
        
        # Добавляем текущего пользователя в группу docker
        try:
            current_user = subprocess.check_output(['whoami']).decode().strip()
            subprocess.run(['sudo', 'usermod', '-aG', 'docker', current_user], check=True)
            print(f"[INFO] Added user {current_user} to docker group")
        except Exception as e:
            print(f"[WARNING] Failed to add user to docker group: {e}")
        
        # Перезапускаем Docker service
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', 'docker'], check=True)
            print("[INFO] Docker service restarted")
        except Exception as e:
            print(f"[WARNING] Failed to restart Docker service: {e}")
        
        # Применяем изменения группы без перезагрузки
        try:
            subprocess.run(['newgrp', 'docker'], check=True)
            print("[INFO] Applied docker group changes")
        except Exception as e:
            print(f"[WARNING] Failed to apply group changes: {e}")
        
        # Ждем немного и проверяем снова
        time.sleep(3)
        
        # Проверяем Docker без sudo
        try:
            result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("[INFO] Docker permissions fixed successfully")
                return True
        except:
            pass
        
        # Если не работает без sudo, проверяем с sudo
        print("[INFO] Docker requires sudo, checking sudo access...")
        try:
            result = subprocess.run(['sudo', 'docker', 'ps'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("[INFO] Docker accessible with sudo")
                return True
            else:
                print(f"[WARNING] Docker not accessible even with sudo: {result.stderr}")
                return False
        except Exception as e:
            print(f"[WARNING] Docker sudo test failed: {e}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to fix Docker permissions: {e}")
        return False

def check_docker_gpu_support():
    """Проверяет поддержку GPU в Docker"""
    try:
        print("[INFO] Checking Docker GPU support...")
        
        # Проверяем наличие nvidia-container-toolkit
        try:
            result = subprocess.run(['nvidia-container-cli', 'info'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("[INFO] nvidia-container-toolkit found")
                
                # Проверяем, работает ли --gpus флаг
                try:
                    result = subprocess.run(['docker', 'run', '--rm', '--gpus', 'all', 'ubuntu:20.04', 'nvidia-smi'], 
                                          capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        print("[INFO] Docker GPU support confirmed with --gpus flag")
                        return True
                except:
                    pass
                
                # Проверяем, работает ли --runtime=nvidia
                try:
                    result = subprocess.run(['docker', 'run', '--rm', '--runtime=nvidia', 'ubuntu:20.04', 'nvidia-smi'], 
                                          capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        print("[INFO] Docker GPU support confirmed with --runtime=nvidia")
                        return True
                except:
                    pass
                
                print("[WARNING] nvidia-container-toolkit found but GPU access not working")
                return False
        except:
            pass
        
        # Проверяем наличие nvidia-docker
        try:
            result = subprocess.run(['docker', 'run', '--rm', '--runtime=nvidia', 'ubuntu:20.04', 'nvidia-smi'], 
                                  capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print("[INFO] Docker GPU support confirmed with nvidia-docker")
                return True
        except:
            pass
        
        print("[WARNING] Docker GPU support not available")
        return False
    except Exception as e:
        print(f"[WARNING] Docker GPU support check failed: {e}")
        return False

def install_nvidia_container_runtime():
    """Устанавливает и настраивает NVIDIA Container Runtime"""
    print("[INFO] Installing NVIDIA Container Runtime...")
    
    try:
        # Определяем дистрибутив
        try:
            with open('/etc/os-release') as f:
                os_info = f.read()
                if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                    distro = 'ubuntu'
                else:
                    distro = 'ubuntu'
        except:
            distro = 'ubuntu'
        
        if distro == 'ubuntu':
            # Устанавливаем nvidia-container-toolkit
            print("[INFO] Installing nvidia-container-toolkit...")
            subprocess.run(['sudo', 'apt-get', 'update'], check=True)
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'nvidia-container-toolkit'], check=True)
            
            # Настраиваем Docker daemon
            print("[INFO] Configuring Docker daemon...")
            subprocess.run(['sudo', 'nvidia-ctk', 'runtime', 'configure', '--runtime=docker'], check=True)
            
            # Перезапускаем Docker
            print("[INFO] Restarting Docker...")
            subprocess.run(['sudo', 'systemctl', 'restart', 'docker'], check=True)
            
            # Ждем запуска
            time.sleep(5)
            
            # Проверяем установку
            result = subprocess.run(['nvidia-container-cli', 'info'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                print("[INFO] NVIDIA Container Runtime installed successfully")
                return True
            else:
                print(f"[ERROR] NVIDIA Container Runtime installation failed: {result.stderr}")
                return False
        else:
            print(f"[ERROR] Unsupported distribution: {distro}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Failed to install NVIDIA Container Runtime: {e}")
        return False

def get_available_resources():
    """Получает информацию о доступных ресурсах системы с учетом уже запущенных контейнеров"""
    try:
        # CPU
        cpu_count = psutil.cpu_count(logical=True)
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # RAM
        memory = psutil.virtual_memory()
        total_ram_gb = memory.total / (1024**3)
        available_ram_gb = memory.available / (1024**3)
        
        # GPU (если есть)
        gpu_count = 0
        try:
            gpu_info = get_gpu_info()
            gpu_count = len(gpu_info) if gpu_info else 0
        except:
            pass
        
        # Disk
        disk_usage = psutil.disk_usage('/')
        total_disk_gb = disk_usage.total / (1024**3)
        available_disk_gb = disk_usage.free / (1024**3)
        
        # Проверяем уже запущенные контейнеры и вычитаем их ресурсы
        running_containers_resources = get_running_containers_resources()
        
        # Вычитаем ресурсы уже запущенных контейнеров
        if running_containers_resources:
            available_ram_gb = max(1, available_ram_gb - running_containers_resources.get('ram_gb', 0))
            available_disk_gb = max(10, available_disk_gb - running_containers_resources.get('disk_gb', 0))
            # GPU считаем как общее количество, так как Docker может использовать все GPU
            # CPU также считаем как общее количество, так как Docker может ограничивать по ядрам
        
        print(f"[INFO] System resources:")
        print(f"  Total CPU cores: {cpu_count}")
        print(f"  Available RAM: {available_ram_gb:.1f}GB")
        print(f"  Available disk: {available_disk_gb:.1f}GB")
        print(f"  GPU count: {gpu_count}")
        if running_containers_resources:
            print(f"  Running containers using: {running_containers_resources.get('ram_gb', 0):.1f}GB RAM, {running_containers_resources.get('disk_gb', 0):.1f}GB disk")
        
        return {
            'cpu_count': cpu_count,
            'cpu_usage_percent': cpu_percent,
            'total_ram_gb': total_ram_gb,
            'available_ram_gb': available_ram_gb,
            'gpu_count': gpu_count,
            'total_disk_gb': total_disk_gb,
            'available_disk_gb': available_disk_gb
        }
    except Exception as e:
        print(f"[ERROR] Failed to get available resources: {e}")
        return None

def install_and_import(package):
    try:
        # Сначала пробуем импортировать
        module = importlib.import_module(package)
        globals()[package] = module
        print(f"[INFO] {package} already available")
    except ImportError:
        print(f"[INFO] Installing {package}...")
        try:
            # Пробуем установить с --user флагом и игнорируем конфликты
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "--no-deps", package])
        except subprocess.CalledProcessError:
            try:
                # Если не получилось, пробуем с --force-reinstall
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "--force-reinstall", "--no-deps", package])
            except subprocess.CalledProcessError:
                # Если все еще не получилось, пробуем без --user
                subprocess.check_call([sys.executable, "-m", "pip", "install", "--force-reinstall", "--no-deps", package])
        finally:
            try:
                globals()[package] = importlib.import_module(package)
            except ImportError:
                print(f"[WARNING] Could not import {package} after installation")
                if package == "psutil":
                    print("[INFO] psutil has issues, using fallback...")
                    # Создаем заглушку для psutil
                elif package == "requests":
                    print("[ERROR] requests is required but could not be installed")
                    sys.exit(1)
                elif package == "docker":
                    print("[WARNING] docker package could not be installed, but Docker CLI should still work")
    except Exception as e:
        print(f"[WARNING] Failed to import {package}: {e}")
        if package == "psutil":
            print("[INFO] psutil has issues, using fallback...")
            globals()[package] = PsutilStub()
        elif package == "requests":
            print("[ERROR] requests is required but could not be installed")
            sys.exit(1)
        elif package == "docker":
            print("[WARNING] docker package could not be installed, but Docker CLI should still work")

# Функция для исправления конфликтов зависимостей
def fix_dependency_conflicts():
    """Исправляет конфликты зависимостей pip"""
    print("[INFO] Checking for dependency conflicts...")
    try:
        # Проверяем конфликты
        result = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True)
        if result.returncode != 0:
            print("[INFO] Found dependency conflicts, attempting to fix...")
            
            # Обновляем проблемные пакеты
            conflicts = [
                ("Jinja2", ">=3.1.2"),
                ("flask", "3.0.2"),
                ("requests", "latest"),
                ("docker", "latest")
            ]
            
            for package, version in conflicts:
                try:
                    if version == "latest":
                        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", package], 
                                     capture_output=True, check=True)
                    else:
                        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "--upgrade", f"{package}{version}"], 
                                     capture_output=True, check=True)
                    print(f"[INFO] Updated {package}")
                except:
                    pass
            
            # Очищаем кэш pip
            subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], capture_output=True)
            print("[INFO] Dependency conflicts fixed")
        else:
            print("[INFO] No dependency conflicts found")
    except Exception as e:
        print(f"[WARNING] Could not check dependencies: {e}")

# Исправляем конфликты зависимостей
fix_dependency_conflicts()

# Устанавливаем пакеты
for pkg in REQUIRED_PACKAGES:
    install_and_import(pkg)

# Импортируем после установки
import psutil
import requests

# Функция для выполнения Docker команд
def docker_cmd(cmd_args, **kwargs):
    """Выполняет Docker команду с автоматическим sudo если нужно"""
    # Проверяем, работает ли Docker без sudo
    use_sudo = False
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            use_sudo = True
    except:
        use_sudo = True
    
    if use_sudo:
        full_cmd = ['sudo', 'docker'] + cmd_args
    else:
        full_cmd = ['docker'] + cmd_args
    
    return subprocess.run(full_cmd, **kwargs)

def install_docker():
    """Устанавливает Docker на систему"""
    system = platform.system()
    
    print("[INFO] Checking Docker installation...")
    
    # Проверяем, установлен ли Docker
    try:
        subprocess.run(['docker', '--version'], check=True, capture_output=True)
        print("[INFO] Docker is already installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[INFO] Docker not found, installing...")
    
    try:
        if system == "Linux":
            # Установка Docker на Linux
            print("[INFO] Installing Docker on Linux...")
            
            # Определяем дистрибутив
            try:
                with open('/etc/os-release') as f:
                    os_info = f.read()
                    if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                        distro = 'ubuntu'
                    elif 'centos' in os_info.lower() or 'rhel' in os_info.lower() or 'fedora' in os_info.lower():
                        distro = 'centos'
                    else:
                        distro = 'ubuntu'  # По умолчанию
            except:
                distro = 'ubuntu'  # По умолчанию
            
            if distro == 'ubuntu':
                # Установка Docker на Ubuntu/Debian
                print("[INFO] Installing Docker on Ubuntu/Debian...")
                
                # Обновляем пакеты
                subprocess.run(['sudo', 'apt-get', 'update'], check=True)
                
                # Устанавливаем необходимые пакеты
                subprocess.run(['sudo', 'apt-get', 'install', '-y', 'apt-transport-https', 'ca-certificates', 'curl', 'gnupg', 'lsb-release'], check=True)
                
                # Добавляем GPG ключ Docker
                subprocess.run('curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg', shell=True, check=True)
                
                # Добавляем репозиторий Docker
                subprocess.run('echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null', shell=True, check=True)
                
                # Обновляем пакеты и устанавливаем Docker
                subprocess.run(['sudo', 'apt-get', 'update'], check=True)
                subprocess.run(['sudo', 'apt-get', 'install', '-y', 'docker-ce', 'docker-ce-cli', 'containerd.io'], check=True)
                
            elif distro == 'centos':
                # Установка Docker на CentOS/RHEL/Fedora
                print("[INFO] Installing Docker on CentOS/RHEL/Fedora...")
                
                # Устанавливаем необходимые пакеты
                subprocess.run(['sudo', 'yum', 'install', '-y', 'yum-utils'], check=True)
                
                # Добавляем репозиторий Docker
                subprocess.run(['sudo', 'yum-config-manager', '--add-repo', 'https://download.docker.com/linux/centos/docker-ce.repo'], check=True)
                
                # Устанавливаем Docker
                subprocess.run(['sudo', 'yum', 'install', '-y', 'docker-ce', 'docker-ce-cli', 'containerd.io'], check=True)
            
            # Запускаем Docker сервис
            subprocess.run(['sudo', 'systemctl', 'start', 'docker'], check=True)
            subprocess.run(['sudo', 'systemctl', 'enable', 'docker'], check=True)
            
            # Добавляем текущего пользователя в группу docker
            subprocess.run(['sudo', 'usermod', '-aG', 'docker', os.getenv('USER', 'root')], check=True)
            
            print("[INFO] Docker installed successfully on Linux")
            print("[INFO] Please restart your session or run: newgrp docker")
            return True
            
        elif system == "Darwin":
            # Установка Docker на macOS
            print("[INFO] Installing Docker Desktop on macOS...")
            print("[WARNING] Please install Docker Desktop manually from https://www.docker.com/products/docker-desktop")
            print("[INFO] After installation, restart the script")
            return False
            
        elif system == "Windows":
            # Установка Docker на Windows
            print("[INFO] Installing Docker Desktop on Windows...")
            print("[WARNING] Please install Docker Desktop manually from https://www.docker.com/products/docker-desktop")
            print("[INFO] After installation, restart the script")
            return False
            
        else:
            print(f"[ERROR] Unsupported operating system: {system}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to install Docker: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during Docker installation: {e}")
        return False

def check_and_install_docker():
    """Проверяет и устанавливает Docker если необходимо"""
    try:
        # Проверяем, работает ли Docker
        docker_cmd(['ps'], check=True, capture_output=True)
        print("[INFO] Docker is working correctly")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[INFO] Docker not working, attempting to fix...")
        
        # Проверяем, установлен ли Docker
        try:
            subprocess.run(['docker', '--version'], check=True, capture_output=True)
            print("[INFO] Docker is installed but not working")
            
            # Используем улучшенную функцию для исправления прав
            if fix_docker_permissions():
                print("[INFO] Docker permissions fixed successfully")
                return True
            else:
                print("[WARNING] Could not fix Docker permissions")
            
            # Если ничего не помогло, пробуем установить заново
            print("[INFO] Attempting Docker reinstallation...")
            if install_docker():
                print("[INFO] Docker installation completed. Please restart the script to use Docker.")
                print("[INFO] Or run: newgrp docker")
                return False
            else:
                print("[ERROR] Docker installation failed")
                return False
                
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[INFO] Docker not found, installing...")
            if install_docker():
                print("[INFO] Docker installation completed. Please restart the script to use Docker.")
                print("[INFO] Or run: newgrp docker")
                return False
            else:
                print("[ERROR] Docker installation failed")
                return False

def detect_gpu_vendor():
    """Определяет производителя GPU"""
    system = platform.system()
    
    try:
        if system == "Linux":
            # Проверяем NVIDIA
            try:
                subprocess.run(['nvidia-smi'], check=True, capture_output=True)
                return "nvidia"
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
            
            # Проверяем AMD
            try:
                subprocess.run(['rocm-smi'], check=True, capture_output=True)
                return "amd"
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
            
            # Проверяем Intel
            try:
                with open('/sys/class/drm/card0/device/vendor') as f:
                    vendor_id = f.read().strip()
                    if vendor_id == '0x8086':  # Intel
                        return "intel"
            except:
                pass
            
            # Проверяем через lspci
            try:
                lspci_output = subprocess.check_output(['lspci', '-nn']).decode()
                if 'nvidia' in lspci_output.lower():
                    return "nvidia"
                elif 'amd' in lspci_output.lower() or 'radeon' in lspci_output.lower():
                    return "amd"
                elif 'intel' in lspci_output.lower():
                    return "intel"
            except:
                pass
                
        elif system == "Darwin":
            # macOS обычно имеет встроенную поддержку GPU
            return "apple"
            
        elif system == "Windows":
            # На Windows драйверы обычно уже установлены
            return "windows"
            
    except Exception as e:
        print(f"[WARNING] GPU detection error: {e}")
    
    return "unknown"

def install_nvidia_drivers():
    """Устанавливает драйверы NVIDIA"""
    print("[INFO] Installing NVIDIA drivers...")
    
    try:
        # Определяем дистрибутив
        try:
            with open('/etc/os-release') as f:
                os_info = f.read()
                if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                    distro = 'ubuntu'
                elif 'centos' in os_info.lower() or 'rhel' in os_info.lower() or 'fedora' in os_info.lower():
                    distro = 'centos'
                else:
                    distro = 'ubuntu'
        except:
            distro = 'ubuntu'
        
        if distro == 'ubuntu':
            # Установка на Ubuntu/Debian
            print("[INFO] Installing NVIDIA drivers on Ubuntu/Debian...")
            
            # Обновляем пакеты
            subprocess.run(['sudo', 'apt-get', 'update'], check=True)
            
            # Устанавливаем необходимые пакеты
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'build-essential', 'dkms'], check=True)
            
            # Добавляем репозиторий NVIDIA
            subprocess.run(['sudo', 'add-apt-repository', 'ppa:graphics-drivers/ppa', '-y'], check=True)
            subprocess.run(['sudo', 'apt-get', 'update'], check=True)
            
            # Устанавливаем последние драйверы NVIDIA
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'nvidia-driver-535'], check=True)
            
            # Устанавливаем CUDA toolkit
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'nvidia-cuda-toolkit'], check=True)
            
        elif distro == 'centos':
            # Установка на CentOS/RHEL/Fedora
            print("[INFO] Installing NVIDIA drivers on CentOS/RHEL/Fedora...")
            
            # Устанавливаем EPEL репозиторий
            subprocess.run(['sudo', 'yum', 'install', '-y', 'epel-release'], check=True)
            
            # Устанавливаем необходимые пакеты
            subprocess.run(['sudo', 'yum', 'install', '-y', 'gcc', 'kernel-devel', 'dkms'], check=True)
            
            # Устанавливаем драйверы NVIDIA
            subprocess.run(['sudo', 'yum', 'install', '-y', 'nvidia-driver'], check=True)
            
            # Устанавливаем CUDA
            subprocess.run(['sudo', 'yum', 'install', '-y', 'cuda'], check=True)
        
        print("[INFO] NVIDIA drivers installed successfully")
        print("[INFO] Please reboot the system to activate drivers")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to install NVIDIA drivers: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during NVIDIA installation: {e}")
        return False

def install_amd_drivers():
    """Устанавливает драйверы AMD"""
    print("[INFO] Installing AMD drivers...")
    
    try:
        # Определяем дистрибутив
        try:
            with open('/etc/os-release') as f:
                os_info = f.read()
                if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                    distro = 'ubuntu'
                else:
                    distro = 'ubuntu'
        except:
            distro = 'ubuntu'
        
        if distro == 'ubuntu':
            # Установка на Ubuntu/Debian
            print("[INFO] Installing AMD drivers on Ubuntu/Debian...")
            
            # Обновляем пакеты
            subprocess.run(['sudo', 'apt-get', 'update'], check=True)
            
            # Устанавливаем необходимые пакеты
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'build-essential', 'dkms'], check=True)
            
            # Устанавливаем ROCm (AMD GPU Compute Platform)
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'rocm-dkms'], check=True)
            
            # Добавляем пользователя в группу video
            subprocess.run(['sudo', 'usermod', '-aG', 'video', os.getenv('USER', 'root')], check=True)
            
            # Устанавливаем OpenCL
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'rocm-opencl-dev'], check=True)
        
        print("[INFO] AMD drivers installed successfully")
        print("[INFO] Please reboot the system to activate drivers")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to install AMD drivers: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during AMD installation: {e}")
        return False

def install_intel_drivers():
    """Устанавливает драйверы Intel"""
    print("[INFO] Installing Intel drivers...")
    
    try:
        # Определяем дистрибутив
        try:
            with open('/etc/os-release') as f:
                os_info = f.read()
                if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                    distro = 'ubuntu'
                else:
                    distro = 'ubuntu'
        except:
            distro = 'ubuntu'
        
        if distro == 'ubuntu':
            # Установка на Ubuntu/Debian
            print("[INFO] Installing Intel drivers on Ubuntu/Debian...")
            
            # Обновляем пакеты
            subprocess.run(['sudo', 'apt-get', 'update'], check=True)
            
            # Устанавливаем Intel Media Driver
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'intel-media-va-driver-non-free'], check=True)
            
            # Устанавливаем Intel OpenCL
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'intel-opencl-icd'], check=True)
            
            # Устанавливаем Intel Compute Runtime
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'intel-compute-runtime'], check=True)
        
        print("[INFO] Intel drivers installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to install Intel drivers: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during Intel installation: {e}")
        return False

def check_and_install_gpu_drivers():
    """Проверяет и устанавливает драйверы GPU если необходимо"""
    system = platform.system()
    
    if system not in ["Linux"]:
        print(f"[INFO] GPU driver installation not needed on {system}")
        return True
    
    print("[INFO] Checking GPU drivers...")
    
    # Определяем производителя GPU
    gpu_vendor = detect_gpu_vendor()
    print(f"[INFO] Detected GPU vendor: {gpu_vendor}")
    
    # Устанавливаем общие инструменты для работы с GPU
    install_common_gpu_tools()
    
    if gpu_vendor == "nvidia":
        # Проверяем, установлены ли драйверы NVIDIA
        try:
            subprocess.run(['nvidia-smi'], check=True, capture_output=True)
            print("[INFO] NVIDIA drivers are already installed and working")
            # Устанавливаем дополнительные инструменты NVIDIA
            install_nvidia_tools()
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[INFO] NVIDIA drivers not found, installing...")
            if install_nvidia_drivers():
                install_nvidia_tools()
                return True
            return False
            
    elif gpu_vendor == "amd":
        # Проверяем, установлены ли драйверы AMD
        try:
            subprocess.run(['rocm-smi'], check=True, capture_output=True)
            print("[INFO] AMD drivers are already installed and working")
            # Устанавливаем дополнительные инструменты AMD
            install_amd_tools()
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[INFO] AMD drivers not found, installing...")
            if install_amd_drivers():
                install_amd_tools()
                return True
            return False
            
    elif gpu_vendor == "intel":
        # Проверяем, установлены ли драйверы Intel
        try:
            subprocess.run(['clinfo'], check=True, capture_output=True)
            print("[INFO] Intel drivers are already installed and working")
            # Устанавливаем дополнительные инструменты Intel
            install_intel_tools()
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[INFO] Intel drivers not found, installing...")
            if install_intel_drivers():
                install_intel_tools()
                return True
            return False
            
    elif gpu_vendor in ["apple", "windows"]:
        print(f"[INFO] GPU drivers handled by {gpu_vendor} system")
        return True
        
    else:
        print("[WARNING] Unknown GPU vendor, skipping driver installation")
        return True

def install_nvidia_tools():
    """Устанавливает дополнительные инструменты NVIDIA"""
    print("[INFO] Installing NVIDIA tools...")
    
    try:
        # Определяем дистрибутив
        try:
            with open('/etc/os-release') as f:
                os_info = f.read()
                if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                    distro = 'ubuntu'
                else:
                    distro = 'ubuntu'
        except:
            distro = 'ubuntu'
        
        if distro == 'ubuntu':
            # Устанавливаем NVIDIA Container Toolkit для Docker
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'nvidia-container-toolkit'], check=True)
            subprocess.run(['sudo', 'systemctl', 'restart', 'docker'], check=True)
            
            # Устанавливаем NVIDIA Docker runtime
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'nvidia-docker2'], check=True)
            
            # Устанавливаем PyTorch CUDA
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'torch', 'torchvision', 'torchaudio', '--index-url', 'https://download.pytorch.org/whl/cu118'], check=True)
            
            # Устанавливаем TensorFlow (GPU поддержка включена по умолчанию в новых версиях)
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'tensorflow'], check=True)
            
        print("[INFO] NVIDIA tools installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[WARNING] Failed to install NVIDIA tools: {e}")
        return False

def install_amd_tools():
    """Устанавливает дополнительные инструменты AMD"""
    print("[INFO] Installing AMD tools...")
    
    try:
        # Определяем дистрибутив
        try:
            with open('/etc/os-release') as f:
                os_info = f.read()
                if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                    distro = 'ubuntu'
                else:
                    distro = 'ubuntu'
        except:
            distro = 'ubuntu'
        
        if distro == 'ubuntu':
            # Устанавливаем ROCm Docker
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'rocm-docker'], check=True)
            
            # Устанавливаем PyTorch ROCm
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'torch', 'torchvision', 'torchaudio', '--index-url', 'https://download.pytorch.org/whl/rocm5.4.2'], check=True)
            
        print("[INFO] AMD tools installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[WARNING] Failed to install AMD tools: {e}")
        return False

def install_intel_tools():
    """Устанавливает дополнительные инструменты Intel"""
    print("[INFO] Installing Intel tools...")
    
    try:
        # Определяем дистрибутив
        try:
            with open('/etc/os-release') as f:
                os_info = f.read()
                if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                    distro = 'ubuntu'
                else:
                    distro = 'ubuntu'
        except:
            distro = 'ubuntu'
        
        if distro == 'ubuntu':
            # Устанавливаем Intel Extension for PyTorch
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'intel-extension-for-pytorch'], check=True)
            
            # Устанавливаем Intel Neural Compute Stick tools
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'intel-openvino-dev'], check=True)
            
        print("[INFO] Intel tools installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[WARNING] Failed to install Intel tools: {e}")
        return False

def install_common_gpu_tools():
    """Устанавливает общие инструменты для работы с GPU"""
    print("[INFO] Installing common GPU tools...")
    
    try:
        # Определяем дистрибутив
        try:
            with open('/etc/os-release') as f:
                os_info = f.read()
                if 'ubuntu' in os_info.lower() or 'debian' in os_info.lower():
                    distro = 'ubuntu'
                else:
                    distro = 'ubuntu'
        except:
            distro = 'ubuntu'
        
        if distro == 'ubuntu':
            # Устанавливаем общие инструменты для работы с GPU
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'clinfo', 'ocl-icd-opencl-dev'], check=True)
            
            # Устанавливаем Python библиотеки для работы с GPU
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'numpy', 'scipy', 'matplotlib'], check=True)
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'opencv-python', 'pillow'], check=True)
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'scikit-learn', 'pandas'], check=True)
            
            # Устанавливаем инструменты мониторинга GPU
            subprocess.run(['sudo', 'apt-get', 'install', '-y', 'htop', 'iotop', 'nethogs'], check=True)
            
        print("[INFO] Common GPU tools installed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"[WARNING] Failed to install common GPU tools: {e}")
        return False

# Универсальная функция для CPU
def get_cpu_info():
    cpu_info = []
    system = platform.system()
    try:
        if system == "Darwin":
            # Получаем информацию о CPU для macOS
            try:
                model = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string']).decode().strip()
                cores = psutil.cpu_count(logical=False)
                threads = psutil.cpu_count(logical=True)
                
                # Получаем частоту через sysctl
                freq = None
                try:
                    freq_mhz = subprocess.check_output(['sysctl', '-n', 'hw.cpufrequency_max']).decode().strip()
                    if freq_mhz.isdigit():
                        freq = float(freq_mhz) / 1000000000  # Конвертируем в GHz
                except:
                    pass
                
                cpu_info.append({
                    "model": model,
                    "cores": cores,
                    "threads": threads,
                    "freq_ghz": round(freq, 2) if freq else None,
                    "count": 1
                })
            except Exception as e:
                print(f"[WARNING] macOS CPU detection failed: {e}")
                # Fallback
                cpu_info.append({
                    "model": platform.processor(),
                    "cores": psutil.cpu_count(logical=False),
                    "threads": psutil.cpu_count(logical=True),
                    "freq_ghz": None,
                    "count": 1
                })
        elif system == "Windows":
            # Получаем информацию о всех CPU через wmic
            try:
                wmic_output = subprocess.check_output(['wmic', 'cpu', 'get', 'Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed'], shell=True).decode(errors='ignore')
                lines = wmic_output.strip().split('\n')[1:]  # Пропускаем заголовок
                
                cpu_groups = {}
                for line in lines:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 4:
                            # Собираем название модели (может содержать пробелы)
                            model_parts = parts[:-3]  # Все части кроме последних 3
                            model = ' '.join(model_parts)
                            cores = int(parts[-3]) if parts[-3].isdigit() else 1
                            threads = int(parts[-2]) if parts[-2].isdigit() else 1
                            freq_mhz = int(parts[-1]) if parts[-1].isdigit() else None
                            freq_ghz = freq_mhz / 1000 if freq_mhz else None
                            
                            # Группируем по модели
                            if model in cpu_groups:
                                cpu_groups[model]['count'] += 1
                                cpu_groups[model]['cores'] += cores
                                cpu_groups[model]['threads'] += threads
                                if freq_ghz and (cpu_groups[model]['freq_ghz'] is None or freq_ghz > cpu_groups[model]['freq_ghz']):
                                    cpu_groups[model]['freq_ghz'] = freq_ghz
                            else:
                                cpu_groups[model] = {
                                    'model': model,
                                    'cores': cores,
                                    'threads': threads,
                                    'freq_ghz': freq_ghz,
                                    'count': 1
                                }
                
                # Добавляем сгруппированные CPU
                for cpu_data in cpu_groups.values():
                    cpu_info.append(cpu_data)
                    
            except Exception as e:
                print(f"[WARNING] Windows CPU detection failed: {e}")
                # Fallback к базовому методу
                model = subprocess.check_output(['wmic', 'cpu', 'get', 'Name'], shell=True).decode(errors='ignore').split('\n')[1].strip()
                cores = psutil.cpu_count(logical=False)
                threads = psutil.cpu_count(logical=True)
                freq = psutil.cpu_freq().max / 1000 if psutil.cpu_freq() else None
                cpu_info.append({
                    "model": model,
                    "cores": cores,
                    "threads": threads,
                    "freq_ghz": round(freq, 2) if freq else None,
                    "count": 1
                })
        elif system == "Linux":
            # Улучшенное получение информации о CPU для Linux с поддержкой множественных CPU
            try:
                # Получаем информацию о количестве сокетов (физических CPU)
                try:
                    lscpu_output = subprocess.check_output(['lscpu']).decode()
                    print(f"[DEBUG] lscpu output: {lscpu_output}")
                    
                    sockets_match = re.search(r'Socket\(s\):\s+(\d+)', lscpu_output)
                    sockets = int(sockets_match.group(1)) if sockets_match else 1
                    print(f"[DEBUG] Detected sockets from lscpu: {sockets}")
                    
                    # Альтернативный способ определения сокетов через /proc/cpuinfo
                    if sockets == 1:
                        try:
                            with open('/proc/cpuinfo') as f:
                                cpuinfo_lines = f.read()
                                # Ищем физический ID процессоров
                                physical_ids = set()
                                for line in cpuinfo_lines.split('\n'):
                                    if line.startswith('physical id'):
                                        physical_id = line.split(':')[1].strip()
                                        physical_ids.add(physical_id)
                                if len(physical_ids) > 1:
                                    sockets = len(physical_ids)
                                    print(f"[DEBUG] Detected sockets from /proc/cpuinfo: {sockets}")
                        except Exception as e:
                            print(f"[DEBUG] Failed to detect sockets from /proc/cpuinfo: {e}")
                    
                    # Еще один способ через dmidecode
                    if sockets == 1:
                        try:
                            dmidecode_output = subprocess.check_output(['dmidecode', '-t', 'processor'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                            socket_count = dmidecode_output.count('Socket Designation:')
                            if socket_count > 1:
                                sockets = socket_count
                                print(f"[DEBUG] Detected sockets from dmidecode: {sockets}")
                        except Exception as e:
                            print(f"[DEBUG] Failed to detect sockets from dmidecode: {e}")
                    
                    # Способ через /sys/devices/system/cpu/
                    if sockets == 1:
                        try:
                            cpu_dirs = [d for d in os.listdir('/sys/devices/system/cpu/') if d.startswith('cpu') and d[3:].isdigit()]
                            if cpu_dirs:
                                # Проверяем топологию CPU
                                topology_file = '/sys/devices/system/cpu/cpu0/topology/physical_package_id'
                                if os.path.exists(topology_file):
                                    with open(topology_file, 'r') as f:
                                        package_ids = set()
                                        for cpu_dir in cpu_dirs:
                                            try:
                                                with open(f'/sys/devices/system/cpu/{cpu_dir}/topology/physical_package_id', 'r') as f:
                                                    package_id = f.read().strip()
                                                    package_ids.add(package_id)
                                            except:
                                                continue
                                        if len(package_ids) > 1:
                                            sockets = len(package_ids)
                                            print(f"[DEBUG] Detected sockets from /sys/devices/system/cpu/: {sockets}")
                        except Exception as e:
                            print(f"[DEBUG] Failed to detect sockets from /sys/devices/system/cpu/: {e}")
                    
                    # Способ через NUMA узлы
                    if sockets == 1:
                        try:
                            numa_dirs = [d for d in os.listdir('/sys/devices/system/node/') if d.startswith('node') and d[4:].isdigit()]
                            if len(numa_dirs) > 1:
                                sockets = len(numa_dirs)
                                print(f"[DEBUG] Detected sockets from NUMA nodes: {sockets}")
                        except Exception as e:
                            print(f"[DEBUG] Failed to detect sockets from NUMA nodes: {e}")
                    
                    # Способ через numactl
                    if sockets == 1:
                        try:
                            numactl_output = subprocess.check_output(['numactl', '--hardware'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                            numa_nodes = numactl_output.count('node ')
                            if numa_nodes > 1:
                                sockets = numa_nodes
                                print(f"[DEBUG] Detected sockets from numactl: {sockets}")
                        except Exception as e:
                            print(f"[DEBUG] Failed to detect sockets from numactl: {e}")
                    
                    # Получаем модель процессора
                    model_match = re.search(r'Model name:\s+(.+)', lscpu_output)
                    if model_match:
                        model = model_match.group(1).strip()
                    else:
                        # Альтернативный способ через /proc/cpuinfo
                        with open('/proc/cpuinfo') as f:
                            cpuinfo_lines = f.read()
                            model_match = re.search(r'model name\s+:\s+(.+)', cpuinfo_lines)
                            model = model_match.group(1).strip() if model_match else platform.processor()
                    
                    # Получаем общее количество ядер и потоков
                    total_cores = psutil.cpu_count(logical=False)
                    total_threads = psutil.cpu_count(logical=True)
                    print(f"[DEBUG] Total cores: {total_cores}, Total threads: {total_threads}")
                    
                    # Вычисляем количество ядер и потоков на один сокет
                    cores_per_socket = total_cores // sockets
                    threads_per_socket = total_threads // sockets
                    print(f"[DEBUG] Cores per socket: {cores_per_socket}, Threads per socket: {threads_per_socket}")
                    
                    # Проверяем корректность вычислений
                    if cores_per_socket * sockets != total_cores:
                        print(f"[WARNING] Socket calculation mismatch: {cores_per_socket} * {sockets} != {total_cores}")
                        # Используем общие значения, если вычисления некорректны
                        cores_per_socket = total_cores
                        threads_per_socket = total_threads
                        sockets = 1
                    
                    # Получаем частоту через lscpu
                    freq = None
                    freq_match = re.search(r'CPU max MHz:\s+(\d+)', lscpu_output)
                    if freq_match:
                        freq = float(freq_match.group(1)) / 1000  # Конвертируем в GHz
                    else:
                        # Альтернативный способ через psutil
                        cpu_freq = psutil.cpu_freq()
                        freq = cpu_freq.max / 1000 if cpu_freq else None
                    
                    # Добавляем информацию о CPU
                    cpu_info.append({
                        "model": model,
                        "cores": cores_per_socket,
                        "threads": threads_per_socket,
                        "freq_ghz": round(freq, 2) if freq else None,
                        "count": sockets
                    })
                    
                except Exception as e:
                    print(f"[WARNING] lscpu failed, using fallback: {e}")
                    # Fallback к базовому методу
                    with open('/proc/cpuinfo') as f:
                        lines = f.read()
                        
                        # Ищем модель процессора
                        model_match = re.search(r'model name\s+:\s+(.+)', lines)
                        if model_match:
                            model = model_match.group(1).strip()
                        else:
                            model = platform.processor()
                        
                        # Получаем количество ядер и потоков
                        cores = psutil.cpu_count(logical=False)
                        threads = psutil.cpu_count(logical=True)
                        
                        # Получаем частоту через psutil
                        freq = None
                        try:
                            cpu_freq = psutil.cpu_freq()
                            freq = cpu_freq.max / 1000 if cpu_freq else None
                        except:
                            pass
                        
                        cpu_info.append({
                            "model": model,
                            "cores": cores,
                            "threads": threads,
                            "freq_ghz": round(freq, 2) if freq else None,
                            "count": 1
                        })
            except Exception as e:
                print(f"[WARNING] CPU info error: {e}")
                # Fallback к базовой информации
                cpu_info.append({
                    "model": platform.processor(),
                    "cores": psutil.cpu_count(logical=False),
                    "threads": psutil.cpu_count(logical=True),
                    "freq_ghz": None,
                    "count": 1
                })
        else:
            # Для других систем (не Linux, не Windows, не Darwin)
            model = platform.processor()
            cores = psutil.cpu_count(logical=False)
            threads = psutil.cpu_count(logical=True)
            freq = psutil.cpu_freq().max / 1000 if psutil.cpu_freq() else None
            
            cpu_info.append({
                "model": model,
                "cores": cores,
                "threads": threads,
                "freq_ghz": round(freq, 2) if freq else None,
                "count": 1
            })
    except Exception as e:
        print(f"[ERROR] CPU info failed: {e}")
        # Минимальная информация в случае ошибки
        if not cpu_info:  # Добавляем только если список пустой
            cpu_info.append({
                "model": "Unknown CPU",
                "cores": psutil.cpu_count(logical=False) or 1,
                "threads": psutil.cpu_count(logical=True) or 1,
                "freq_ghz": None,
                "count": 1
            })
    return cpu_info

# Универсальная функция для RAM
def get_ram_info():
    total_ram_gb = round(psutil.virtual_memory().total / (1024 ** 3))
    ram_type = "Unknown"
    system = platform.system()
    try:
        if system == "Darwin":
            ram_type_out = subprocess.check_output(["system_profiler", "SPMemoryDataType"]).decode()
            match = re.search(r'Type: (\w+)', ram_type_out)
            if match:
                ram_type = match.group(1)
        elif system == "Windows":
            ram_type_out = subprocess.check_output(['wmic', 'memorychip', 'get', 'MemoryType'], shell=True).decode(errors='ignore')
            # https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-physicalmemory
            # 24 = DDR3, 26 = DDR4, etc.
            if '24' in ram_type_out:
                ram_type = 'DDR3'
            elif '26' in ram_type_out:
                ram_type = 'DDR4'
        elif system == "Linux":
            # Улучшенное определение типа RAM для Linux
            try:
                # Попробуем через dmidecode (требует sudo)
                try:
                    ram_type_out = subprocess.check_output(['sudo', 'dmidecode', '-t', 'memory'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                    match = re.search(r'Type:\s+(DDR\w*)', ram_type_out)
                    if match:
                        ram_type = match.group(1)
                except:
                    # Альтернативный способ через /proc/meminfo и lshw
                    try:
                        lshw_output = subprocess.check_output(['lshw', '-class', 'memory'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                        match = re.search(r'DDR(\w*)', lshw_output)
                        if match:
                            ram_type = f"DDR{match.group(1)}"
                    except:
                        # Попробуем через sysfs
                        try:
                            for i in range(10):  # Проверяем несколько слотов памяти
                                try:
                                    with open(f'/sys/devices/system/memory/memory{i}/phys_index', 'r') as f:
                                        pass
                                    # Если файл существует, попробуем получить информацию о типе
                                    try:
                                        with open(f'/sys/devices/system/memory/memory{i}/type', 'r') as f:
                                            mem_type = f.read().strip()
                                            if 'DDR' in mem_type:
                                                ram_type = mem_type
                                                break
                                    except:
                                        continue
                                except:
                                    break
                        except:
                            pass
            except Exception as e:
                print(f"[WARNING] RAM type detection error: {e}")
    except Exception as e:
        print(f"[ERROR] RAM info failed: {e}")
    return total_ram_gb, ram_type


# Универсальная функция для GPU
def get_gpu_info():
    gpus = []
    system = platform.system()
    print(f"[DEBUG] Detected system: {system}")
    
    try:
        if system == "Darwin":
            sp = subprocess.check_output(['system_profiler', 'SPDisplaysDataType']).decode()
            for block in sp.split('\n\n'):
                model = re.search(r'Chipset Model: (.+)', block)
                vram = re.search(r'VRAM.*: (\d+)\s*MB', block)
                vendor = re.search(r'Vendor: (.+)', block)
                metal = re.search(r'Metal Family: (.+)', block)
                if model:
                    gpus.append({
                        "model": model.group(1),
                        "vram_gb": int(vram.group(1)) // 1024 if vram else 0,  # Backend требует обязательное поле
                        "max_cuda_version": None,
                        "tflops": None,
                        "bandwidth_gbps": None,
                        "vendor": vendor.group(1) if vendor else None,
                        "metal_family": metal.group(1) if metal else None,
                        "count": 1
                    })
        elif system == "Windows":
            out = subprocess.check_output(['wmic', 'path', 'win32_VideoController', 'get', 'Name,AdapterRAM,PNPDeviceID,DriverVersion'], shell=True).decode(errors='ignore')
            for line in out.split('\n')[1:]:
                if line.strip():
                    parts = line.split()
                    model = ' '.join(parts[:-3]) if len(parts) > 3 else parts[0]
                    vram = int(parts[-3]) if parts[-3].isdigit() else None
                    driver = parts[-1] if len(parts) > 1 else None
                    gpus.append({
                        "model": model,
                        "vram_gb": vram // (1024 ** 3) if vram else 0,  # Backend требует обязательное поле
                        "max_cuda_version": None,
                        "tflops": None,
                        "bandwidth_gbps": None,
                        "driver_version": driver,
                        "count": 1
                    })
        elif system == "Linux":
            # Улучшенное определение GPU для Linux с поддержкой множественных GPU
            print("[DEBUG] Detecting Linux GPUs...")
            try:
                # Сначала попробуем nvidia-smi для NVIDIA GPU
                print("[DEBUG] Trying nvidia-smi -L...")
                nvidia_output = subprocess.check_output(['nvidia-smi', '-L'], stderr=subprocess.DEVNULL, timeout=10).decode(errors='ignore')
                for line in nvidia_output.strip().split('\n'):
                    if line:
                        # Парсим строку вида "GPU 0: NVIDIA GeForce RTX 3080 (UUID: ...)"
                        match = re.search(r'GPU (\d+): (.+?) \(UUID:', line)
                        if match:
                            gpu_index = int(match.group(1))
                            model = match.group(2).strip()
                            
                            # Получаем дополнительную информацию для КОНКРЕТНОЙ GPU
                            vram_gb = None
                            cuda_version = None
                            cuda_cores = None
                            tflops = None
                            bandwidth_gbps = None
                            try:
                                print(f"[DEBUG] Getting detailed info for GPU {gpu_index}...")
                                # Получаем информацию для конкретной GPU по индексу
                                nvidia_detailed = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.total,driver_version', '--format=csv,noheader', '-i', str(gpu_index)], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                if nvidia_detailed.strip():
                                    parts = nvidia_detailed.strip().split(',')
                                    if len(parts) >= 2:
                                        vram_str = parts[0].strip()
                                        driver_version = parts[1].strip()
                                        # Парсим VRAM (например, "8192 MiB" или "24 GiB")
                                        vram_match = re.search(r'(\d+)\s*(MiB|GiB)', vram_str)
                                        if vram_match:
                                            vram_size = int(vram_match.group(1))
                                            vram_unit = vram_match.group(2)
                                            # Конвертируем в ГБ
                                            if vram_unit == 'MiB':
                                                vram_gb = vram_size // 1024
                                            elif vram_unit == 'GiB':
                                                vram_gb = vram_size
                                            else:
                                                vram_gb = vram_size // 1024  # По умолчанию считаем МБ
                                        # Парсим CUDA версию из driver version
                                        cuda_match = re.search(r'CUDA Version: (\d+\.\d+)', driver_version)
                                        if cuda_match:
                                            cuda_version = cuda_match.group(1)
                                        else:
                                            # Если не нашли в driver version, попробуем получить через nvidia-smi
                                            try:
                                                cuda_output = subprocess.check_output(['nvidia-smi'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                                cuda_match = re.search(r'CUDA Version:\s+(\d+\.\d+)', cuda_output)
                                                if cuda_match:
                                                    cuda_version = cuda_match.group(1)
                                            except:
                                                pass
                                        # Получаем количество CUDA ядер через nvidia-smi для конкретной GPU
                                        try:
                                             # Попробуем получить количество CUDA ядер через альтернативные методы
                                             # Метод 1: Попробуем получить через nvidia-smi с другими параметрами
                                             try:
                                                 cuda_cores_output = subprocess.check_output(['nvidia-smi', '--query-gpu=compute_cap,sm_count', '--format=csv,noheader'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                             except:
                                                 # Метод 2: Попробуем получить через nvidia-smi без специфичных параметров
                                                 cuda_cores_output = subprocess.check_output(['nvidia-smi', '--query-gpu=name,compute_cap', '--format=csv,noheader'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                             if cuda_cores_output.strip():
                                                 # Получаем информацию для всех GPU и находим нужную
                                                 gpu_lines = cuda_cores_output.strip().split('\n')
                                                 if gpu_index < len(gpu_lines):
                                                     parts = gpu_lines[gpu_index].strip().split(',')
                                                     if len(parts) >= 2:
                                                         # Проверяем, какой формат получили
                                                         if 'RTX' in parts[0] or 'GeForce' in parts[0]:
                                                             # Формат: name,compute_cap
                                                             compute_cap = parts[1].strip()
                                                             # Оценка SM count на основе модели и compute capability
                                                             if '9.0' in compute_cap:  # Blackwell (RTX 5090)
                                                                 sm_count = 128  # Примерное количество SM для RTX 5090
                                                             elif '8.9' in compute_cap:  # Ada Lovelace
                                                                 sm_count = 128  # Примерное количество SM для RTX 4090
                                                             elif '8.6' in compute_cap:  # Ampere
                                                                 sm_count = 82   # Примерное количество SM для RTX 3090
                                                             else:
                                                                 sm_count = 68   # Базовое количество SM
                                                         else:
                                                             # Формат: compute_cap,sm_count
                                                             compute_cap = parts[0].strip()
                                                             sm_count = int(parts[1].strip())
                                                         
                                                         # Определяем количество CUDA ядер на основе SM count и compute capability
                                                         if '9.0' in compute_cap:  # Blackwell (RTX 5090)
                                                             cuda_cores = sm_count * 144  # 144 CUDA cores per SM
                                                         elif '8.9' in compute_cap:  # Ada Lovelace
                                                             cuda_cores = sm_count * 128  # 128 CUDA cores per SM
                                                         elif '8.6' in compute_cap:  # Ampere
                                                             cuda_cores = sm_count * 128  # 128 CUDA cores per SM
                                                         elif '7.5' in compute_cap:  # Turing
                                                             cuda_cores = sm_count * 64   # 64 CUDA cores per SM
                                                         elif '6.1' in compute_cap:  # Pascal
                                                             cuda_cores = sm_count * 128  # 128 CUDA cores per SM
                                                         else:
                                                             # Fallback: используем примерную оценку на основе VRAM
                                                             if vram_gb:
                                                                 # Примерная оценка на основе VRAM (более универсальная)
                                                                 cuda_cores = vram_gb * 600  # Базовая оценка
                                                             
                                                             # Попробуем получить через sysfs для Linux
                                                             if not cuda_cores:
                                                                 try:
                                                                     for i in range(10):
                                                                         try:
                                                                             with open(f'/sys/class/drm/card{i}/device/gpu_busy_percent', 'r') as f:
                                                                                 # Если файл существует, это GPU
                                                                                 # Попробуем получить информацию о SM count
                                                                                 if os.path.exists(f'/sys/class/drm/card{i}/device/sm_count'):
                                                                                     with open(f'/sys/class/drm/card{i}/device/sm_count', 'r') as f:
                                                                                         sm_count = int(f.read().strip())
                                                                                         # Примерная оценка: SM count * 128
                                                                                         cuda_cores = sm_count * 128
                                                                                         break
                                                                         except:
                                                                             continue
                                                                 except:
                                                                     pass
                                        except subprocess.TimeoutExpired:
                                            print(f"[WARNING] Timeout getting CUDA cores for GPU {gpu_index}")
                                        except Exception as e:
                                            print(f"[WARNING] Error getting CUDA cores for GPU {gpu_index}: {e}")
                                        
                                        # Получаем информацию о памяти и производительности для конкретной GPU
                                        try:
                                            # Попробуем получить memory info через альтернативные методы
                                            try:
                                                # Метод 1: Попробуем получить через nvidia-smi с другими параметрами
                                                memory_info = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.clock,memory.bus_width', '--format=csv,noheader'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                            except:
                                                # Метод 2: Попробуем получить через nvidia-smi без специфичных параметров
                                                memory_info = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                            if memory_info.strip():
                                                # Получаем информацию для всех GPU и находим нужную
                                                gpu_lines = memory_info.strip().split('\n')
                                                if gpu_index < len(gpu_lines):
                                                    parts = gpu_lines[gpu_index].strip().split(',')
                                                    if len(parts) >= 2:
                                                        # Проверяем, какой формат получили
                                                        if 'RTX' in parts[0] or 'GeForce' in parts[0]:
                                                            # Формат: name,memory.total - используем fallback для bandwidth
                                                            pass
                                                        else:
                                                            # Формат: memory.clock,memory.bus_width
                                                            try:
                                                                memory_clock_mhz = float(parts[0].strip())
                                                                bus_width = int(parts[1].strip())
                                                                # Рассчитываем bandwidth: (memory_clock * 2 * bus_width) / 8
                                                                bandwidth_gbps = (memory_clock_mhz * 2 * bus_width) / 8000
                                                            except:
                                                                pass
                                        except subprocess.TimeoutExpired:
                                            print(f"[WARNING] Timeout getting memory info for GPU {gpu_index}")
                                        except Exception as e:
                                            print(f"[WARNING] Error getting memory info for GPU {gpu_index}: {e}")
                                        
                                        # Fallback для bandwidth если не удалось получить memory info
                                        if not bandwidth_gbps:
                                            # Попробуем получить через sysfs
                                            try:
                                                for i in range(10):
                                                    try:
                                                        if os.path.exists(f'/sys/class/drm/card{i}/device/gpu_busy_percent'):
                                                            # Попробуем получить memory clock через sysfs
                                                            if os.path.exists(f'/sys/class/drm/card{i}/device/pp_dpm_mclk'):
                                                                with open(f'/sys/class/drm/card{i}/device/pp_dpm_mclk', 'r') as f:
                                                                    mclk_info = f.read()
                                                                    mclk_match = re.search(r'(\d+):\s*(\d+)Mhz', mclk_info)
                                                                    if mclk_match:
                                                                        memory_clock_mhz = int(mclk_match.group(2))
                                                                        # Примерная оценка bandwidth: memory_clock * 2 / 1000
                                                                        bandwidth_gbps = memory_clock_mhz * 2 / 1000
                                                                        break
                                                    except:
                                                        continue
                                            except:
                                                pass
                                            
                                            # Если все еще нет bandwidth, используем примерную оценку на основе VRAM
                                            if not bandwidth_gbps and vram_gb:
                                                # Примерная оценка: VRAM * 30 GB/s per GB
                                                bandwidth_gbps = vram_gb * 30
                                        
                                        # Получаем TFLOPS через nvidia-smi для конкретной GPU
                                        try:
                                            # Попробуем получить через nvidia-smi --query-gpu=clocks.current.graphics
                                            clock_info = subprocess.check_output(['nvidia-smi', '--query-gpu=clocks.current.graphics', '--format=csv,noheader'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                            if clock_info.strip() and cuda_cores:
                                                # Получаем информацию для всех GPU и находим нужную
                                                gpu_lines = clock_info.strip().split('\n')
                                                if gpu_index < len(gpu_lines):
                                                    clock_str = gpu_lines[gpu_index].strip()
                                                    # Парсим частоту из строки вида "2400 MHz"
                                                    clock_match = re.search(r'(\d+(?:\.\d+)?)\s*MHz', clock_str)
                                                    if clock_match:
                                                        graphics_clock_mhz = float(clock_match.group(1))
                                                        # Оценка TFLOPS: (cuda_cores * graphics_clock * 2) / 1000000
                                                        tflops = (cuda_cores * graphics_clock_mhz * 2) / 1000000
                                        except subprocess.TimeoutExpired:
                                            print(f"[WARNING] Timeout getting clock info for GPU {gpu_index}")
                                        except Exception as e:
                                            print(f"[WARNING] Error getting clock info for GPU {gpu_index}: {e}")
                                        
                                        # Fallback для TFLOPS если не удалось получить clock info
                                        if not tflops and cuda_cores:
                                            # Попробуем получить через альтернативные методы
                                            try:
                                                # Метод 1: Попробуем получить через nvidia-smi с другими параметрами
                                                clock_info = subprocess.check_output(['nvidia-smi', '--query-gpu=clocks.current.graphics', '--format=csv,noheader'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                            except:
                                                # Метод 2: Попробуем получить через nvidia-smi без специфичных параметров
                                                try:
                                                    clock_info = subprocess.check_output(['nvidia-smi', '--query-gpu=name,clocks.current.graphics', '--format=csv,noheader'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                                except:
                                                    clock_info = ""
                                            
                                            if clock_info.strip():
                                                # Получаем информацию для всех GPU и находим нужную
                                                gpu_lines = clock_info.strip().split('\n')
                                                if gpu_index < len(gpu_lines):
                                                     try:
                                                         clock_str = gpu_lines[gpu_index].strip()
                                                         # Парсим частоту из строки вида "2400 MHz"
                                                         clock_match = re.search(r'(\d+(?:\.\d+)?)\s*MHz', clock_str)
                                                         if clock_match:
                                                             graphics_clock_mhz = float(clock_match.group(1))
                                                             # Оценка TFLOPS: (cuda_cores * graphics_clock * 2) / 1000000
                                                             tflops = (cuda_cores * graphics_clock_mhz * 2) / 1000000
                                                     except:
                                                         pass
                                            # Попробуем получить через sysfs
                                            try:
                                                for i in range(10):
                                                    try:
                                                        if os.path.exists(f'/sys/class/drm/card{i}/device/gpu_busy_percent'):
                                                            # Попробуем получить clock info через sysfs
                                                            if os.path.exists(f'/sys/class/drm/card{i}/device/pp_dpm_sclk'):
                                                                with open(f'/sys/class/drm/card{i}/device/pp_dpm_sclk', 'r') as f:
                                                                    clock_info = f.read()
                                                                    # Ищем максимальную частоту
                                                                    clock_match = re.search(r'(\d+):\s*(\d+)Mhz', clock_info)
                                                                    if clock_match:
                                                                        max_clock_mhz = int(clock_match.group(2))
                                                                        # Оценка TFLOPS: (cuda_cores * clock * 2) / 1000000
                                                                        tflops = (cuda_cores * max_clock_mhz * 2) / 1000000
                                                                        break
                                                            elif os.path.exists(f'/sys/class/drm/card{i}/device/pp_dpm_gfx'):
                                                                with open(f'/sys/class/drm/card{i}/device/pp_dpm_gfx', 'r') as f:
                                                                    clock_info = f.read()
                                                                    clock_match = re.search(r'(\d+):\s*(\d+)Mhz', clock_info)
                                                                    if clock_match:
                                                                        max_clock_mhz = int(clock_match.group(2))
                                                                        tflops = (cuda_cores * max_clock_mhz * 2) / 1000000
                                                                        break
                                                    except:
                                                        continue
                                            except:
                                                pass
                                            
                                            # Если все еще нет TFLOPS, используем примерную оценку на основе VRAM
                                            if not tflops and vram_gb:
                                                # Примерная оценка: VRAM * 2.5 TFLOPS per GB
                                                tflops = vram_gb * 2.5
                            except subprocess.TimeoutExpired:
                                print(f"[WARNING] Timeout getting detailed info for GPU {gpu_index}")
                            except Exception as e:
                                print(f"[WARNING] Error getting detailed info for GPU {gpu_index}: {e}")
                            
                        gpus.append({
                            "model": model,
                            "vram_gb": vram_gb if vram_gb is not None else 0,  # Backend требует обязательное поле
                            "max_cuda_version": cuda_version,
                            "cuda_cores": cuda_cores,  # Добавляем количество CUDA ядер
                            "tflops": tflops,  # Добавляем TFLOPS
                            "bandwidth_gbps": bandwidth_gbps,  # Добавляем пропускную способность
                            "vendor": "NVIDIA",
                            "count": 1
                        })
            except subprocess.TimeoutExpired:
                print("[WARNING] Timeout getting NVIDIA GPU list")
            except Exception as e:
                print(f"[WARNING] Error getting NVIDIA GPU list: {e}")
            
            # Попробуем lspci для всех GPU (AMD, Intel, другие)
            try:
                print("[DEBUG] Trying lspci for other GPUs...")
                lspci_output = subprocess.check_output(['lspci', '-nn'], timeout=5).decode(errors='ignore')
                for line in lspci_output.split('\n'):
                    if 'VGA compatible controller' in line or '3D controller' in line or 'Display controller' in line:
                        # Правильно парсим строку lspci
                        # Пример: "01:00.0 VGA compatible controller [0300]: Advanced Micro Devices, Inc. [AMD/ATI] Rembrandt [Radeon 680M] [1681:1681] (rev c8)"
                        parts = line.split(':')
                        if len(parts) >= 2:
                            # Берем часть после первого двоеточия
                            device_info = ':'.join(parts[1:]).strip()
                            
                            # Ищем описание устройства - ищем текст между скобками
                            model = "Unknown"
                            vendor = "Unknown"
                            
                            # Ищем AMD/ATI GPU
                            if 'AMD' in device_info or 'ATI' in device_info:
                                vendor = "AMD"
                                # Ищем название модели в скобках
                                amd_match = re.search(r'\[([^\]]+)\]', device_info)
                                if amd_match:
                                    model = amd_match.group(1)
                                    # Если это код, ищем другое описание
                                    if model.isdigit() or len(model) < 4:
                                        # Ищем Radeon в строке
                                        radeon_match = re.search(r'Radeon\s+([^\s\]]+)', device_info)
                                        if radeon_match:
                                            model = f"AMD Radeon {radeon_match.group(1)}"
                                        else:
                                            # Ищем любое описание в скобках
                                            desc_match = re.search(r'\[([^\]]+)\]', device_info)
                                            if desc_match and len(desc_match.group(1)) > 4:
                                                model = desc_match.group(1)
                            # Ищем NVIDIA GPU
                            elif 'NVIDIA' in device_info:
                                vendor = "NVIDIA"
                                nvidia_match = re.search(r'\[([^\]]+)\]', device_info)
                                if nvidia_match:
                                    model = nvidia_match.group(1)
                            # Ищем Intel GPU
                            elif 'Intel' in device_info:
                                vendor = "Intel"
                                intel_match = re.search(r'\[([^\]]+)\]', device_info)
                                if intel_match:
                                    model = intel_match.group(1)
                            
                            # Если модель все еще "Unknown" или слишком короткая, попробуем другой подход
                            if model == "Unknown" or len(model) < 4:
                                # Ищем любое описание в скобках, которое не является кодом
                                all_brackets = re.findall(r'\[([^\]]+)\]', device_info)
                                for bracket_content in all_brackets:
                                    if len(bracket_content) > 4 and not bracket_content.isdigit():
                                        model = bracket_content
                                        break
                            
                            # Получаем дополнительную информацию для AMD GPU
                            vram_gb = None
                            cuda_version = None
                            bandwidth_gbps = None
                            tflops = None
                            
                            if vendor == "AMD":
                                try:
                                    # Попробуем получить информацию через rocm-smi
                                    rocm_output = subprocess.check_output(['rocm-smi', '--showproductname'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                                    if rocm_output.strip():
                                        model = rocm_output.strip()
                                except subprocess.TimeoutExpired:
                                    print("[WARNING] Timeout getting AMD GPU info via rocm-smi")
                                except Exception as e:
                                    print(f"[WARNING] Error getting AMD GPU info via rocm-smi: {e}")
                                
                                # Попробуем получить VRAM через sysfs
                                try:
                                    for i in range(10):
                                        try:
                                            with open(f'/sys/class/drm/card{i}/device/mem_info_vram_total', 'r') as f:
                                                vram_bytes = int(f.read().strip())
                                                vram_gb = vram_bytes // (1024**3)
                                                break
                                        except:
                                            continue
                                except:
                                    pass
                                
                                # Если не удалось получить через sysfs, попробуем другие методы
                                if vram_gb is None:
                                    try:
                                        # Попробуем через /proc/meminfo для интегрированной графики
                                        with open('/proc/meminfo', 'r') as f:
                                            meminfo = f.read()
                                            # Ищем информацию о видеопамяти
                                            vram_match = re.search(r'VramTotal:\s+(\d+)', meminfo)
                                            if vram_match:
                                                vram_kb = int(vram_match.group(1))
                                                vram_gb = vram_kb // (1024 * 1024)
                                    except:
                                        pass
                                
                                # Если все еще нет информации, попробуем через lshw
                                if vram_gb is None:
                                    try:
                                        lshw_output = subprocess.check_output(['lshw', '-class', 'display'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                        vram_match = re.search(r'size:\s+(\d+)\s*([GM])iB', lshw_output)
                                        if vram_match:
                                            size = int(vram_match.group(1))
                                            unit = vram_match.group(2)
                                            if unit == 'G':
                                                vram_gb = size
                                            elif unit == 'M':
                                                vram_gb = size // 1024
                                    except:
                                        pass
                                
                                # Получаем информацию о производительности AMD GPU через rocm-smi
                                try:
                                    # Попробуем получить информацию через rocm-smi
                                    rocm_info = subprocess.check_output(['rocm-smi', '--showproductname', '--showclocks', '--showmeminfo', '--showcomputeunits'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                    if rocm_info.strip():
                                        # Парсим информацию о памяти
                                        mem_match = re.search(r'vram.*?(\d+)\s*MB', rocm_info, re.IGNORECASE)
                                        if mem_match and not vram_gb:
                                            vram_mb = int(mem_match.group(1))
                                            vram_gb = vram_mb // 1024
                                        
                                        # Парсим количество compute units
                                        cu_match = re.search(r'Compute Units:\s*(\d+)', rocm_info)
                                        if cu_match:
                                            compute_units = int(cu_match.group(1))
                                            # Каждый compute unit содержит 64 stream processors в современных AMD GPU
                                            stream_processors = compute_units * 64
                                        else:
                                            try:
                                                for i in range(10):
                                                    try:
                                                        with open(f'/sys/class/drm/card{i}/device/gpu_core_count', 'r') as f:
                                                            stream_processors = int(f.read().strip())
                                                            break
                                                    except:
                                                        continue
                                            except:
                                                stream_processors = None
                                        
                                        # Парсим информацию о частотах
                                        clock_match = re.search(r'GPU.*?(\d+)\s*MHz', rocm_info)
                                        if clock_match and stream_processors:
                                            gpu_clock_mhz = int(clock_match.group(1))
                                            # Универсальная формула TFLOPS для AMD GPU
                                            # 2 операции на такт для современных AMD GPU
                                            tflops = (gpu_clock_mhz * stream_processors * 2) / 1000000
                                except:
                                    pass
                                
                                # Если не удалось получить через rocm-smi, попробуем через sysfs
                                if not tflops or not bandwidth_gbps:
                                    try:
                                        # Получаем информацию о памяти через sysfs
                                        for i in range(10):
                                            try:
                                                with open(f'/sys/class/drm/card{i}/device/mem_info_vram_total', 'r') as f:
                                                    vram_bytes = int(f.read().strip())
                                                    if not vram_gb:
                                                        vram_gb = vram_bytes // (1024**3)
                                                
                                                # Получаем информацию о частоте памяти
                                                with open(f'/sys/class/drm/card{i}/device/pp_dpm_mclk', 'r') as f:
                                                    mclk_info = f.read()
                                                    mclk_match = re.search(r'(\d+):\s*(\d+)Mhz', mclk_info)
                                                    if mclk_match:
                                                        memory_clock_mhz = int(mclk_match.group(2))
                                                        # Оценка bandwidth (примерная)
                                                        bandwidth_gbps = memory_clock_mhz * 2 / 1000  # Примерная оценка
                                                    break
                                            except:
                                                continue
                                    except:
                                        pass
                                
                                # Для AMD GPU CUDA не поддерживается, но есть ROCm
                                cuda_version = "ROCm supported"
                            
                            # Добавляем GPU только если модель определена и не пустая
                            if model != "Unknown" and len(model) > 3:
                                gpus.append({
                                    "model": model,
                                    "vram_gb": vram_gb if vram_gb is not None else 0,  # Backend требует обязательное поле
                                    "max_cuda_version": cuda_version,
                                    "tflops": tflops,
                                    "bandwidth_gbps": bandwidth_gbps,
                                    "vendor": vendor,
                                    "count": 1
                                })
            except subprocess.TimeoutExpired:
                print("[WARNING] Timeout getting GPU info via lspci")
            except Exception as e:
                print(f"[WARNING] lspci parsing error: {e}")
                        
    except subprocess.TimeoutExpired:
        print("[WARNING] Timeout in GPU detection")
    except Exception as e:
        print(f"[ERROR] GPU info failed: {e}")
    
    # Группируем одинаковые GPU и фильтруем мусорные записи
    print("[DEBUG] Grouping identical GPUs and filtering garbage entries...")
    filtered_gpus = []
    gpu_groups = {}
    
    for gpu in gpus:
        model = gpu.get("model", "")
        vendor = gpu.get("vendor", "")
        
        # Фильтруем мусорные записи (коды устройств, слишком короткие названия)
        if (model in ["Unknown", "0300", "1a03:2000"] or 
            len(model) < 4 or 
            model.isdigit() or 
            model.startswith('0') or 
            ':' in model):
            print(f"[DEBUG] Filtering out garbage GPU entry: {model}")
            continue
        
        # Создаем ключ для группировки
        key = f"{vendor}_{model}"
        
        if key in gpu_groups:
            # Увеличиваем count для одинаковых GPU
            gpu_groups[key]["count"] += 1
            print(f"[DEBUG] Found duplicate GPU: {model}, count now: {gpu_groups[key]['count']}")
        else:
            # Добавляем новую GPU
            gpu_groups[key] = gpu.copy()
            gpu_groups[key]["count"] = 1
            print(f"[DEBUG] Added new GPU: {model}")
    
    filtered_gpus = list(gpu_groups.values())
    print(f"[DEBUG] GPU detection completed. Found {len(filtered_gpus)} unique GPUs (total: {len(gpus)} entries)")
    return filtered_gpus

# Универсальная функция для дисков
def get_disk_info():
    disks = []
    system = platform.system()
    try:
        if system == "Darwin":
            # Используем diskutil для получения подробной информации о каждом диске
            disk_list = subprocess.check_output(['diskutil', 'list']).decode()
            for match in re.finditer(r'/dev/(disk\d+)', disk_list):
                disk = match.group(1)
                try:
                    info = subprocess.check_output(['diskutil', 'info', disk]).decode()
                    model = re.search(r'Device / Media Name: (.+)', info)
                    size = re.search(r'Total Size:.*\((\d+(?:\.\d+)?)\s+GB\)', info)
                    dtype = re.search(r'Protocol: (.+)', info)
                    disks.append({
                        "model": model.group(1) if model else disk,
                        "type": dtype.group(1) if dtype else None,
                        "size_gb": float(size.group(1)) if size else None,
                        "read_speed_mb_s": None,
                        "write_speed_mb_s": None
                    })
                except Exception:
                    continue
        elif system == "Windows":
            # Используем wmic для получения информации о дисках
            out = subprocess.check_output(['wmic', 'diskdrive', 'get', 'Model,Size,MediaType,InterfaceType'], shell=True).decode(errors='ignore')
            for line in out.split('\n')[1:]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 4:
                        model = ' '.join(parts[:-3])
                        dtype = parts[-2]
                        size = int(parts[-3]) if parts[-3].isdigit() else None
                        size_gb = size // (1024 ** 3) if size else None
                        disks.append({
                            "model": model,
                            "type": dtype,
                            "size_gb": size_gb,
                            "read_speed_mb_s": None,
                            "write_speed_mb_s": None
                        })
        elif system == "Linux":
            # Упрощенный подход для ноутбуков
            try:
                # Сначала попробуем простой lsblk
                lsblk_output = subprocess.check_output(['lsblk', '-d', '-o', 'NAME,MODEL,SIZE,TYPE'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                lines = lsblk_output.split('\n')
                
                # Находим индекс заголовка
                header_index = -1
                for i, line in enumerate(lines):
                    if 'NAME' in line and 'MODEL' in line and 'SIZE' in line and 'TYPE' in line:
                        header_index = i
                        break
                
                # Обрабатываем строки после заголовка
                for line in lines[header_index + 1:]:
                    if line.strip() and 'disk' in line:
                        parts = line.split()
                        print(f"[DEBUG] Processing disk: {parts}")
                        if len(parts) >= 4:
                            name = parts[0]
                            
                            # Определяем размер и тип - они всегда в конце
                            dtype = parts[-1]  # Последний элемент - это TYPE
                            
                            # Ищем размер - это будет элемент с единицами измерения (G, T, M, K)
                            size_str = None
                            model_parts = []
                            
                            for i, part in enumerate(parts[1:-1]):  # Пропускаем первый (NAME) и последний (TYPE)
                                if any(unit in part.upper() for unit in ['G', 'T', 'M', 'K']) and any(char.isdigit() for char in part):
                                    size_str = part
                                    # Все элементы до размера - это модель
                                    model_parts = parts[1:i+1]
                                    break
                            
                            # Если размер не найден, попробуем найти его в конце перед TYPE
                            if size_str is None and len(parts) >= 5:
                                size_str = parts[-2]  # Предпоследний элемент
                                model_parts = parts[1:-2]  # Все между NAME и SIZE
                            
                            # Проверяем, что размер не содержит неожиданные значения
                            if size_str in ['-', 'Unknown', 'LEGEND'] or not size_str:
                                print(f"[INFO] Skipping disk with invalid size: '{size_str}'")
                                continue
                            
                            # Объединяем части модели
                            model = ' '.join(model_parts) if model_parts else "Unknown"
                            
                            # Дополнительная проверка на наличие неожиданных символов
                            if any(char.isalpha() and char.upper() not in ['G', 'T', 'M', 'K', 'I', 'B'] for char in size_str):
                                print(f"[INFO] Skipping disk size with unexpected characters: '{size_str}'")
                                continue
                            
                            # Улучшенный парсинг размера
                            size_gb = None
                            if size_str != '-':
                                try:
                                    # Убираем все пробелы
                                    size_str = size_str.strip()
                                    
                                    # Проверяем, что строка содержит валидные символы для размера
                                    # Разрешаем форматы: 512G, 1.5T, 256M, 512K, 512GiB, 1.5TiB и т.д.
                                    if not re.match(r'^[\d\.]+[GMTK]?[i]?[B]?$', size_str, re.IGNORECASE):
                                        # Если строка не содержит валидные символы размера, пропускаем её
                                        print(f"[INFO] Skipping invalid disk size format: '{size_str}'")
                                        continue
                                    
                                    if 'G' in size_str.upper():
                                        # Пример: "512G", "512.5G"
                                        size_gb = float(size_str.replace('G', '').replace('g', ''))
                                    elif 'T' in size_str.upper():
                                        # Пример: "1T", "2.5T"
                                        size_gb = float(size_str.replace('T', '').replace('t', '')) * 1024
                                    elif 'M' in size_str.upper():
                                        # Пример: "512M"
                                        size_gb = float(size_str.replace('M', '').replace('m', '')) / 1024
                                    elif 'K' in size_str.upper():
                                        # Пример: "512K"
                                        size_gb = float(size_str.replace('K', '').replace('k', '')) / (1024 * 1024)
                                    elif size_str.isdigit():
                                        # Если это просто число, предполагаем что это байты
                                        size_bytes = int(size_str)
                                        size_gb = size_bytes // (1024**3)
                                    else:
                                        # Попробуем извлечь число из строки
                                        number_match = re.search(r'(\d+(?:\.\d+)?)', size_str)
                                        if number_match:
                                            number = float(number_match.group(1))
                                            if 'T' in size_str.upper():
                                                size_gb = number * 1024
                                            elif 'M' in size_str.upper():
                                                size_gb = number / 1024
                                            elif 'K' in size_str.upper():
                                                size_gb = number / (1024 * 1024)
                                            else:
                                                size_gb = number
                                except Exception as e:
                                    print(f"[WARNING] Failed to parse disk size '{size_str}': {e}")
                                    # Продолжаем обработку других дисков
                                    pass
                            
                            # Если не удалось получить размер через lsblk, попробуем другие методы
                            if size_gb is None:
                                try:
                                    # Попробуем через fdisk
                                    fdisk_output = subprocess.check_output(['fdisk', '-l', name], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                    size_match = re.search(r'Disk\s+\S+:\s+(\d+(?:\.\d+)?)\s*([GM])iB', fdisk_output)
                                    if size_match:
                                        size = float(size_match.group(1))
                                        unit = size_match.group(2)
                                        if unit == 'G':
                                            size_gb = size
                                        elif unit == 'M':
                                            size_gb = size / 1024
                                except:
                                    pass
                            
                            # Если все еще нет размера, попробуем через /proc/partitions
                            if size_gb is None:
                                try:
                                    with open('/proc/partitions', 'r') as f:
                                        for part_line in f.readlines()[2:]:
                                            part_parts = part_line.split()
                                            if len(part_parts) >= 4 and part_parts[3] == name.replace('/dev/', ''):
                                                sectors = int(part_parts[2])
                                                size_gb = sectors // (1024 * 1024)  # 512 байт на сектор
                                                break
                                except:
                                    pass
                            
                            # Последний fallback - через blockdev
                            if size_gb is None:
                                try:
                                    blockdev_output = subprocess.check_output(['blockdev', '--getsize64', name], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                    size_bytes = int(blockdev_output.strip())
                                    size_gb = size_bytes // (1024**3)
                                except:
                                    pass
                            
                            # Определяем тип диска
                            disk_type = "Unknown"
                            try:
                                if os.path.exists(f'/sys/block/{name.replace("/dev/", "")}/queue/rotational'):
                                    with open(f'/sys/block/{name.replace("/dev/", "")}/queue/rotational', 'r') as f:
                                        rotational = f.read().strip()
                                        disk_type = "SSD" if rotational == "0" else "HDD"
                            except:
                                pass
                            
                            # Получаем скорость диска
                            read_speed_mb_s = None
                            write_speed_mb_s = None
                            try:
                                # Попробуем получить через hdparm
                                hdparm_output = subprocess.check_output(['hdparm', '-t', name], stderr=subprocess.DEVNULL, timeout=10).decode(errors='ignore')
                                speed_match = re.search(r'Timing buffered disk reads:\s+(\d+(?:\.\d+)?)\s+MB', hdparm_output)
                                if speed_match:
                                    read_speed_mb_s = float(speed_match.group(1))
                            except:
                                pass
                            
                            # Fallback для скорости на основе типа диска
                            if not read_speed_mb_s:
                                # Попробуем получить через другие методы
                                try:
                                    # Метод 1: dd для измерения скорости
                                    dd_output = subprocess.check_output(['dd', 'if=/dev/zero', f'of={name}', 'bs=1M', 'count=100', 'oflag=direct'], stderr=subprocess.STDOUT, timeout=30).decode(errors='ignore')
                                    speed_match = re.search(r'(\d+(?:\.\d+)?)\s+MB/s', dd_output)
                                    if speed_match:
                                        write_speed_mb_s = float(speed_match.group(1))
                                except:
                                    pass
                                
                                try:
                                    # Метод 2: fio для более точного измерения
                                    fio_cmd = ['fio', '--name=test', f'--filename={name}', '--size=100M', '--readwrite=read', '--direct=1', '--ioengine=libaio', '--bs=1M', '--runtime=10']
                                    fio_output = subprocess.check_output(fio_cmd, stderr=subprocess.DEVNULL, timeout=60).decode(errors='ignore')
                                    speed_match = re.search(r'READ.*BW=(\d+(?:\.\d+)?)MiB/s', fio_output)
                                    if speed_match:
                                        read_speed_mb_s = float(speed_match.group(1))
                                except:
                                    pass
                                
                                # Если все еще нет скорости, используем примерную оценку на основе типа диска
                                if not read_speed_mb_s:
                                    if disk_type == "SSD":
                                        if size_gb and size_gb > 1000:  # NVMe SSD
                                            read_speed_mb_s = 3500
                                            write_speed_mb_s = 3000
                                        else:  # SATA SSD
                                            read_speed_mb_s = 550
                                            write_speed_mb_s = 500
                                    elif disk_type == "HDD":
                                        read_speed_mb_s = 150
                                        write_speed_mb_s = 120
                                    else:
                                        # Для неизвестного типа диска используем консервативную оценку
                                        read_speed_mb_s = 100
                                        write_speed_mb_s = 80
                            
                            disks.append({
                                "model": model,
                                "type": disk_type,
                                "size_gb": size_gb,
                                "read_speed_mb_s": read_speed_mb_s,
                                "write_speed_mb_s": write_speed_mb_s
                            })
                        
            except Exception as e:
                print(f"[WARNING] lsblk failed: {e}")
                # Fallback через /proc/partitions
                try:
                    with open('/proc/partitions', 'r') as f:
                        for line in f.readlines()[2:]:  # Пропускаем заголовки
                            parts = line.split()
                            if len(parts) >= 4 and (parts[3].endswith('sd') or parts[3].endswith('nvme') or parts[3].endswith('hd')):
                                name = f"/dev/{parts[3]}"
                                size_gb = int(parts[2]) // (1024 * 1024)  # Конвертируем из секторов
                                disks.append({
                                    "model": "Unknown",
                                    "type": "Unknown",
                                    "size_gb": size_gb,
                                    "read_speed_mb_s": None,
                                    "write_speed_mb_s": None
                                })
                except Exception as e2:
                    print(f"[WARNING] /proc/partitions also failed: {e2}")
                    pass
                
                # Дополнительный fallback - попробуем через df
                if not disks:
                    try:
                        df_output = subprocess.check_output(['df', '-h', '/'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                        lines = df_output.strip().split('\n')
                        if len(lines) > 1:
                            parts = lines[1].split()
                            if len(parts) >= 2:
                                size_str = parts[1]
                                # Парсим размер (например, "500G", "1T")
                                size_gb = None
                                if 'G' in size_str:
                                    size_gb = float(size_str.replace('G', ''))
                                elif 'T' in size_str:
                                    size_gb = float(size_str.replace('T', '')) * 1024
                                elif 'M' in size_str:
                                    size_gb = float(size_str.replace('M', '')) / 1024
                                
                                if size_gb:
                                    disks.append({
                                        "model": "System Disk",
                                        "type": "Unknown",
                                        "size_gb": size_gb,
                                        "read_speed_mb_s": None,
                                        "write_speed_mb_s": None
                                    })
                    except Exception as e3:
                        print(f"[WARNING] df fallback also failed: {e3}")
                        # Последний fallback - добавляем базовый диск
                        # Пытаемся определить размер через df
                        fallback_disk_added = False
                        try:
                            df_output = subprocess.check_output(['df', '-h', '/'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                            lines = df_output.strip().split('\n')
                            if len(lines) > 1:
                                parts = lines[1].split()
                                if len(parts) >= 2:
                                    size_str = parts[1]
                                    # Парсим размер
                                    fallback_size = None
                                    if 'G' in size_str:
                                        fallback_size = float(size_str.replace('G', ''))
                                    elif 'T' in size_str:
                                        fallback_size = float(size_str.replace('T', '')) * 1024
                                    elif 'M' in size_str:
                                        fallback_size = float(size_str.replace('M', '')) / 1024
                                    
                                    if fallback_size:
                                        disks.append({
                                            "model": "System Disk",
                                            "type": "Unknown",
                                            "size_gb": fallback_size,
                                            "read_speed_mb_s": None,
                                            "write_speed_mb_s": None
                                        })
                                        fallback_disk_added = True
                        except:
                            pass
                        
                        # Если все методы не сработали, используем минимальный размер
                        if not fallback_disk_added:
                            disks.append({
                                "model": "Unknown Disk",
                                "type": "Unknown",
                                "size_gb": 50,  # Минимальный размер вместо хардкода
                                "read_speed_mb_s": None,
                                "write_speed_mb_s": None
                            })
    except Exception as e:
        print(f"[ERROR] Disk info failed: {e}")
        # В случае полной ошибки добавляем базовый диск
        disks.append({
            "model": "Unknown Disk",
            "type": "Unknown",
            "size_gb": 100,
            "read_speed_mb_s": None,
            "write_speed_mb_s": None
        })
    return disks

# Универсальная функция для сетей
def get_network_info():
    networks = []
    system = platform.system()
    try:
        if system == "Darwin":
            sp = subprocess.check_output(['networksetup', '-listallhardwareports']).decode()
            for match in re.finditer(r'Hardware Port: (.+?)\nDevice: (.+?)\n', sp):
                port, device = match.groups()
                up_mbps = None
                try:
                    info = subprocess.check_output(['ifconfig', device]).decode()
                    up = re.search(r'media:.*\((\d+)baseT', info)
                    up_mbps = int(up.group(1)) if up else None
                except Exception:
                    pass
                networks.append({
                    "up_mbps": up_mbps,
                    "down_mbps": up_mbps,
                    "ports": device
                })
        elif system == "Windows":
            # Используем wmic и powershell для получения информации о сетевых интерфейсах
            try:
                out = subprocess.check_output(['wmic', 'nic', 'get', 'Name,Speed'], shell=True).decode(errors='ignore')
                for line in out.split('\n')[1:]:
                    if line.strip():
                        parts = line.split()
                        name = ' '.join(parts[:-1]) if len(parts) > 1 else parts[0]
                        speed = int(parts[-1]) if parts[-1].isdigit() else None
                        networks.append({
                            "up_mbps": speed // 1_000_000 if speed else None,
                            "down_mbps": speed // 1_000_000 if speed else None,
                            "ports": name
                        })
            except Exception:
                pass
        elif system == "Linux":
            # Улучшенное определение сетевых интерфейсов для Linux
            try:
                # Используем ip link для получения списка интерфейсов
                ip_link_output = subprocess.check_output(['ip', '-o', 'link', 'show'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                
                for line in ip_link_output.split('\n'):
                    if line.strip():
                        try:
                            # Парсим строку ip link
                            parts = line.split(':')
                            if len(parts) >= 2:
                                iface_name = parts[1].strip()
                                
                                # Пропускаем loopback и виртуальные интерфейсы
                                if iface_name == 'lo' or iface_name.startswith('virbr') or iface_name.startswith('docker') or iface_name.startswith('veth'):
                                    continue
                                
                                # Получаем реальную скорость интерфейса
                                up_mbps = None
                                down_mbps = None
                                
                                # Метод 1: Через sysfs
                                try:
                                    if os.path.exists(f'/sys/class/net/{iface_name}/speed'):
                                        with open(f'/sys/class/net/{iface_name}/speed', 'r') as f:
                                            speed = f.read().strip()
                                            if speed != '-1' and speed.isdigit():
                                                up_mbps = int(speed)
                                                down_mbps = int(speed)
                                except:
                                    pass
                                
                                # Метод 2: Через ethtool
                                if up_mbps is None:
                                    try:
                                        ethtool_output = subprocess.check_output(['ethtool', iface_name], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                        speed_match = re.search(r'Speed:\s+(\d+)\s*Mb/s', ethtool_output)
                                        if speed_match:
                                            up_mbps = int(speed_match.group(1))
                                            down_mbps = int(speed_match.group(1))
                                    except:
                                        pass
                                
                                # Метод 3: Для WiFi интерфейсов через iwconfig
                                if up_mbps is None and ('wlan' in iface_name or 'wifi' in iface_name or 'wl' in iface_name or iface_name.startswith('wl')):
                                    try:
                                        iwconfig_output = subprocess.check_output(['iwconfig', iface_name], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                        # Определяем стандарт WiFi и устанавливаем соответствующую скорость
                                        if '802.11ax' in iwconfig_output or 'Wi-Fi 6' in iwconfig_output:
                                            up_mbps = 1200  # Mbps для WiFi 6
                                            down_mbps = 1200
                                        elif '802.11ac' in iwconfig_output or 'Wi-Fi 5' in iwconfig_output:
                                            up_mbps = 866   # Mbps для WiFi 5
                                            down_mbps = 866
                                        elif '802.11n' in iwconfig_output:
                                            up_mbps = 300   # Mbps для WiFi 4
                                            down_mbps = 300
                                        elif '802.11g' in iwconfig_output:
                                            up_mbps = 54    # Mbps для WiFi g
                                            down_mbps = 54
                                        else:
                                            up_mbps = 54    # Mbps для старых стандартов
                                            down_mbps = 54
                                    except:
                                        pass
                                
                                # Метод 4: Через /sys/class/net для получения максимальной скорости
                                if up_mbps is None:
                                    try:
                                        if os.path.exists(f'/sys/class/net/{iface_name}/device/max_speed'):
                                            with open(f'/sys/class/net/{iface_name}/device/max_speed', 'r') as f:
                                                max_speed = f.read().strip()
                                                if max_speed.isdigit():
                                                    up_mbps = int(max_speed)
                                                    down_mbps = int(max_speed)
                                    except:
                                        pass
                                
                                # Определяем тип интерфейса
                                interface_type = "Unknown"
                                if 'wlan' in iface_name or 'wifi' in iface_name or 'wl' in iface_name or iface_name.startswith('wl'):
                                    interface_type = "WiFi"
                                elif 'eth' in iface_name or 'en' in iface_name:
                                    interface_type = "Ethernet"
                                
                                # Дополнительная проверка через sysfs
                                try:
                                    if os.path.exists(f'/sys/class/net/{iface_name}/type'):
                                        with open(f'/sys/class/net/{iface_name}/type', 'r') as f:
                                            net_type = f.read().strip()
                                            if net_type == '1':
                                                interface_type = "Ethernet"
                                            elif net_type == '801':
                                                interface_type = "WiFi"
                                except:
                                    pass
                                
                                # Fallback для скорости на основе типа интерфейса
                                if up_mbps is None:
                                    # Попробуем получить через другие методы
                                    try:
                                        # Метод 1: Через /proc/net/dev для получения статистики
                                        with open('/proc/net/dev', 'r') as f:
                                            for line in f.readlines()[2:]:
                                                if iface_name in line:
                                                    parts = line.split()
                                                    if len(parts) >= 10:
                                                        # Получаем байты отправленные и полученные
                                                        bytes_recv = int(parts[1])
                                                        bytes_sent = int(parts[9])
                                                        # Примерная оценка на основе статистики
                                                        if bytes_recv > 0 or bytes_sent > 0:
                                                            # Если есть трафик, пытаемся определить реальную скорость
                                                            try:
                                                                if os.path.exists(f'/sys/class/net/{iface_name}/speed'):
                                                                    with open(f'/sys/class/net/{iface_name}/speed', 'r') as f:
                                                                        speed = f.read().strip()
                                                                        if speed != '-1' and speed.isdigit():
                                                                            up_mbps = int(speed)
                                                                            down_mbps = int(speed)
                                                                        else:
                                                                            # Fallback к типичным значениям
                                                                            if interface_type == "Ethernet":
                                                                                up_mbps = 1000
                                                                                down_mbps = 1000
                                                                            elif interface_type == "WiFi":
                                                                                up_mbps = 300
                                                                                down_mbps = 300
                                                            except:
                                                                # Fallback к типичным значениям
                                                                if interface_type == "Ethernet":
                                                                    up_mbps = 1000
                                                                    down_mbps = 1000
                                                                elif interface_type == "WiFi":
                                                                    up_mbps = 300
                                                                    down_mbps = 300
                                                            break
                                    except:
                                        pass
                                    
                                    # Если все еще нет скорости, используем примерную оценку
                                    if up_mbps is None:
                                        if interface_type == "Ethernet":
                                            # Определяем скорость по имени интерфейса
                                            if '10g' in iface_name or '10G' in iface_name:
                                                up_mbps = 10000
                                                down_mbps = 10000
                                            elif '25g' in iface_name or '25G' in iface_name:
                                                up_mbps = 25000
                                                down_mbps = 25000
                                            elif '40g' in iface_name or '40G' in iface_name:
                                                up_mbps = 40000
                                                down_mbps = 40000
                                            elif '100g' in iface_name or '100G' in iface_name:
                                                up_mbps = 100000
                                                down_mbps = 100000
                                            else:
                                                # Пытаемся определить скорость через sysfs
                                                try:
                                                    if os.path.exists(f'/sys/class/net/{iface_name}/speed'):
                                                        with open(f'/sys/class/net/{iface_name}/speed', 'r') as f:
                                                            speed = f.read().strip()
                                                            if speed != '-1' and speed.isdigit():
                                                                up_mbps = int(speed)
                                                                down_mbps = int(speed)
                                                            else:
                                                                # По умолчанию 1Gbps для Ethernet
                                                                up_mbps = 1000
                                                                down_mbps = 1000
                                                    else:
                                                        # По умолчанию 1Gbps для Ethernet
                                                        up_mbps = 1000
                                                        down_mbps = 1000
                                                except:
                                                    # По умолчанию 1Gbps для Ethernet
                                                    up_mbps = 1000
                                                    down_mbps = 1000
                                        elif interface_type == "WiFi":
                                            # Пытаемся определить стандарт WiFi
                                            try:
                                                iwconfig_output = subprocess.check_output(['iwconfig', iface_name], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                                if '802.11ax' in iwconfig_output or 'Wi-Fi 6' in iwconfig_output:
                                                    up_mbps = 1200  # WiFi 6
                                                    down_mbps = 1200
                                                elif '802.11ac' in iwconfig_output or 'Wi-Fi 5' in iwconfig_output:
                                                    up_mbps = 866   # WiFi 5
                                                    down_mbps = 866
                                                elif '802.11n' in iwconfig_output:
                                                    up_mbps = 300   # WiFi 4
                                                    down_mbps = 300
                                                else:
                                                    up_mbps = 54    # Старые стандарты
                                                    down_mbps = 54
                                            except:
                                                up_mbps = 300  # По умолчанию WiFi 4
                                                down_mbps = 300
                                        else:
                                            # Пытаемся определить тип интерфейса и скорость
                                            try:
                                                if os.path.exists(f'/sys/class/net/{iface_name}/speed'):
                                                    with open(f'/sys/class/net/{iface_name}/speed', 'r') as f:
                                                        speed = f.read().strip()
                                                        if speed != '-1' and speed.isdigit():
                                                            up_mbps = int(speed)
                                                            down_mbps = int(speed)
                                                        else:
                                                            up_mbps = 1000  # По умолчанию 1Gbps
                                                            down_mbps = 1000
                                                else:
                                                    up_mbps = 1000  # По умолчанию 1Gbps
                                                    down_mbps = 1000
                                            except:
                                                up_mbps = 1000  # По умолчанию 1Gbps
                                                down_mbps = 1000
                                
                                networks.append({
                                    "up_mbps": up_mbps,
                                    "down_mbps": down_mbps,
                                    "ports": iface_name,
                                    "type": interface_type
                                })
                                
                        except Exception as e:
                            print(f"[WARNING] Network interface parsing error: {e}")
                            continue
                
                # Если не удалось получить информацию через ip, попробуем альтернативные методы
                if not networks:
                    try:
                        # Попробуем через /proc/net/dev
                        with open('/proc/net/dev', 'r') as f:
                            for line in f.readlines()[2:]:  # Пропускаем заголовки
                                if line.strip():
                                    parts = line.split(':')
                                    if len(parts) >= 2:
                                        iface_name = parts[0].strip()
                                        if iface_name != 'lo':  # Пропускаем loopback
                                            interface_type = "Unknown"
                                            if 'wlan' in iface_name or 'wifi' in iface_name or 'wl' in iface_name or iface_name.startswith('wl'):
                                                interface_type = "WiFi"
                                            elif 'eth' in iface_name or 'en' in iface_name:
                                                interface_type = "Ethernet"
                                            
                                            # Пытаемся получить скорость для этого интерфейса
                                            up_mbps = None
                                            down_mbps = None
                                            try:
                                                if os.path.exists(f'/sys/class/net/{iface_name}/speed'):
                                                    with open(f'/sys/class/net/{iface_name}/speed', 'r') as f:
                                                        speed = f.read().strip()
                                                        if speed != '-1' and speed.isdigit():
                                                            up_mbps = int(speed)
                                                            down_mbps = int(speed)
                                            except:
                                                pass
                                            
                                            networks.append({
                                                "up_mbps": up_mbps,
                                                "down_mbps": down_mbps,
                                                "ports": iface_name,
                                                "type": interface_type
                                            })
                    except:
                        pass

            except Exception as e:
                print(f"[WARNING] Network detection error: {e}")
                # Fallback к базовой информации
                try:
                    ip_link = subprocess.check_output(['ip', '-o', 'link', 'show']).decode(errors='ignore')
                    for line in ip_link.split('\n'):
                        if line:
                            iface = line.split(':')[1].strip()
                            if iface != 'lo':  # Пропускаем loopback
                                interface_type = "Unknown"
                                if 'wlan' in iface or 'wifi' in iface or 'wl' in iface or iface.startswith('wl'):
                                    interface_type = "WiFi"
                                elif 'eth' in iface or 'en' in iface:
                                    interface_type = "Ethernet"
                                
                                networks.append({
                                    "up_mbps": None,
                                    "down_mbps": None,
                                    "ports": iface,
                                    "type": interface_type
                                })
                except:
                    pass
    except Exception as e:
        print(f"[ERROR] Network info failed: {e}")
    return networks

# Универсальные функции для hostname и ip

def get_ip_address():
    """Получает реальный IP адрес для SSH подключения"""
    try:
        # Метод 1: Попробуем получить внешний IP через внешний сервис
        try:
            response = requests.get('https://api.ipify.org', timeout=5)
            if response.status_code == 200:
                external_ip = response.text.strip()
                if external_ip and external_ip != '127.0.0.1':
                    return external_ip
        except:
            pass
        
        # Метод 2: Попробуем другой сервис
        try:
            response = requests.get('https://ifconfig.me', timeout=5)
            if response.status_code == 200:
                external_ip = response.text.strip()
                if external_ip and external_ip != '127.0.0.1':
                    return external_ip
        except:
            pass
        
        # Метод 3: Для Linux - попробуем получить IP через сетевые интерфейсы
        if platform.system() == "Linux":
            try:
                # Получаем список всех сетевых интерфейсов
                ip_output = subprocess.check_output(['ip', '-4', 'addr', 'show'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                
                # Ищем IP адреса, исключая localhost и внутренние сети
                for line in ip_output.split('\n'):
                    if 'inet ' in line:
                        # Парсим строку вида "inet 192.168.1.100/24 brd 192.168.1.255 scope global dynamic noprefixroute eth0"
                        parts = line.strip().split()
                        for i, part in enumerate(parts):
                            if part == 'inet':
                                if i + 1 < len(parts):
                                    ip_with_mask = parts[i + 1]
                                    ip = ip_with_mask.split('/')[0]
                                    
                                    # Проверяем, что это не localhost и не внутренний IP
                                    if (ip != '127.0.0.1' and 
                                        not ip.startswith('10.') and 
                                        not ip.startswith('172.16.') and 
                                        not ip.startswith('172.17.') and 
                                        not ip.startswith('172.18.') and 
                                        not ip.startswith('172.19.') and 
                                        not ip.startswith('172.2') and 
                                        not ip.startswith('172.3') and 
                                        not ip.startswith('192.168.')):
                                        return ip
                                    
                                    # Если это локальный IP, но не localhost, тоже можем использовать
                                    if (ip != '127.0.0.1' and 
                                        (ip.startswith('192.168.') or 
                                         ip.startswith('10.') or 
                                         ip.startswith('172.'))):
                                        return ip
            except:
                pass
        
        # Метод 4: Для macOS
        elif platform.system() == "Darwin":
            try:
                # Получаем IP через ifconfig
                ifconfig_output = subprocess.check_output(['ifconfig']).decode(errors='ignore')
                for line in ifconfig_output.split('\n'):
                    if 'inet ' in line and '127.0.0.1' not in line:
                        parts = line.strip().split()
                        for i, part in enumerate(parts):
                            if part == 'inet':
                                if i + 1 < len(parts):
                                    ip = parts[i + 1]
                                    if ip != '127.0.0.1':
                                        return ip
            except:
                pass
        
        # Метод 5: Для Windows
        elif platform.system() == "Windows":
            try:
                ipconfig_output = subprocess.check_output(['ipconfig'], shell=True).decode(errors='ignore')
                for line in ipconfig_output.split('\n'):
                    if 'IPv4 Address' in line:
                        ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                        if ip_match:
                            ip = ip_match.group(1)
                            if ip != '127.0.0.1':
                                return ip
            except:
                pass
        
        # Метод 6: Fallback к старому методу
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip != '127.0.0.1':
                return ip
        except:
            pass
        
        # Если ничего не получилось, возвращаем None
        return None
        
    except Exception as e:
        print(f"[WARNING] IP address detection error: {e}")
        return None

def get_hostname():
    return platform.node()

def get_location_from_ip(ip_address):
    """Определяет код региона по IP адресу"""
    if not ip_address:
        return "Unknown"
    
    try:
        # Используем ipapi.co для определения местоположения
        response = requests.get(f'https://ipapi.co/{ip_address}/json/', timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            # Возвращаем код страны (например, "ru", "us", "de")
            if data.get('country'):
                return data['country'].lower()
                
    except Exception as e:
        print(f"[WARNING] Failed to get location from IP {ip_address}: {e}")
    
    # Fallback к определению по часовому поясу и маппингу на регионы
    try:
        import time
        offset = time.timezone if hasattr(time, 'timezone') else 0
        hours = abs(offset) // 3600
        
        # Маппинг часовых поясов на коды регионов
        timezone_to_region = {
            0: "gb",      # UTC
            1: "gb",      # UTC+1 (UK)
            2: "de",      # UTC+2 (Central Europe)
            3: "ru",      # UTC+3 (Moscow)
            4: "ru",      # UTC+4 (Samara)
            5: "ru",      # UTC+5 (Yekaterinburg)
            6: "ru",      # UTC+6 (Omsk)
            7: "ru",      # UTC+7 (Novosibirsk)
            8: "ru",      # UTC+8 (Krasnoyarsk)
            9: "ru",      # UTC+9 (Irkutsk)
            10: "ru",     # UTC+10 (Vladivostok)
            11: "ru",     # UTC+11 (Magadan)
            12: "ru",     # UTC+12 (Kamchatka)
            -5: "us",     # UTC-5 (Eastern US)
            -6: "us",     # UTC-6 (Central US)
            -7: "us",     # UTC-7 (Mountain US)
            -8: "us",     # UTC-8 (Pacific US)
            -9: "us",     # UTC-9 (Alaska)
            -10: "us",    # UTC-10 (Hawaii)
        }
        
        if offset == 0:
            return "gb"  # UTC
        elif offset in timezone_to_region:
            return timezone_to_region[offset]
        else:
            # Для неизвестных часовых поясов возвращаем "unknown"
            return "unknown"
    except:
        pass
    
    return "unknown"

def get_hardware_info():
    print("[DEBUG] Getting CPU info...")
    try:
        cpus = get_cpu_info()
        print(f"[DEBUG] CPU info collected: {len(cpus)} CPUs")
    except Exception as e:
        print(f"[WARNING] Failed to get CPU info: {e}")
        cpus = []
    
    print("[DEBUG] Getting GPU info...")
    try:
        gpus = get_gpu_info()
        print(f"[DEBUG] GPU info collected: {len(gpus)} GPUs")
    except Exception as e:
        print(f"[WARNING] Failed to get GPU info: {e}")
        gpus = []
    
    print("[DEBUG] Getting disk info...")
    try:
        disks = get_disk_info()
        print(f"[DEBUG] Disk info collected: {len(disks)} disks")
    except Exception as e:
        print(f"[WARNING] Failed to get disk info: {e}")
        disks = []
    
    print("[DEBUG] Getting network info...")
    try:
        networks = get_network_info()
        print(f"[DEBUG] Network info collected: {len(networks)} networks")
    except Exception as e:
        print(f"[WARNING] Failed to get network info: {e}")
        networks = []
    
    return {
        "cpus": cpus,
        "gpus": gpus,
        "disks": disks,
        "networks": networks
    }

def get_system_info():
    print("[DEBUG] Getting hostname...")
    try:
        hostname = get_hostname()
        print(f"[DEBUG] Hostname: {hostname}")
    except Exception as e:
        print(f"[WARNING] Failed to get hostname: {e}")
        hostname = "unknown"
    
    print("[DEBUG] Getting IP address...")
    try:
        ip_address = get_ip_address()
        print(f"[DEBUG] IP address: {ip_address}")
    except Exception as e:
        print(f"[WARNING] Failed to get IP address: {e}")
        ip_address = "unknown"
    
    print("[DEBUG] Getting RAM info...")
    try:
        total_ram_gb, ram_type = get_ram_info()
        print(f"[DEBUG] RAM: {total_ram_gb}GB, type: {ram_type}")
    except Exception as e:
        print(f"[WARNING] Failed to get RAM info: {e}")
        total_ram_gb, ram_type = 0, "unknown"
    
    print("[DEBUG] Getting hardware info...")
    hardware_info = get_hardware_info()
    print("[DEBUG] Hardware info collected")
    
    print("[DEBUG] Getting available ports range...")
    try:
        available_ports_start, available_ports_end = get_available_ports_range()
        print(f"[DEBUG] Available ports: {available_ports_start}-{available_ports_end}")
    except Exception as e:
        print(f"[WARNING] Failed to get available ports range: {e}")
        available_ports_start, available_ports_end = None, None
    
    return {
        "hostname": hostname,
        "ip_address": ip_address,
        "total_ram_gb": total_ram_gb,
        "ram_type": ram_type,
        "hardware_info": hardware_info,
        "available_ports_start": available_ports_start,
        "available_ports_end": available_ports_end
    }

# === Функция отправки данных на сервер ===
def send_init_to_server(agent_id, secret_key, data):
    url = f"{BASE_URL}/v1/agents/{agent_id}/init"
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Secret-Key": secret_key
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"[INFO] Server response: {response.status_code}")
        print(response.text)
        return response.json()
    except Exception as e:
        print(f"[ERROR] Failed to send data: {e}")
        return None

def get_cpu_temperature():
    """Get CPU temperature in Celsius as integer"""
    system = platform.system()
    temperature = None
    
    try:
        if system == "Linux":
            # Попробуем несколько методов для Linux
            temperature_sources = [
                "/sys/class/thermal/thermal_zone0/temp",
                "/sys/class/hwmon/hwmon0/temp1_input",
                "/sys/class/hwmon/hwmon1/temp1_input",
                "/sys/class/hwmon/hwmon*/temp1_input",
                "/proc/acpi/thermal_zone/THM0/temperature",
                "/proc/acpi/thermal_zone/THM1/temperature"
            ]
            
            for source in temperature_sources:
                try:
                    if '*' in source:
                        # Для glob patterns
                        import glob
                        for file_path in glob.glob(source):
                            with open(file_path, 'r') as f:
                                temp_raw = f.read().strip()
                                if temp_raw.isdigit():
                                    temperature = int(int(temp_raw) / 1000)  # Convert from millidegrees to integer
                                    break
                    else:
                        with open(source, 'r') as f:
                            temp_raw = f.read().strip()
                            if temp_raw.isdigit():
                                temperature = int(int(temp_raw) / 1000)  # Convert from millidegrees to integer
                                break
                except:
                    continue
            
            # Если не удалось через файлы, попробуем через sensors
            if temperature is None:
                try:
                    sensors_output = subprocess.check_output(['sensors'], stderr=subprocess.DEVNULL, timeout=10).decode(errors='ignore')
                    # Ищем температуру CPU
                    temp_match = re.search(r'Core 0:\s*\+(\d+(?:\.\d+)?)°C', sensors_output)
                    if temp_match:
                        temperature = int(float(temp_match.group(1)))
                    else:
                        # Попробуем найти любую температуру CPU
                        temp_match = re.search(r'CPU.*\+(\d+(?:\.\d+)?)°C', sensors_output)
                        if temp_match:
                            temperature = int(float(temp_match.group(1)))
                except:
                    pass
                    
        elif system == "Darwin":
            # Для macOS используем powermetrics
            try:
                powermetrics_output = subprocess.check_output(['sudo', 'powermetrics', '-n', '1', '-i', '1000'], stderr=subprocess.DEVNULL, timeout=5).decode(errors='ignore')
                temp_match = re.search(r'CPU die temperature: (\d+(?:\.\d+)?)', powermetrics_output)
                if temp_match:
                    temperature = int(float(temp_match.group(1)))
            except:
                pass
                
        elif system == "Windows":
            # Для Windows используем wmic
            try:
                wmic_output = subprocess.check_output(['wmic', '/namespace:\\\\root\\wmi', 'path', 'MSAcpi_ThermalZoneTemperature', 'get', 'CurrentTemperature'], shell=True).decode(errors='ignore')
                temp_match = re.search(r'(\d+)', wmic_output)
                if temp_match:
                    # Windows возвращает температуру в десятых градуса Кельвина
                    temp_kelvin = int(temp_match.group(1)) / 10.0
                    temperature = int(temp_kelvin - 273.15)  # Convert to Celsius as integer
            except:
                pass
                
    except Exception as e:
        print(f"[WARNING] Failed to get CPU temperature: {e}")
    
    return temperature

def get_network_usage():
    usage = {}
    system = platform.system()
    try:
        # Получаем статистику сети
        counters = psutil.net_io_counters(pernic=True)
        
        # Для Linux используем простой подход - измеряем изменение байт за секунду
        if system == "Linux":
            # Запоминаем начальные значения
            counters_before = {}
            for iface, stats in counters.items():
                counters_before[iface] = stats.bytes_sent + stats.bytes_recv
            
            # Ждем 0.5 секунды вместо 1 секунды для более быстрого отклика
            time.sleep(0.5)
            
            # Получаем новые значения
            counters_after = psutil.net_io_counters(pernic=True)
            
            # Вычисляем использование для каждого интерфейса
            for iface in counters:
                if iface in counters_before and iface in counters_after:
                    before = counters_before[iface]
                    after = counters_after[iface].bytes_sent + counters_after[iface].bytes_recv
                    delta_bytes = after - before
                    
                    # Конвертируем в мегабиты в секунду (умножаем на 2 так как измеряли за 0.5 сек)
                    delta_mbps = (delta_bytes * 8 * 2) / (1024 * 1024)
                    
                    # Получаем реальную скорость интерфейса
                    max_speed = None
                    try:
                        # Попробуем получить скорость через sysfs
                        if os.path.exists(f'/sys/class/net/{iface}/speed'):
                            with open(f'/sys/class/net/{iface}/speed', 'r') as f:
                                speed = f.read().strip()
                                if speed != '-1' and speed.isdigit():
                                    max_speed = int(speed)
                    except:
                        pass
                    
                    # Если не удалось получить скорость, попробуем ethtool
                    if max_speed is None:
                        try:
                            ethtool_output = subprocess.check_output(['ethtool', iface], stderr=subprocess.DEVNULL).decode(errors='ignore')
                            speed_match = re.search(r'Speed:\s+(\d+)\s*Mb/s', ethtool_output)
                            if speed_match:
                                max_speed = int(speed_match.group(1))
                        except:
                            pass
                    
                    # Если все еще не удалось получить скорость, используем разумные предположения
                    if max_speed is None:
                        # Определяем тип интерфейса по имени
                        if 'wlan' in iface or 'wifi' in iface or 'wl' in iface or iface.startswith('wl'):
                            # Для WiFi используем типичную скорость в зависимости от стандарта
                            try:
                                iwconfig_output = subprocess.check_output(['iwconfig', iface], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                if '802.11ax' in iwconfig_output or 'Wi-Fi 6' in iwconfig_output:
                                    max_speed = 1200  # Mbps для WiFi 6
                                elif '802.11ac' in iwconfig_output or 'Wi-Fi 5' in iwconfig_output:
                                    max_speed = 866   # Mbps для WiFi 5
                                elif '802.11n' in iwconfig_output:
                                    max_speed = 300   # Mbps для WiFi 4
                                else:
                                    max_speed = 54    # Mbps для старых стандартов
                            except:
                                max_speed = 300  # Предполагаем WiFi 4
                        else:
                            # Для Ethernet пытаемся определить реальную скорость
                            try:
                                if os.path.exists(f'/sys/class/net/{iface}/speed'):
                                    with open(f'/sys/class/net/{iface}/speed', 'r') as f:
                                        speed = f.read().strip()
                                        if speed != '-1' and speed.isdigit():
                                            max_speed = int(speed)
                                        else:
                                            max_speed = 1000  # 1 Gbps по умолчанию
                                else:
                                    max_speed = 1000  # 1 Gbps по умолчанию
                            except:
                                max_speed = 1000  # 1 Gbps по умолчанию
                    
                    # Вычисляем процент использования
                    if max_speed and max_speed > 0:
                        percent = min(100.0, (delta_mbps / max_speed) * 100)
                    else:
                        percent = 0.0
                    
                    usage[iface] = round(percent, 2)
                else:
                    usage[iface] = 0.0
        else:
            # Для других систем используем базовый подход
            for iface in counters:
                usage[iface] = 0.0
                
    except Exception as e:
        print(f"[WARNING] Network usage calculation error: {e}")
        # Возвращаем пустой словарь в случае ошибки
        usage = {}
    
    return usage

def get_gpu_usage():
    """Получение среднего использования GPU для Linux систем"""
    gpu_usage = {}
    system = platform.system()
    
    if system != "Linux":
        return gpu_usage
    
    try:
        total_usage = 0
        gpu_count = 0
        
        # Попробуем получить информацию через nvidia-smi для NVIDIA
        try:
            nvidia_output = subprocess.check_output(['nvidia-smi', '--query-gpu=name,utilization.gpu', '--format=csv,noheader'], stderr=subprocess.DEVNULL).decode(errors='ignore')
            for line in nvidia_output.strip().split('\n'):
                if line:
                    parts = line.split(',')
                    if len(parts) >= 2:
                        gpu_name = parts[0].strip()
                        usage_str = parts[1].strip()
                        usage_match = re.search(r'(\d+)', usage_str)
                        if usage_match:
                            usage = int(usage_match.group(1))
                            total_usage += usage
                            gpu_count += 1
                            # Сохраняем также индивидуальное использование для совместимости
                            gpu_usage[gpu_name] = usage
        except:
            pass
        
        # Попробуем получить информацию через rocm-smi для AMD
        try:
            rocm_output = subprocess.check_output(['rocm-smi', '--showuse'], stderr=subprocess.DEVNULL).decode(errors='ignore')
            for line in rocm_output.split('\n'):
                if 'GPU' in line and '%' in line:
                    match = re.search(r'GPU\s+(\d+).*?(\d+)%', line)
                    if match:
                        gpu_id = match.group(1)
                        usage = int(match.group(2))
                        total_usage += usage
                        gpu_count += 1
                        gpu_usage[f"AMD GPU {gpu_id}"] = usage
        except:
            pass
        
        # Попробуем получить информацию через sysfs для общих GPU
        try:
            for i in range(10):  # Проверяем несколько GPU
                try:
                    # Проверяем, существует ли GPU
                    if os.path.exists(f'/sys/class/drm/card{i}/device/gpu_busy_percent'):
                        with open(f'/sys/class/drm/card{i}/device/gpu_busy_percent', 'r') as f:
                            usage = int(f.read().strip())
                            total_usage += usage
                            gpu_count += 1
                            gpu_usage[f"GPU {i}"] = usage
                except:
                    continue
        except:
            pass
        
        # Вычисляем среднее использование
        if gpu_count > 0:
            avg_usage = total_usage / gpu_count
            # Добавляем среднее использование как отдельное поле
            gpu_usage["average"] = round(avg_usage, 1)
            
    except Exception as e:
        print(f"[WARNING] GPU usage detection error: {e}")
    
    return gpu_usage

# === Docker и SSH ===
def get_running_containers_resources():
    """Получает информацию о ресурсах уже запущенных контейнеров"""
    try:
        import subprocess
        
        # Проверяем права Docker
        use_sudo = False
        try:
            result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                use_sudo = True
        except:
            use_sudo = True
        
        # Получаем список запущенных контейнеров
        cmd = ['docker', 'ps', '--format', '{{.Names}}']
        if use_sudo:
            cmd = ['sudo'] + cmd[1:]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print(f"[WARNING] Failed to get running containers: {result.stderr}")
            return None
        
        container_names = result.stdout.strip().split('\n') if result.stdout.strip() else []
        if not container_names:
            return {'ram_gb': 0, 'disk_gb': 0}
        
        total_ram_gb = 0
        total_disk_gb = 0
        
        # Получаем информацию о ресурсах каждого контейнера
        for container_name in container_names:
            if not container_name:
                continue
                
            # Получаем информацию о памяти контейнера
            try:
                stats_cmd = ['docker', 'stats', container_name, '--no-stream', '--format', '{{.MemUsage}}']
                if use_sudo:
                    stats_cmd = ['sudo'] + stats_cmd[1:]
                
                stats_result = subprocess.run(stats_cmd, capture_output=True, text=True, timeout=5)
                if stats_result.returncode == 0 and stats_result.stdout.strip():
                    mem_usage = stats_result.stdout.strip()
                    # Парсим строку вида "1.234GiB / 2.000GiB" или "31.22MiB / 2.000GiB"
                    try:
                        if 'GiB' in mem_usage:
                            mem_parts = mem_usage.split('/')[0].strip()
                            mem_gb = float(mem_parts.replace('GiB', ''))
                            total_ram_gb += mem_gb
                        elif 'MiB' in mem_usage:
                            mem_parts = mem_usage.split('/')[0].strip()
                            mem_mb = float(mem_parts.replace('MiB', ''))
                            total_ram_gb += mem_mb / 1024
                        elif 'KB' in mem_usage:
                            mem_parts = mem_usage.split('/')[0].strip()
                            mem_kb = float(mem_parts.replace('KB', ''))
                            total_ram_gb += mem_kb / (1024 * 1024)
                        elif 'B' in mem_usage:
                            mem_parts = mem_usage.split('/')[0].strip()
                            mem_b = float(mem_parts.replace('B', ''))
                            total_ram_gb += mem_b / (1024 * 1024 * 1024)
                        else:
                            # Попробуем парсить как число (предполагаем байты)
                            mem_parts = mem_usage.split('/')[0].strip()
                            mem_bytes = float(mem_parts)
                            total_ram_gb += mem_bytes / (1024 * 1024 * 1024)
                    except (ValueError, IndexError) as parse_error:
                        print(f"[WARNING] Could not parse memory usage '{mem_usage}' for container {container_name}: {parse_error}")
                        # Используем примерную оценку
                        total_ram_gb += 1.0  # Примерно 1GB на контейнер
            except Exception as e:
                print(f"[WARNING] Failed to get memory usage for container {container_name}: {e}")
        
        # Оценка дискового пространства (примерная)
        total_disk_gb = len(container_names) * 5  # Примерно 5GB на контейнер
        
        return {
            'ram_gb': total_ram_gb,
            'disk_gb': total_disk_gb,
            'container_count': len(container_names)
        }
        
    except Exception as e:
        print(f"[WARNING] Failed to get running containers resources: {e}")
        return None

def get_available_port(start_port=21234, max_attempts=100):
    """Получает свободный порт для SSH подключения"""
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    return None

def get_available_ports_range(start_port=10000, end_port=65535, max_range_size=1000):
    """Определяет диапазон доступных портов для агента"""
    import socket
    
    # Проверяем, что диапазон валидный
    if start_port >= end_port or start_port < 1 or end_port > 65535:
        print(f"[WARNING] Invalid port range: {start_port}-{end_port}")
        return None, None
    
    # Ищем свободный диапазон портов
    available_start = None
    available_end = None
    
    for port in range(start_port, end_port - max_range_size + 1):
        # Проверяем, свободен ли текущий порт
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                s.close()
                
                # Если порт свободен, проверяем следующий диапазон
                range_available = True
                for check_port in range(port + 1, port + max_range_size):
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                            s2.bind(('localhost', check_port))
                            s2.close()
                    except OSError:
                        range_available = False
                        break
                
                if range_available:
                    available_start = port
                    available_end = port + max_range_size - 1
                    break
        except OSError:
            continue
    
    if available_start and available_end:
        print(f"[INFO] Found available port range: {available_start}-{available_end}")
        return available_start, available_end
    else:
        print(f"[WARNING] No available port range found in {start_port}-{end_port}")
        return None, None

def wait_for_ssh_ready(host, port, timeout=60):
    """Ждет, пока SSH сервис будет готов к подключению"""
    import socket
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                result = s.connect_ex((host, port))
                if result == 0:
                    return True
        except:
            pass
        time.sleep(2)
    return False

def run_docker_container_simple(task):
    """Простая версия создания Docker контейнера с SSH согласно документации"""
    import subprocess
    
    # Получаем данные задачи
    task_data = task.get('task_data', {})
    container_info = task.get('container_info', {})
    
    # Получаем docker_image из task_data
    docker_image = task_data.get('docker_image')
    if not docker_image:
        print("[ERROR] No docker_image specified in task")
        return None
    
    # Получаем SSH credentials из container_info
    ssh_username = container_info.get('ssh_username')
    ssh_password = container_info.get('ssh_password')
    ssh_port = container_info.get('ssh_port')
    ssh_host = container_info.get('ssh_host')
    
    if not all([ssh_username, ssh_password, ssh_port]):
        print("[ERROR] Missing SSH credentials in container_info")
        return None
    
    print(f"[INFO] Using SSH credentials from task:")
    print(f"  Username: {ssh_username}")
    print(f"  Port: {ssh_port}")
    print(f"  Host: {ssh_host}")
    
    # Получаем выделенные ресурсы из задачи
    gpus_allocated = task_data.get('gpus_allocated', {})
    cpus_allocated = task_data.get('cpus_allocated', {})
    ram_allocated = task_data.get('ram_allocated', 0)
    
    # Получаем доступные ресурсы для проверки лимитов
    available_resources = get_available_resources()
    
    # Рассчитываем лимиты ресурсов с проверкой доступности
    cpu_limit = cpus_allocated.get('cores') if cpus_allocated else 1
    if available_resources and cpu_limit > available_resources.get('cpu_count', 1):
        print(f"[WARNING] Requested CPU cores ({cpu_limit}) exceeds available ({available_resources.get('cpu_count', 1)}), using available")
        cpu_limit = available_resources.get('cpu_count', 1)
    
    ram_limit_gb = ram_allocated if ram_allocated else 2
    if available_resources and ram_limit_gb > available_resources.get('available_ram_gb', 2):
        print(f"[WARNING] Requested RAM ({ram_limit_gb}GB) exceeds available ({available_resources.get('available_ram_gb', 2)}GB), using available")
        ram_limit_gb = int(available_resources.get('available_ram_gb', 2))
    
    gpu_limit = gpus_allocated.get('count') if gpus_allocated else 0
    if available_resources and gpu_limit > available_resources.get('gpu_count', 0):
        print(f"[WARNING] Requested GPUs ({gpu_limit}) exceeds available ({available_resources.get('gpu_count', 0)}), using available")
        gpu_limit = available_resources.get('gpu_count', 0)
    
    task_id = task.get('id', int(time.time()))
    container_name = f"task_{task_id}_{ssh_username}"
    
    # Собираем docker run команду согласно документации
    cmd = [
        'docker', 'run', '-d', '--rm',
        '--name', container_name,
        '-p', f'{ssh_port}:22',
        '--memory', f'{ram_limit_gb}g',
        '--cpus', str(cpu_limit)
    ]
    
    # Добавляем GPU если есть
    if gpu_limit > 0:
        print(f"[INFO] GPU access required for {gpu_limit} GPUs")
        
        # Проверяем и исправляем настройки NVIDIA Container Runtime
        try:
            # Проверяем статус nvidia-container-runtime
            result = subprocess.run(['nvidia-container-cli', 'info'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                print("[WARNING] nvidia-container-cli not working, attempting to fix...")
                
                # Пытаемся перезапустить nvidia-container-runtime
                try:
                    subprocess.run(['sudo', 'systemctl', 'restart', 'nvidia-container-runtime'], check=True)
                    print("[INFO] nvidia-container-runtime restarted")
                    time.sleep(3)  # Ждем запуска
                except:
                    pass
                
                # Пытаемся перезапустить Docker
                try:
                    subprocess.run(['sudo', 'systemctl', 'restart', 'docker'], check=True)
                    print("[INFO] Docker restarted")
                    time.sleep(5)  # Ждем запуска
                except:
                    pass
                
                # Проверяем снова
                result = subprocess.run(['nvidia-container-cli', 'info'], capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                print("[INFO] nvidia-container-cli is working")
                
                # Проверяем, какой флаг работает - используем более быстрый тест
                print("[INFO] Testing GPU access with --gpus all...")
                
                # Сначала попробуем с уже загруженным образом или быстрым образом
                test_cmd = ['docker', 'run', '--rm', '--gpus', 'all', 'nvidia/cuda:11.0-base', 'nvidia-smi', '--list-gpus']
                test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=30)
                
                if test_result.returncode == 0:
                    cmd += ['--gpus', 'all']
                    print(f"[INFO] Using --gpus all flag for GPU access")
                else:
                    # Пробуем --runtime=nvidia
                    print("[INFO] Testing GPU access with --runtime=nvidia...")
                    test_cmd = ['docker', 'run', '--rm', '--runtime=nvidia', 'nvidia/cuda:11.0-base', 'nvidia-smi', '--list-gpus']
                    test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=30)
                    
                    if test_result.returncode == 0:
                        cmd += ['--runtime=nvidia']
                        print(f"[INFO] Using --runtime=nvidia flag for GPU access")
                    else:
                        # Попробуем с Ubuntu образом (может быть уже загружен)
                        print("[INFO] Testing GPU access with Ubuntu image...")
                        test_cmd = ['docker', 'run', '--rm', '--gpus', 'all', 'ubuntu:20.04', 'bash', '-c', 'nvidia-smi --list-gpus || echo "nvidia-smi not available"']
                        test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=30)
                        
                        if test_result.returncode == 0 and 'nvidia-smi not available' not in test_result.stdout:
                            cmd += ['--gpus', 'all']
                            print(f"[INFO] Using --gpus all flag for GPU access (Ubuntu test)")
                        else:
                            print("[ERROR] Neither --gpus all nor --runtime=nvidia works!")
                            print(f"[ERROR] --gpus all error: {test_result.stderr}")
                            print(f"[ERROR] --runtime=nvidia error: {test_result.stderr}")
                            
                            # Попробуем установить/обновить nvidia-container-toolkit
                            print("[INFO] Attempting to install/update NVIDIA Container Runtime...")
                            try:
                                if install_nvidia_container_runtime():
                                    # Проверяем снова
                                    test_cmd = ['docker', 'run', '--rm', '--gpus', 'all', 'nvidia/cuda:11.0-base', 'nvidia-smi', '--list-gpus']
                                    test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=30)
                                    
                                    if test_result.returncode == 0:
                                        cmd += ['--gpus', 'all']
                                        print(f"[INFO] GPU access fixed, using --gpus all")
                                    else:
                                        raise Exception("GPU access still not working after installation")
                                else:
                                    raise Exception("Failed to install NVIDIA Container Runtime")
                            except Exception as e:
                                print(f"[ERROR] Failed to fix GPU access: {e}")
                                raise Exception("GPU access is required but not available")
            else:
                print(f"[ERROR] nvidia-container-cli failed: {result.stderr}")
                raise Exception("nvidia-container-cli not working")
                
        except Exception as e:
            print(f"[ERROR] GPU setup failed: {e}")
            raise Exception(f"GPU access is required but setup failed: {e}")
    
    # Добавляем образ и команду запуска
    cmd += [
        docker_image,
        'bash', '-c',
        f"apt-get update && apt-get install -y openssh-server sudo && "
        f"mkdir /var/run/sshd && "
        f"useradd -m -s /bin/bash {ssh_username} && "
        f"echo '{ssh_username}:{ssh_password}' | chpasswd && "
        f"usermod -aG sudo {ssh_username} && "
        f"sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && "
        f"/usr/sbin/sshd -D"
    ]
    
    print(f"[INFO] Starting container with command: {' '.join(cmd)}")
    
    # Проверяем права Docker
    use_sudo = False
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            use_sudo = True
    except:
        use_sudo = True
    
    if use_sudo:
        cmd = ['sudo'] + cmd
    
    try:
        print(f"[INFO] Executing Docker command...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            print(f"[ERROR] Docker command failed with return code {result.returncode}")
            print(f"[ERROR] Docker stderr: {result.stderr}")
            print(f"[ERROR] Docker stdout: {result.stdout}")
            
            # Если GPU обязателен, не пытаемся запускать без него
            if gpu_limit > 0:
                print(f"[ERROR] GPU access is required but Docker command failed")
                print(f"[ERROR] Please check NVIDIA Container Runtime installation")
                print(f"[ERROR] Try running: sudo apt-get install nvidia-container-toolkit")
                print(f"[ERROR] Then restart Docker: sudo systemctl restart docker")
                return None
            else:
                return None
        else:
            container_id = result.stdout.strip()
            print(f"[INFO] Container started with ID: {container_id}")
        
        # Ожидаем готовности SSH
        print(f"[INFO] Waiting for SSH service to be ready on port {ssh_port}...")
        if wait_for_ssh_ready('localhost', ssh_port):
            print(f"[INFO] SSH service is ready on port {ssh_port}")
        else:
            print(f"[WARNING] SSH service not ready within timeout on port {ssh_port}")
        
        return {
            'container_id': container_id,
            'container_name': container_name,
            'ssh_port': ssh_port,
            'ssh_host': ssh_host,
            'ssh_command': container_info.get('ssh_command', f"ssh {ssh_username}@{ssh_host} -p {ssh_port}"),
            'ssh_username': ssh_username,
            'ssh_password': ssh_password,
            'status': 'running',
            'allocated_resources': {
                'cpu_cores': cpu_limit,
                'ram_gb': ram_limit_gb,
                'gpu_count': gpu_limit,
                'storage_gb': 20,
                'gpu_support': gpu_limit > 0
            }
        }
        
    except subprocess.TimeoutExpired:
        print("[ERROR] Docker operation timed out")
        return None
    except Exception as e:
        print(f"[ERROR] Docker operation failed: {e}")
        return None

def run_docker_container(task):
    import subprocess
    import secrets
    import string
    import random
    
    # Получаем доступные ресурсы системы
    available_resources = get_available_resources()
    if not available_resources:
        print("[ERROR] Failed to get available resources")
        return None
    
    print(f"[INFO] Available resources: {json.dumps(available_resources, indent=2)}")
    
    # Получаем данные задачи
    task_data = task.get('task_data', {})
    container_info = task.get('container_info', {})
    
    # Получаем docker_image из task_data
    docker_image = task_data.get('docker_image')
    if not docker_image:
        print("[ERROR] No docker_image specified in task")
        return None
    
    # Получаем SSH credentials из container_info
    ssh_username = container_info.get('ssh_username')
    ssh_password = container_info.get('ssh_password')
    ssh_port = container_info.get('ssh_port')
    ssh_host = container_info.get('ssh_host')
    
    if not all([ssh_username, ssh_password, ssh_port]):
        print("[ERROR] Missing SSH credentials in container_info")
        return None
    
    print(f"[INFO] Using SSH credentials from task:")
    print(f"  Username: {ssh_username}")
    print(f"  Port: {ssh_port}")
    print(f"  Host: {ssh_host}")
    
    # === 1. РАСЧЕТ РЕСУРСОВ ИЗ TASK_DATA ===
    # Получаем выделенные ресурсы из задачи
    gpus_allocated = task_data.get('gpus_allocated', {})
    cpus_allocated = task_data.get('cpus_allocated', {})
    ram_allocated = task_data.get('ram_allocated', 0)
    storage_allocated = task_data.get('storage_allocated', 0)
    
    # Используем выделенные ресурсы или рассчитываем из доступных
    cpu_limit = cpus_allocated.get('cores') if cpus_allocated else max(1, int(available_resources['cpu_count'] * 0.9))
    ram_limit_gb = ram_allocated if ram_allocated else max(2, int(available_resources['available_ram_gb'] * 0.9))
    gpu_limit = gpus_allocated.get('count') if gpus_allocated else (available_resources['gpu_count'] if check_docker_gpu_support() else 0)
    storage_limit_gb = storage_allocated if storage_allocated else max(20, int(available_resources['available_disk_gb'] * 0.9))
    
    print(f"[INFO] Allocating resources for container:")
    print(f"  CPU: {cpu_limit} cores")
    print(f"  RAM: {ram_limit_gb}GB")
    print(f"  GPU: {gpu_limit} GPUs")
    print(f"  Storage: {storage_limit_gb}GB")
    
    # === 2. СОЗДАНИЕ DOCKERFILE С SSH ===
    import tempfile
    
    task_id = task.get('id', int(time.time()))
    container_name = f"task_{task_id}_{ssh_username}"
    
    # Создаем временный Dockerfile
    dockerfile_content = f"""
FROM {docker_image}

# Объединяем все команды RUN для ускорения сборки
RUN apt-get update && apt-get install -y \\
    openssh-server \\
    sudo \\
    curl \\
    wget \\
    git \\
    vim \\
    nano \\
    htop \\
    software-properties-common \\
    && rm -rf /var/lib/apt/lists/* \\
    && mkdir -p /var/run/sshd /workspace \\
    && useradd -m -s /bin/bash {ssh_username} \\
    && echo '{ssh_username}:{ssh_password}' | chpasswd \\
    && usermod -aG sudo {ssh_username} \\
    && echo '{ssh_username} ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers \\
    && chown {ssh_username}:{ssh_username} /workspace \\
    && sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config \\
    && sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config \\
    && sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Устанавливаем переменные окружения
ENV HOME=/home/{ssh_username}
ENV WORKSPACE=/workspace

# Открываем порт 22
EXPOSE 22

# Запускаем SSH сервер
CMD ["/usr/sbin/sshd", "-D"]
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.dockerfile', delete=False) as f:
        f.write(dockerfile_content)
        dockerfile_path = f.name
    
    try:
        # === 3. СОБОРКА ОБРАЗА ===
        image_name = f"task-{task_id}-{ssh_username}"
        build_cmd = [
            'docker', 'build', 
            '-f', dockerfile_path,
            '-t', image_name,
            '.'
        ]
        
        # Проверяем права Docker
        use_sudo = False
        try:
            result = subprocess.run(['docker', 'ps'], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                use_sudo = True
        except:
            use_sudo = True
        
        if use_sudo:
            build_cmd = ['sudo'] + build_cmd
        
        print(f"[INFO] Building Docker image: {' '.join(build_cmd)}")
        print(f"[INFO] This may take several minutes on first run...")
        
        try:
            # Запускаем сборку с выводом в реальном времени
            process = subprocess.Popen(
                build_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT, 
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Читаем вывод в реальном времени
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    print(f"[DOCKER BUILD] {output.strip()}")
            
            return_code = process.poll()
            
            if return_code != 0:
                print(f"[ERROR] Docker build failed with return code: {return_code}")
                return None
            else:
                print(f"[INFO] Docker build completed successfully")
                
        except subprocess.TimeoutExpired:
            print("[ERROR] Docker build timed out after 5 minutes")
            if 'process' in locals():
                process.terminate()
            return None
        except Exception as e:
            print(f"[ERROR] Docker build failed: {e}")
            return None
        
        # === 4. ЗАПУСК КОНТЕЙНЕРА ===
        # Собираем docker run команду с оптимальными настройками
        cmd = [
            'docker', 'run', '-d', '--rm',
            '--name', container_name,
            '-p', f'{ssh_port}:22',  # Пробрасываем порт для ssh
            '--memory', f'{ram_limit_gb}g',
            '--cpus', str(cpu_limit),
            '--shm-size', '4g',  # Увеличиваем shared memory для GPU
            '--ulimit', 'memlock=-1',  # Убираем лимит на память для GPU
            '--ulimit', 'stack=67108864',  # Увеличиваем стек для GPU
        ]
        
        # Добавляем GPU если есть
        if gpu_limit > 0:
            cmd += ['--gpus', 'all']
            print(f"[INFO] GPU access enabled for {gpu_limit} GPUs")
        
        # Добавляем volume для хранения данных
        cmd += ['-v', f'/tmp/{container_name}_data:/workspace']
        
        # Добавляем образ
        cmd += [image_name]
        
        print(f"[INFO] Starting container with command: {' '.join(cmd)}")
        
        # Проверяем права Docker перед запуском
        if use_sudo:
            cmd = ['sudo'] + cmd
        
        container_id = subprocess.check_output(cmd, timeout=60).decode().strip()
        print(f"[INFO] Container started with ID: {container_id}")
        
        # === 5. ОЖИДАНИЕ ГОТОВНОСТИ SSH ===
        print(f"[INFO] Waiting for SSH service to be ready on port {ssh_port}...")
        if wait_for_ssh_ready('localhost', ssh_port):
            print(f"[INFO] SSH service is ready on port {ssh_port}")
        else:
            print(f"[WARNING] SSH service not ready within timeout on port {ssh_port}")
        
        # === 6. ПРОВЕРКА КОНТЕЙНЕРА ===
        # Проверяем, что контейнер действительно запущен
        try:
            status_cmd = ['docker', 'ps', '--filter', f'name={container_name}', '--format', '{{.Status}}']
            if use_sudo:
                status_cmd = ['sudo'] + status_cmd[1:]
            
            status = subprocess.check_output(status_cmd, timeout=10).decode().strip()
            if not status:
                print("[ERROR] Container not found in running containers")
                return None
            print(f"[INFO] Container status: {status}")
            
            # Проверяем GPU доступность в контейнере
            if gpu_limit > 0:
                try:
                    gpu_test_cmd = ['docker', 'exec', container_name, 'nvidia-smi']
                    if use_sudo:
                        gpu_test_cmd = ['sudo'] + gpu_test_cmd[1:]
                    
                    gpu_result = subprocess.run(gpu_test_cmd, capture_output=True, text=True, timeout=30)
                    if gpu_result.returncode == 0:
                        print(f"[INFO] GPU access confirmed in container: {gpu_result.stdout[:200]}...")
                    else:
                        print(f"[WARNING] GPU not accessible in container: {gpu_result.stderr}")
                except Exception as e:
                    print(f"[WARNING] Failed to test GPU in container: {e}")
                    
        except Exception as e:
            print(f"[WARNING] Failed to check container status: {e}")
        
        # === 7. ВОЗВРАТ ИНФОРМАЦИИ ===
        return {
            'container_id': container_id,
            'container_name': container_name,
            'ssh_port': ssh_port,
            'ssh_host': ssh_host,
            'ssh_command': container_info.get('ssh_command', f"ssh {ssh_username}@{ssh_host} -p {ssh_port}"),
            'ssh_username': ssh_username,
            'ssh_password': ssh_password,
            'status': 'running',
            'allocated_resources': {
                'cpu_cores': cpu_limit,
                'ram_gb': ram_limit_gb,
                'gpu_count': gpu_limit,
                'storage_gb': storage_limit_gb,
                'gpu_support': gpu_limit > 0
            }
        }
        
    except subprocess.TimeoutExpired:
        print("[ERROR] Docker operation timed out")
        return None
    except Exception as e:
        print(f"[ERROR] Docker operation failed: {e}")
        return None
    finally:
        # Удаляем временный файл
        try:
            os.unlink(dockerfile_path)
        except:
            pass

def stop_docker_container(container_info):
    """Останавливает Docker контейнер"""
    import subprocess
    try:
        container_name = container_info.get('container_name')
        if container_name:
            cmd = ['docker', 'stop', container_name]
            subprocess.run(cmd, check=True)
            print(f"[INFO] Container {container_name} stopped")
            return True
    except Exception as e:
        print(f"[ERROR] Failed to stop container: {e}")
    return False

def get_container_status(container_name):
    """Получает статус Docker контейнера"""
    import subprocess
    try:
        cmd = ['docker', 'ps', '--filter', f'name={container_name}', '--format', '{{.Status}}']
        result = subprocess.check_output(cmd).decode().strip()
        return 'running' if result else 'stopped'
    except:
        return 'unknown'

def list_running_containers():
    """Получает список запущенных контейнеров"""
    import subprocess
    try:
        # Проверяем права Docker
        if not fix_docker_permissions():
            print("[WARNING] Using sudo for listing containers...")
            cmd = ['sudo', 'docker', 'ps', '--format', '{{.Names}}\t{{.Status}}\t{{.Ports}}']
        else:
            cmd = ['docker', 'ps', '--format', '{{.Names}}\t{{.Status}}\t{{.Ports}}']
        
        result = subprocess.check_output(cmd, timeout=10).decode().strip()
        containers = []
        for line in result.split('\n'):
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 3:
                    containers.append({
                        'name': parts[0],
                        'status': parts[1],
                        'ports': parts[2]
                    })
        return containers
    except subprocess.TimeoutExpired:
        print("[WARNING] List containers command timed out")
        return []
    except Exception as e:
        print(f"[ERROR] Failed to list containers: {e}")
        return []

def cleanup_stopped_containers():
    """Удаляет остановленные контейнеры"""
    import subprocess
    try:
        # Проверяем права Docker
        if not fix_docker_permissions():
            print("[WARNING] Using sudo for cleanup...")
            cmd = ['sudo', 'docker', 'container', 'prune', '-f']
        else:
            cmd = ['docker', 'container', 'prune', '-f']
        
        subprocess.run(cmd, check=True, timeout=30)
        print("[INFO] Cleaned up stopped containers")
    except subprocess.TimeoutExpired:
        print("[WARNING] Cleanup command timed out")
    except Exception as e:
        print(f"[ERROR] Failed to cleanup containers: {e}")

def test_ssh_connection(host, port, timeout=10):
    """Тестирует SSH подключение к контейнеру"""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((host, port))
            return result == 0
    except:
        return False

def poll_for_tasks(agent_id, secret_key):
    url = f"{BASE_URL}/v1/agents/{agent_id}/tasks/pull"
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Secret-Key": secret_key
    }
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            print(f"[DEBUG] Polling for tasks from {url}")
            response = requests.post(url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                resp_json = response.json()
                
                # Проверяем exception поле согласно документации
                if resp_json.get('exception') != 0:
                    print(f"[WARNING] Server returned exception: {resp_json.get('message', 'Unknown error')}")
                    consecutive_errors += 1
                    time.sleep(10)
                    continue
                
                data = resp_json.get('data', {})
                task_id = data.get('task_id')
                task_data = data.get('task_data')
                container_info = data.get('container_info')
                message = data.get('message', '')
                
                print(f"[INFO] Server response: {message}")
                
                if task_id is not None and task_data is not None and container_info is not None:
                    print(f"[INFO] New task received:")
                    print(f"  Task ID: {task_id}")
                    print(f"  Docker Image: {task_data.get('docker_image')}")
                    print(f"  SSH Username: {container_info.get('ssh_username')}")
                    print(f"  SSH Port: {container_info.get('ssh_port')}")
                    print(f"  SSH Command: {container_info.get('ssh_command')}")
                    
                    # Проверяем права Docker перед запуском контейнера
                    if not fix_docker_permissions():
                        print("[ERROR] Docker permissions not available, trying with sudo...")
                        # Продолжаем, но будем использовать sudo
                    
                    # Проверяем поддержку GPU в Docker
                    gpu_support = check_docker_gpu_support()
                    if not gpu_support:
                        print("[WARNING] GPU support not available in Docker, containers will run without GPU access")
                    
                    # Создаем полную задачу с task_id и container_info
                    full_task = {
                        'id': task_id,
                        'task_data': task_data,
                        'container_info': container_info
                    }
                    
                    # Используем простую версию создания контейнера
                    container_info = run_docker_container_simple(full_task)
                    if container_info:
                        print(f"[INFO] Docker container started successfully:")
                        print(f"  Container ID: {container_info['container_id']}")
                        print(f"  Container Name: {container_info['container_name']}")
                        print(f"  SSH Host: {container_info['ssh_host']}")
                        print(f"  SSH Port: {container_info['ssh_port']}")
                        print(f"  SSH Command: {container_info['ssh_command']}")
                        print(f"  Allocated Resources: {container_info.get('allocated_resources', 'N/A')}")
                        
                        # Отправляем статус задачи обратно на сервер с container_id
                        send_task_status(agent_id, task_id, secret_key, container_info)
                        consecutive_errors = 0  # Сбрасываем счетчик ошибок при успехе
                    else:
                        print(f"[ERROR] Failed to start container for task {task_id}")
                        consecutive_errors += 1
                elif task_id is None:
                    print(f"[INFO] No tasks available: {message}")
                    consecutive_errors = 0  # Сбрасываем счетчик ошибок
                else:
                    print(f"[WARNING] Invalid task data received: {data}")
                    consecutive_errors += 1
            else:
                print(f"[WARNING] Server returned status {response.status_code}")
                print(f"[DEBUG] Server response: {response.text}")
                consecutive_errors += 1
                
        except requests.exceptions.Timeout:
            print("[WARNING] Request timeout, retrying...")
            consecutive_errors += 1
        except requests.exceptions.ConnectionError:
            print("[WARNING] Connection error, retrying...")
            consecutive_errors += 1
        except Exception as e:
            print(f"[ERROR] Polling failed: {e}")
            consecutive_errors += 1
        
        # Если слишком много ошибок подряд, увеличиваем интервал
        if consecutive_errors >= max_consecutive_errors:
            print(f"[WARNING] Too many consecutive errors ({consecutive_errors}), increasing poll interval")
            time.sleep(60)  # Увеличиваем интервал до 1 минуты
        else:
            time.sleep(10)  # Обычный интервал

def send_task_status(agent_id, task_id, secret_key, container_info):
    url = f"{BASE_URL}/v1/agents/{agent_id}/tasks/{task_id}/status"
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Secret-Key": secret_key
    }
    data = {
        "status": "running",
        "progress": 0.0,
        "output": f"Container {container_info['container_name']} started successfully. SSH ready on {container_info['ssh_host']}:{container_info['ssh_port']}",
        "error_message": None,
        "container_id": container_info['container_id'],
        "container_name": container_info['container_name']
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"[INFO] Task status updated: {response.status_code}")
        if response.status_code == 200:
            resp_json = response.json()
            if resp_json.get('exception') == 0:
                print(f"[INFO] Task status updated successfully")
                print(f"[INFO] Container ID: {container_info['container_id']}")
                print(f"[INFO] Container Name: {container_info['container_name']}")
                print(f"[INFO] SSH Command: {container_info['ssh_command']}")
                print(f"[INFO] Username: {container_info.get('ssh_username', 'root')}")
                print(f"[INFO] Password: {container_info.get('ssh_password', '')}")
            else:
                print(f"[WARNING] Server returned exception: {resp_json.get('message', 'Unknown error')}")
        else:
            print(f"[WARNING] Server returned status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"[ERROR] Failed to update task status: {e}")

def send_heartbeat(agent_id, secret_key):
    """Отправляет heartbeat с информацией о состоянии агента и использовании ресурсов"""
    url = f"{BASE_URL}/v1/agents/{agent_id}/heartbeat"
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Secret-Key": secret_key
    }
    
    try:
        # Собираем данные мониторинга
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.virtual_memory().percent
        gpu_usage_data = get_gpu_usage()
        
        # Формируем данные GPU usage как словарь
        gpu_usage = {}
        if gpu_usage_data:
            for gpu_id, usage in gpu_usage_data.items():
                if gpu_id != "average":
                    gpu_usage[f"gpu{gpu_id}"] = usage
        
        # Получаем информацию о диске
        disk_usage = {}
        try:
            disk_usage = {"/": psutil.disk_usage('/').percent}
        except:
            pass
        
        # Получаем информацию о сети
        network_usage = get_network_usage()
        net_up_mbps = network_usage.get('up_mbps', 0)
        net_down_mbps = network_usage.get('down_mbps', 0)
        
        data = {
            "status": "online",
            "gpu_usage": gpu_usage,
            "cpu_usage": cpu_usage,
            "memory_usage": memory_usage,
            "disk_usage": disk_usage,
            "network_usage": {
                "up_mbps": net_up_mbps,
                "down_mbps": net_down_mbps
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            resp_json = response.json()
            if resp_json.get('exception') == 0:
                print(f"[INFO] Heartbeat sent successfully")
            else:
                print(f"[WARNING] Heartbeat failed: {resp_json.get('message', 'Unknown error')}")
        else:
            print(f"[WARNING] Heartbeat failed with status {response.status_code}")
            
    except Exception as e:
        print(f"[ERROR] Failed to send heartbeat: {e}")

def confirm_agent(secret_key, data):
    url = f"{BASE_URL}/v1/agents/confirm"
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Secret-Key": secret_key
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"[INFO] Confirm response: {response.status_code}")
        print(response.text)
        resp_json = response.json()
        # Ожидаем, что agent_id будет в data
        agent_id = None
        if resp_json and isinstance(resp_json, dict):
            data_field = resp_json.get("data")
            if data_field and isinstance(data_field, dict):
                agent_id = data_field.get("agent_id") or data_field.get("id")
        return agent_id
    except Exception as e:
        print(f"[ERROR] Failed to confirm agent: {e}")
        return None

# === Git Auto-Update ===
def perform_git_pull():
    """Выполняет git pull для обновления кода агента"""
    try:
        # Проверяем, что мы в git репозитории
        if not os.path.exists('.git'):
            print("[INFO] Not a git repository, skipping git pull")
            return False
        
        # Проверяем, что git доступен
        try:
            subprocess.run(['git', '--version'], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[WARNING] Git not available, skipping git pull")
            return False
        
        print("[INFO] Performing git pull to update agent code...")
        
        # Сохраняем текущую ветку
        current_branch = subprocess.check_output(['git', 'branch', '--show-current'], 
                                               stderr=subprocess.DEVNULL, 
                                               text=True).strip()
        
        # Выполняем git pull
        result = subprocess.run(['git', 'pull', 'origin', current_branch], 
                              capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            if "Already up to date" in result.stdout:
                print("[INFO] Agent code is already up to date")
            else:
                print(f"[INFO] Agent code updated successfully: {result.stdout.strip()}")
                # Если код обновился, можно добавить логику перезапуска
                # Например, установить флаг для graceful restart
            return True
        else:
            print(f"[WARNING] Git pull failed: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        print("[WARNING] Git pull timed out")
        return False
    except Exception as e:
        print(f"[WARNING] Git pull error: {e}")
        return False

if __name__ == "__main__":
    import json
    if len(sys.argv) < 2:
        print("Usage: python installator.py <secret_key>")
        sys.exit(1)
    secret_key = sys.argv[1]
    
    # Проверяем и устанавливаем Docker
    print("[INFO] Checking Docker installation...")
    if not check_and_install_docker():
        print("[ERROR] Docker is required but not available. Please install Docker and restart the script.")
        sys.exit(1)
    
    # Проверяем и исправляем права Docker
    print("[INFO] Checking Docker permissions...")
    if not fix_docker_permissions():
        print("[WARNING] Docker permissions could not be fixed automatically.")
        print("[WARNING] You may need to run: sudo usermod -aG docker $USER")
        print("[WARNING] Then log out and log back in, or restart the system.")
        print("[WARNING] Continuing anyway, but Docker operations may fail...")
    else:
        print("[INFO] Docker permissions are OK")
    
    # Проверяем и устанавливаем GPU драйверы
    print("[INFO] Checking GPU drivers...")
    if not check_and_install_gpu_drivers():
        print("[WARNING] GPU drivers installation failed, but continuing...")
        print("[INFO] GPU functionality may be limited")
    
    # Автоматически определяем location по IP адресу
    print("[INFO] Detecting location automatically from IP address...")
    ip_address = get_ip_address()
    if ip_address:
        location = get_location_from_ip(ip_address)
        print(f"[INFO] Detected location: {location} (IP: {ip_address})")
    else:
        location = "Unknown"
        print("[WARNING] Could not detect IP address, using 'Unknown' location")
    
    # Проверяем, есть ли сохранённый agent_id
    agent_id = None
    if os.path.exists(AGENT_ID_FILE):
        with open(AGENT_ID_FILE, "r") as f:
            agent_id = f.read().strip()
            print(f"[INFO] Loaded agent_id from {AGENT_ID_FILE}: {agent_id}")
    
    # Собираем системную информацию с обработкой ошибок
    print("[INFO] Collecting system information...")
    try:
        system_info = get_system_info()
        print("[INFO] System information collected successfully")
    except Exception as e:
        print(f"[ERROR] Failed to collect system info: {e}")
        system_info = {"hostname": "unknown", "ip_address": ip_address, "total_ram_gb": 0, "ram_type": "unknown", "hardware_info": {}}
    
    # Собираем данные мониторинга с обработкой ошибок
    print("[INFO] Collecting monitoring data...")
    try:
        cpu_usage = psutil.cpu_percent()
        print(f"[INFO] CPU usage: {cpu_usage}%")
    except Exception as e:
        print(f"[WARNING] Failed to get CPU usage: {e}")
        cpu_usage = 0
    
    try:
        memory_usage = psutil.virtual_memory().percent
        print(f"[INFO] Memory usage: {memory_usage}%")
    except Exception as e:
        print(f"[WARNING] Failed to get memory usage: {e}")
        memory_usage = 0
    
    try:
        gpu_usage_data = get_gpu_usage()
        # Используем среднее значение GPU usage, как для CPU
        if "average" in gpu_usage_data:
            gpu_usage = gpu_usage_data["average"]
            # Убираем "average" из данных, оставляем только индивидуальные значения
            del gpu_usage_data["average"]
        else:
            # Если нет среднего значения, вычисляем из индивидуальных значений
            if gpu_usage_data:
                avg_usage = sum(gpu_usage_data.values()) / len(gpu_usage_data)
                gpu_usage = round(avg_usage, 1)
            else:
                gpu_usage = 0
        print(f"[INFO] GPU usage collected: {gpu_usage}%")
    except Exception as e:
        print(f"[WARNING] Failed to get GPU usage: {e}")
        gpu_usage = 0
    
    try:
        disk_usage = {part.mountpoint: psutil.disk_usage(part.mountpoint).percent for part in psutil.disk_partitions()}
        print(f"[INFO] Disk usage collected")
    except Exception as e:
        print(f"[WARNING] Failed to get disk usage: {e}")
        disk_usage = {}
    
    try:
        network_usage = get_network_usage()
        print(f"[INFO] Network usage collected")
    except Exception as e:
        print(f"[WARNING] Failed to get network usage: {e}")
        network_usage = {}
    
    try:
        cpu_temperature = get_cpu_temperature()
        if cpu_temperature is not None:
            print(f"[INFO] CPU temperature: {cpu_temperature}°C")
        else:
            print(f"[INFO] CPU temperature: not available")
    except Exception as e:
        print(f"[WARNING] Failed to get CPU temperature: {e}")
        cpu_temperature = None
    
    data = {
        **system_info,
        "location": location,
        "status": "online",
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "gpu_usage": gpu_usage,  # Теперь это число, а не словарь
        "disk_usage": disk_usage,
        "network_usage": network_usage,
        "cpu_temperature": cpu_temperature,
    }
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
    if not agent_id:
        # Первый запуск — делаем confirm
        print("[INFO] First run - confirming agent with server...")
        try:
            agent_id = confirm_agent(secret_key, data)
            if agent_id:    
                with open(AGENT_ID_FILE, "w") as f:
                    f.write(str(agent_id))
                print(f"[INFO] Saved agent_id to {AGENT_ID_FILE}: {agent_id}")
            else:
                print("[ERROR] Could not obtain agent_id from server. Exiting.")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Failed to confirm agent: {e}")
            sys.exit(1)
    
    # Теперь agent_id есть, делаем init
    print(f"[INFO] Sending init data to server for agent_id: {agent_id}")
    try:
        send_init_to_server(agent_id, secret_key, data)
        print("[INFO] Init data sent successfully")
    except Exception as e:
        print(f"[ERROR] Failed to send init data: {e}")
        # Продолжаем работу даже если init не удался

    # Запускаем polling в отдельном потоке
    print("[INFO] Starting polling thread...")
    try:
        polling_thread = threading.Thread(target=poll_for_tasks, args=(agent_id, secret_key), daemon=True)
        polling_thread.start()
        print("[INFO] Polling thread started successfully")
    except Exception as e:
        print(f"[ERROR] Failed to start polling thread: {e}")
        sys.exit(1)
    
    print("[INFO] Agent initialization completed. Starting main loop...")
    # Основной цикл с периодической очисткой, мониторингом, heartbeat и обновлением кода
    cleanup_counter = 0
    git_pull_counter = 0
    heartbeat_counter = 0
    print("[INFO] Main loop started. Agent is running...")
    
    while True:
        try:
            time.sleep(60)
            cleanup_counter += 1
            git_pull_counter += 1
            heartbeat_counter += 1
            
            # Каждые 5 минут (5 * 60 секунд) отправляем heartbeat
            if heartbeat_counter >= 5:
                print("[INFO] Sending heartbeat...")
                try:
                    send_heartbeat(agent_id, secret_key)
                except Exception as e:
                    print(f"[WARNING] Heartbeat failed: {e}")
                heartbeat_counter = 0
            
            # Каждые 10 минут (10 * 60 секунд) очищаем остановленные контейнеры
            if cleanup_counter >= 10:
                print("[INFO] Running periodic cleanup...")
                try:
                    cleanup_stopped_containers()
                    
                    # Показываем список запущенных контейнеров
                    running_containers = list_running_containers()
                    if running_containers:
                        print(f"[INFO] Currently running containers: {len(running_containers)}")
                        for container in running_containers:
                            print(f"  - {container['name']}: {container['status']} ({container['ports']})")
                    else:
                        print("[INFO] No running containers")
                except Exception as e:
                    print(f"[WARNING] Cleanup failed: {e}")
                
                cleanup_counter = 0
            
            # Каждые 30 минут (30 * 60 секунд) выполняем git pull для обновления кода
            if git_pull_counter >= 30:
                print("[INFO] Running periodic git pull...")
                try:
                    perform_git_pull()
                except Exception as e:
                    print(f"[WARNING] Git pull failed: {e}")
                git_pull_counter = 0
                
        except KeyboardInterrupt:
            print("[INFO] Received interrupt signal. Shutting down...")
            break
        except Exception as e:
            print(f"[ERROR] Main loop error: {e}")
            time.sleep(10)  # Пауза перед продолжением

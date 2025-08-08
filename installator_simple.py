#!/usr/bin/env python3
"""
Упрощенная версия installator.py без psutil
Используется когда есть проблемы с установкой psutil
"""

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

AGENT_ID_FILE = ".agent_id"

# Список необходимых пакетов (без psutil)
REQUIRED_PACKAGES = ["requests", "docker"]

def install_and_import(package):
    try:
        # Сначала пробуем импортировать
        module = importlib.import_module(package)
        globals()[package] = module
        print(f"[INFO] {package} already available")
    except ImportError:
        print(f"[INFO] Installing {package}...")
        try:
            # Пробуем установить с --user флагом
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", package])
        except subprocess.CalledProcessError:
            # Если не получилось, пробуем без --user
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        finally:
            globals()[package] = importlib.import_module(package)

# Устанавливаем пакеты
for pkg in REQUIRED_PACKAGES:
    install_and_import(pkg)

# Импортируем после установки
import requests

# Заглушка для psutil
class PsutilStub:
    def cpu_percent(self): 
        try:
            # Пробуем получить через /proc/loadavg
            with open('/proc/loadavg', 'r') as f:
                load = float(f.read().split()[0])
                return min(load * 25, 100)  # Примерная оценка
        except:
            return 0
    
    def virtual_memory(self): 
        class Mem:
            def __init__(self): 
                try:
                    # Пробуем получить через /proc/meminfo
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
            # Пробуем получить через /proc/mounts
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
                    # Пробуем получить через df
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
                    # Пробуем получить через /proc/net/dev
                    with open('/proc/net/dev', 'r') as f:
                        lines = f.readlines()[2:]  # Пропускаем заголовки
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

# Используем заглушку вместо psutil
psutil = PsutilStub()

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
            
            # Добавляем пользователя в группу docker
            try:
                subprocess.run(['sudo', 'usermod', '-aG', 'docker', os.getenv('USER')], check=True)
                print("[INFO] User added to docker group. You may need to log out and back in.")
            except:
                pass
            
            return True
            
        elif system == "Darwin":
            print("[INFO] Please install Docker Desktop for macOS manually")
            return False
        elif system == "Windows":
            print("[INFO] Please install Docker Desktop for Windows manually")
            return False
        else:
            print(f"[INFO] Docker installation not supported on {system}")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Docker installation failed: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Docker installation error: {e}")
        return False

def check_and_install_docker():
    """Проверяет и устанавливает Docker если нужно"""
    try:
        # Проверяем, запущен ли Docker
        result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
        if result.returncode == 0:
            print("[INFO] Docker is running")
            return True
        else:
            print("[INFO] Docker is not running, trying to start...")
            try:
                subprocess.run(['sudo', 'systemctl', 'start', 'docker'], check=True)
                time.sleep(2)
                result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
                if result.returncode == 0:
                    print("[INFO] Docker started successfully")
                    return True
                else:
                    print("[INFO] Docker start failed, installing...")
                    return install_docker()
            except:
                print("[INFO] Docker start failed, installing...")
                return install_docker()
    except FileNotFoundError:
        print("[INFO] Docker not found, installing...")
        return install_docker()

# Импортируем остальные функции из основного файла
try:
    from installator import (
        detect_gpu_vendor, install_nvidia_drivers, install_amd_drivers, 
        install_intel_drivers, check_and_install_gpu_drivers,
        get_cpu_info, get_ram_info, get_gpu_info, get_disk_info, 
        get_network_info, get_ip_address, get_hostname, get_location_from_ip,
        get_hardware_info, get_system_info, send_init_to_server,
        get_network_usage, get_gpu_usage, get_available_port, wait_for_ssh_ready,
        run_docker_container, stop_docker_container, get_container_status,
        list_running_containers, cleanup_stopped_containers, test_ssh_connection,
        poll_for_tasks, send_task_status, confirm_agent, perform_git_pull
    )
    print("[INFO] Imported functions from main installator.py")
except ImportError as e:
    print(f"[WARNING] Could not import from main installator.py: {e}")
    print("[INFO] Using simplified version with limited functionality")
    
    # Простые заглушки для основных функций
    def get_cpu_info():
        return [{"model": "Unknown CPU", "cores": 1, "threads": 1, "freq_ghz": 1.0, "count": 1}]
    
    def get_ram_info():
        return (8, "DDR4")  # 8GB по умолчанию
    
    def get_gpu_info():
        return []  # Пустой список GPU
    
    def get_disk_info():
        return [{"model": "Unknown Disk", "size_gb": 100, "type": "SSD", "read_speed_mb_s": 500, "write_speed_mb_s": 400}]
    
    def get_network_info():
        return [{"provider": "Unknown", "up_mbps": 100, "down_mbps": 100, "speed_gbps": 0.1, "latency_ms": 10.0}]
    
    def get_ip_address():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def get_hostname():
        return socket.gethostname()
    
    def get_location_from_ip(ip_address):
        return "Unknown"
    
    def get_hardware_info():
        return {
            "cpus": get_cpu_info(),
            "gpus": get_gpu_info(),
            "disks": get_disk_info(),
            "networks": get_network_info()
        }
    
    def get_system_info():
        hostname = get_hostname()
        ip_address = get_ip_address()
        total_ram_gb, ram_type = get_ram_info()
        hardware_info = get_hardware_info()
        return {
            "hostname": hostname,
            "ip_address": ip_address,
            "total_ram_gb": total_ram_gb,
            "ram_type": ram_type,
            "hardware_info": hardware_info
        }
    
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
    
    def get_network_usage():
        return {}
    
    def get_gpu_usage():
        return {}
    
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
            agent_id = None
            if resp_json and isinstance(resp_json, dict):
                data_field = resp_json.get("data")
                if data_field and isinstance(data_field, dict):
                    agent_id = data_field.get("agent_id") or data_field.get("id")
            return agent_id
        except Exception as e:
            print(f"[ERROR] Failed to confirm agent: {e}")
            return None
    
    def perform_git_pull():
        return True
    
    def poll_for_tasks(agent_id, secret_key):
        while True:
            time.sleep(30)
            print("[INFO] Polling for tasks...")

if __name__ == "__main__":
    import json
    if len(sys.argv) < 2:
        print("Usage: python installator_simple.py <secret_key>")
        sys.exit(1)
    secret_key = sys.argv[1]
    
    # Проверяем и устанавливаем Docker
    print("[INFO] Checking Docker installation...")
    if not check_and_install_docker():
        print("[ERROR] Docker is required but not available. Please install Docker and restart the script.")
        sys.exit(1)
    
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
    
    system_info = get_system_info()
    data = {
        **system_info,
        "location": location,
        "status": "online",
        "cpu_usage": psutil.cpu_percent(),
        "memory_usage": psutil.virtual_memory().percent,
        "gpu_usage": get_gpu_usage(),
        "disk_usage": {part.mountpoint: psutil.disk_usage(part.mountpoint).percent for part in psutil.disk_partitions()},
        "network_usage": get_network_usage(),
    }
    print(json.dumps(data, indent=2, ensure_ascii=False))
    
    if not agent_id:
        # Первый запуск — делаем confirm
        agent_id = confirm_agent(secret_key, data)
        if agent_id:    
            with open(AGENT_ID_FILE, "w") as f:
                f.write(str(agent_id))
            print(f"[INFO] Saved agent_id to {AGENT_ID_FILE}: {agent_id}")
        else:
            print("[ERROR] Could not obtain agent_id from server. Exiting.")
            sys.exit(1)
    
    # Теперь agent_id есть, делаем init
    send_init_to_server(agent_id, secret_key, data)

    # Запускаем polling в отдельном потоке
    polling_thread = threading.Thread(target=poll_for_tasks, args=(agent_id, secret_key), daemon=True)
    polling_thread.start()
    
    # Основной цикл
    print("[INFO] Agent started successfully!")
    print("[INFO] Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(60)
            print("[INFO] Agent is running...")
    except KeyboardInterrupt:
        print("[INFO] Agent stopped by user")

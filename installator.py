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

AGENT_ID_FILE = ".agent_id"

# Список необходимых пакетов
REQUIRED_PACKAGES = ["psutil", "requests"]

def install_and_import(package):
    try:
        importlib.import_module(package)
    except ImportError:
        print(f"[INFO] Installing {package}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    finally:
        globals()[package] = importlib.import_module(package)

for pkg in REQUIRED_PACKAGES:
    install_and_import(pkg)

import psutil
import requests

# Универсальная функция для CPU

def get_cpu_info():
    cpu_info = []
    system = platform.system()
    try:
        if system == "Darwin":
            model = subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string']).decode().strip()
        elif system == "Windows":
            model = subprocess.check_output(['wmic', 'cpu', 'get', 'Name'], shell=True).decode(errors='ignore').split('\n')[1].strip()
        elif system == "Linux":
            with open('/proc/cpuinfo') as f:
                lines = f.read()
            match = re.search(r'model name\s+:\s+(.+)', lines)
            model = match.group(1) if match else platform.processor()
        else:
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
    except Exception:
        pass
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
            try:
                ram_type_out = subprocess.check_output(['sudo', 'dmidecode', '-t', 'memory']).decode(errors='ignore')
                match = re.search(r'Type: (DDR\w*)', ram_type_out)
                if match:
                    ram_type = match.group(1)
            except Exception:
                pass
    except Exception:
        pass
    return total_ram_gb, ram_type

# Универсальная функция для GPU

def get_gpu_info():
    gpus = []
    system = platform.system()
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
                        "vram_gb": int(vram.group(1)) // 1024 if vram else None,
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
                        "vram_gb": vram // (1024 ** 3) if vram else None,
                        "max_cuda_version": None,
                        "tflops": None,
                        "bandwidth_gbps": None,
                        "driver_version": driver,
                        "count": 1
                    })
        elif system == "Linux":
            try:
                lspci = subprocess.check_output(['lspci']).decode(errors='ignore')
                for line in lspci.split('\n'):
                    if 'VGA compatible controller' in line or '3D controller' in line:
                        model = line.split(':')[-1].strip()
                        gpus.append({
                            "model": model,
                            "vram_gb": None,
                            "max_cuda_version": None,
                            "tflops": None,
                            "bandwidth_gbps": None,
                            "count": 1
                        })
            except Exception:
                pass
            # Попробуем nvidia-smi для NVIDIA
            try:
                nvidia_smi = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total', '--format=csv,noheader']).decode(errors='ignore')
                for line in nvidia_smi.strip().split('\n'):
                    if line:
                        model, vram = line.split(',')
                        gpus.append({
                            "model": model.strip(),
                            "vram_gb": int(vram.strip().split()[0]),
                            "max_cuda_version": None,
                            "tflops": None,
                            "bandwidth_gbps": None,
                            "count": 1
                        })
            except Exception:
                pass
    except Exception:
        pass
    return gpus

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
            try:
                lsblk = subprocess.check_output(['lsblk', '-d', '-o', 'NAME,MODEL,SIZE,TYPE'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                for line in lsblk.split('\n')[1:]:
                    if line.strip() and 'disk' in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            name, model, size, dtype = parts[:4]
                            size_gb = int(float(size.replace('G', '')))
                            disks.append({
                                "model": model,
                                "type": dtype,
                                "size_gb": size_gb,
                                "read_speed_mb_s": None,
                                "write_speed_mb_s": None
                            })
            except Exception:
                pass
    except Exception:
        pass
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
            try:
                ip_link = subprocess.check_output(['ip', '-o', 'link', 'show']).decode(errors='ignore')
                for line in ip_link.split('\n'):
                    if line:
                        iface = line.split(':')[1].strip()
                        networks.append({
                            "up_mbps": None,
                            "down_mbps": None,
                            "ports": iface
                        })
            except Exception:
                pass
    except Exception:
        pass
    return networks

# Универсальные функции для hostname и ip

def get_ip_address():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return None

def get_hostname():
    return platform.node()

def get_hardware_info():
    cpus = get_cpu_info()
    gpus = get_gpu_info()
    disks = get_disk_info()
    networks = get_network_info()
    return {
        "cpus": cpus,
        "gpus": gpus,
        "disks": disks,
        "networks": networks
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

def get_network_usage():
    usage = {}
    system = platform.system()
    try:
        counters = psutil.net_io_counters(pernic=True)
        speeds = {}
        # Получаем скорости интерфейсов (в битах/сек)
        if system == "Darwin":
            # macOS: используем networksetup и ifconfig
            try:
                sp = subprocess.check_output(['networksetup', '-listallhardwareports']).decode()
                for match in re.finditer(r'Hardware Port: (.+?)\nDevice: (.+?)\n', sp):
                    port, device = match.groups()
                    try:
                        info = subprocess.check_output(['ifconfig', device]).decode()
                        up = re.search(r'media:.*\((\d+)baseT', info)
                        if up:
                            speeds[device] = int(up.group(1)) * 1_000_000  # в битах/сек
                    except Exception:
                        continue
            except Exception:
                pass
        elif system == "Windows":
            try:
                out = subprocess.check_output(['wmic', 'nic', 'get', 'Name,Speed'], shell=True).decode(errors='ignore')
                for line in out.split('\n')[1:]:
                    if line.strip():
                        parts = line.split()
                        name = ' '.join(parts[:-1]) if len(parts) > 1 else parts[0]
                        speed = int(parts[-1]) if parts[-1].isdigit() else None
                        if speed:
                            speeds[name] = speed  # в битах/сек
            except Exception:
                pass
        # Для Linux можно использовать ethtool, но это требует root
        # Считаем usage как изменение байт за 1 секунду относительно скорости
        import time
        counters_before = {iface: (stats.bytes_sent + stats.bytes_recv) for iface, stats in counters.items()}
        time.sleep(1)
        counters_after = psutil.net_io_counters(pernic=True)
        for iface in counters:
            before = counters_before.get(iface, 0)
            after = counters_after[iface].bytes_sent + counters_after[iface].bytes_recv
            delta_bytes = after - before
            delta_bits = delta_bytes * 8
            speed = speeds.get(iface)
            if speed and speed > 0:
                percent = min(100.0, (delta_bits / speed) * 100)
                usage[iface] = round(percent, 2)
            else:
                usage[iface] = 0.0  # всегда число, если не удалось определить usage
    except Exception:
        pass
    return usage

# === Docker и SSH ===
def run_docker_container(task):
    import subprocess
    docker_image = task.get('docker_image')
    ram = task.get('ram_allocated')
    storage = task.get('storage_allocated')
    gpus = task.get('gpus_allocated')
    cpus = task.get('cpus_allocated')
    # Собираем docker run команду
    cmd = [
        'docker', 'run', '-d', '--rm',
        '--name', f"task_{task.get('id', int(time.time()))}",
        '-p', '21234:22',  # Пробрасываем порт для ssh
    ]
    if ram:
        cmd += ['--memory', f'{ram}g']
    if cpus:
        cpu_count = cpus.get('count', 1) if isinstance(cpus, dict) else cpus
        cmd += ['--cpus', str(cpu_count)]
    if gpus:
        cmd += ['--gpus', 'all']
    if storage:
        # Можно добавить volume, если нужно
        pass
    cmd += [docker_image]
    # Предполагаем, что образ уже настроен для ssh (sshd)
    try:
        container_id = subprocess.check_output(cmd).decode().strip()
        return container_id
    except Exception as e:
        print(f"[ERROR] Docker run failed: {e}")
        return None

def poll_for_tasks(agent_id, secret_key):
    url = f"{BASE_URL}/v1/agents/{agent_id}/tasks/pull"
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Secret-Key": secret_key
    }
    while True:
        try:
            response = requests.post(url, headers=headers, timeout=10)
            if response.status_code == 200:
                resp_json = response.json()
                task = resp_json.get('data')
                if task and task.get('task_id') is not None and task.get('task_data') is not None:
                    print(f"[INFO] New task received: {task}")
                    container_id = run_docker_container(task)
                    if container_id:
                        print(f"[INFO] Docker container started: {container_id}")
                        print(f"[INFO] SSH connect: ssh user@95.165.77.84 -p 21234")
                        # Можно отправить статус задачи обратно на сервер
                        send_task_status(agent_id, task.get('id'), secret_key, container_id)
                else:
                    print(f"[INFO] No valid task received: {task}")
            else:
                print(f"[INFO] No new task. Status: {response.status_code}")
                print(f"[INFO] Server response body: {response.text}")
        except Exception as e:
            print(f"[ERROR] Polling failed: {e}")
        time.sleep(10)  # Пауза между запросами

def send_task_status(agent_id, task_id, secret_key, container_id):
    url = f"{BASE_URL}/v1/agents/{agent_id}/tasks/{task_id}/status"
    headers = {
        "Content-Type": "application/json",
        "X-Agent-Secret-Key": secret_key
    }
    data = {
        "status": "running",
        "container_id": container_id,
        "output": f"ssh user@95.165.77.84 -p 21234"
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        print(f"[INFO] Task status updated: {response.status_code}")
    except Exception as e:
        print(f"[ERROR] Failed to update task status: {e}")

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

if __name__ == "__main__":
    import json
    if len(sys.argv) < 2:
        print("Usage: python installator.py <secret_key>")
        sys.exit(1)
    secret_key = sys.argv[1]
    # Проверяем, есть ли сохранённый agent_id
    agent_id = None
    if os.path.exists(AGENT_ID_FILE):
        with open(AGENT_ID_FILE, "r") as f:
            agent_id = f.read().strip()
            print(f"[INFO] Loaded agent_id from {AGENT_ID_FILE}: {agent_id}")
    system_info = get_system_info()
    data = {
        **system_info,
        "location": "Moscow, Russia",
        "price_per_hour": 1.5,
        "max_duration_hours": 12,
        "status": "online",
        "cpu_usage": psutil.cpu_percent(),
        "memory_usage": psutil.virtual_memory().percent,
        "gpu_usage": {},  # Можно реализовать сбор usage для GPU отдельно
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
    # Основной поток просто ждет
    while True:
        time.sleep(60)

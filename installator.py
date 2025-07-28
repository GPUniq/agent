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
            # Улучшенное получение информации о CPU для Linux
            try:
                with open('/proc/cpuinfo') as f:
                    lines = f.read()
                
                # Ищем модель процессора
                model_match = re.search(r'model name\s+:\s+(.+)', lines)
                if model_match:
                    model = model_match.group(1).strip()
                else:
                    # Альтернативный способ через lscpu
                    try:
                        lscpu_output = subprocess.check_output(['lscpu']).decode()
                        model_match = re.search(r'Model name:\s+(.+)', lscpu_output)
                        model = model_match.group(1).strip() if model_match else platform.processor()
                    except:
                        model = platform.processor()
                
                # Получаем количество ядер и потоков
                cores = psutil.cpu_count(logical=False)
                threads = psutil.cpu_count(logical=True)
                
                # Получаем частоту через lscpu
                freq = None
                try:
                    lscpu_output = subprocess.check_output(['lscpu']).decode()
                    freq_match = re.search(r'CPU max MHz:\s+(\d+)', lscpu_output)
                    if freq_match:
                        freq = float(freq_match.group(1)) / 1000  # Конвертируем в GHz
                    else:
                        # Альтернативный способ через psutil
                        cpu_freq = psutil.cpu_freq()
                        freq = cpu_freq.max / 1000 if cpu_freq else None
                except:
                    cpu_freq = psutil.cpu_freq()
                    freq = cpu_freq.max / 1000 if cpu_freq else None
                
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
            # Улучшенное определение GPU для Linux
            try:
                # Сначала попробуем nvidia-smi для NVIDIA GPU
                nvidia_output = subprocess.check_output(['nvidia-smi', '-L'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                for line in nvidia_output.strip().split('\n'):
                    if line:
                        # Парсим строку вида "GPU 0: NVIDIA GeForce RTX 3080 (UUID: ...)"
                        match = re.search(r'GPU \d+: (.+?) \(UUID:', line)
                        if match:
                            model = match.group(1).strip()
                            
                            # Получаем дополнительную информацию через nvidia-smi
                            vram_gb = None
                            cuda_version = None
                            try:
                                nvidia_detailed = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.total,driver_version', '--format=csv,noheader'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                if nvidia_detailed.strip():
                                    parts = nvidia_detailed.strip().split(',')
                                    if len(parts) >= 2:
                                        vram_str = parts[0].strip()
                                        driver_version = parts[1].strip()
                                        # Парсим VRAM (например, "8192 MiB")
                                        vram_match = re.search(r'(\d+)', vram_str)
                                        if vram_match:
                                            vram_gb = int(vram_match.group(1))
                                        # Парсим CUDA версию из driver version
                                        cuda_match = re.search(r'CUDA Version: (\d+\.\d+)', driver_version)
                                        if cuda_match:
                                            cuda_version = cuda_match.group(1)
                            except:
                                pass
                            
                            gpus.append({
                                "model": model,
                                "vram_gb": vram_gb,
                                "max_cuda_version": cuda_version,
                                "tflops": None,
                                "bandwidth_gbps": None,
                                "vendor": "NVIDIA",
                                "count": 1
                            })
            except:
                pass
            
            # Попробуем lspci для всех GPU
            try:
                lspci_output = subprocess.check_output(['lspci', '-nn']).decode(errors='ignore')
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
                                    rocm_output = subprocess.check_output(['rocm-smi', '--showproductname'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                                    if rocm_output.strip():
                                        model = rocm_output.strip()
                                except:
                                    pass
                                
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
                                
                                # Оцениваем пропускную способность памяти для AMD Radeon 680M
                                if '680M' in model:
                                    bandwidth_gbps = 448  # LPDDR5-6400
                                    # Оценка производительности в TFLOPS (примерная)
                                    tflops = 3.38  # Для Radeon 680M
                                
                                # Для AMD GPU CUDA не поддерживается, но есть ROCm
                                cuda_version = "ROCm supported"
                            
                            # Проверяем, не добавили ли мы уже эту GPU
                            already_added = False
                            for gpu in gpus:
                                if vendor in gpu["model"] and vendor != "Unknown":
                                    already_added = True
                                    break
                            
                            if not already_added and model != "Unknown" and len(model) > 3:
                                gpus.append({
                                    "model": model,
                                    "vram_gb": vram_gb,
                                    "max_cuda_version": cuda_version,
                                    "tflops": tflops,
                                    "bandwidth_gbps": bandwidth_gbps,
                                    "vendor": vendor,
                                    "count": 1
                                })
            except Exception as e:
                print(f"[WARNING] lspci parsing error: {e}")
                pass
                        
    except Exception as e:
        print(f"[ERROR] GPU info failed: {e}")
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
            # Упрощенный подход для ноутбуков
            try:
                # Сначала попробуем простой lsblk
                lsblk_output = subprocess.check_output(['lsblk', '-d', '-o', 'NAME,MODEL,SIZE,TYPE'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                for line in lsblk_output.split('\n')[1:]:  # Пропускаем заголовок
                    if line.strip() and 'disk' in line:
                        parts = line.split()
                        if len(parts) >= 4:
                            name = parts[0]
                            model = parts[1] if parts[1] != '-' else "Unknown"
                            size_str = parts[2]
                            dtype = parts[3]
                            
                            # Парсим размер
                            size_gb = None
                            if size_str != '-':
                                try:
                                    if 'G' in size_str:
                                        size_gb = float(size_str.replace('G', ''))
                                    elif 'T' in size_str:
                                        size_gb = float(size_str.replace('T', '')) * 1024
                                    elif 'M' in size_str:
                                        size_gb = float(size_str.replace('M', '')) / 1024
                                    elif size_str.isdigit():
                                        # Если это просто число, предполагаем что это байты
                                        size_bytes = int(size_str)
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
                            
                            disks.append({
                                "model": model,
                                "type": disk_type,
                                "size_gb": size_gb,
                                "read_speed_mb_s": None,
                                "write_speed_mb_s": None
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
    except Exception as e:
        print(f"[ERROR] Disk info failed: {e}")
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
                                
                                # Пропускаем loopback интерфейсы
                                if iface_name == 'lo':
                                    continue
                                
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
                                
                                networks.append({
                                    "up_mbps": None,
                                    "down_mbps": None,
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
                                            
                                            networks.append({
                                                "up_mbps": None,
                                                "down_mbps": None,
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
                            # Для Ethernet используем типичную скорость
                            max_speed = 1000  # 1 Gbps
                    
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
    """Получение использования GPU для Linux систем"""
    gpu_usage = {}
    system = platform.system()
    
    if system != "Linux":
        return gpu_usage
    
    try:
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
                            gpu_usage[gpu_name] = int(usage_match.group(1))
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
                            gpu_usage[f"GPU {i}"] = usage
                except:
                    continue
        except:
            pass
            
    except Exception as e:
        print(f"[WARNING] GPU usage detection error: {e}")
    
    return gpu_usage

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
                        print(f"[INFO] Container is ready for tasks")
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
        "output": f"Container {container_id} started successfully"
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
        print("Usage: python installator.py <secret_key> [location] [price_per_hour] [max_duration_hours]")
        sys.exit(1)
    secret_key = sys.argv[1]
    
    # Получаем настраиваемые параметры из аргументов командной строки или переменных окружения
    location = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('AGENT_LOCATION', 'Unknown')
    price_per_hour = float(sys.argv[3]) if len(sys.argv) > 3 else float(os.environ.get('AGENT_PRICE_PER_HOUR', '1.5'))
    max_duration_hours = int(sys.argv[4]) if len(sys.argv) > 4 else int(os.environ.get('AGENT_MAX_DURATION_HOURS', '12'))
    
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
        "price_per_hour": price_per_hour,
        "max_duration_hours": max_duration_hours,
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
    # Основной поток просто ждет
    while True:
        time.sleep(60)

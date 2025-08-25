#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import time
import json
import threading
import subprocess
import socket
import re
import importlib
import shutil
import tempfile
import site

def _ensure_python_packages():
    """Ensure required third-party Python packages are installed before imports.
    Installs missing packages using pip; attempts ensurepip if pip is unavailable.
    On Debian/Ubuntu, tries apt-get python3-pip if needed. Exits on failure.
    """
    required_packages = [
        "psutil",
        "requests",
    ]

    def _has_pip(py_exec: str) -> bool:
        try:
            return subprocess.call([py_exec, "-m", "pip", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        except Exception:
            return False

    def _install_pip_via_get_pip(py_exec: str, use_user: bool) -> int:
        try:
            import urllib.request  # stdlib
            url = "https://bootstrap.pypa.io/get-pip.py"
            with tempfile.NamedTemporaryFile(delete=False, suffix="_get-pip.py") as tf:
                tmp_path = tf.name
            try:
                with urllib.request.urlopen(url, timeout=30) as resp, open(tmp_path, "wb") as out:
                    out.write(resp.read())
            except Exception:
                return 1
            cmd = [py_exec, tmp_path]
            if use_user:
                cmd.append("--user")
            try:
                return subprocess.call(cmd)
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
        except Exception:
            return 1

    for package_name in required_packages:
        try:
            importlib.import_module(package_name)
            continue
        except ImportError:
            print(f"[INFO] Missing Python package '{package_name}', attempting to install...")

        python_executable = sys.executable or "python3"

        def _pip_install(use_user: bool) -> int:
            cmd = [python_executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", package_name]
            if use_user:
                cmd.append("--user")
            try:
                return subprocess.call(cmd)
            except Exception:
                return 1

        # Try pip install (prefer --user if not root)
        is_root = False
        try:
            is_root = hasattr(os, "geteuid") and os.geteuid() == 0
        except Exception:
            is_root = False

        # Ensure we have pip first
        if not _has_pip(python_executable):
            tried_any = False
            # Try ensurepip
            try:
                import ensurepip  # type: ignore
                tried_any = True
                ensurepip.bootstrap()
            except Exception:
                pass
            # Recheck
            if not _has_pip(python_executable):
                # Try apt-get only if root or sudo non-interactive works
                apt_get = shutil.which("apt-get")
                sudo = shutil.which("sudo")
                sudo_ok = False
                try:
                    if sudo and not is_root:
                        sudo_ok = subprocess.call([sudo, "-n", "true"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
                except Exception:
                    sudo_ok = False
                if apt_get and (is_root or sudo_ok):
                    print("[INFO] Installing python3-pip via apt to proceed with dependency installation...")
                    try:
                        base = [] if is_root else [sudo, "-n"]
                        subprocess.call(base + [apt_get, "update", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        subprocess.call(base + [apt_get, "install", "-y", "python3-pip"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except Exception:
                        pass
            # Recheck
            if not _has_pip(python_executable):
                # Try get-pip.py (user space)
                gp_rc = _install_pip_via_get_pip(python_executable, use_user=not is_root)
                if gp_rc != 0 and is_root:
                    # If root install failed with --user, retry system-wide
                    _install_pip_via_get_pip(python_executable, use_user=False)

        # Now try pip install of the package
        rc = _pip_install(use_user=not is_root)

        # If pip missing, try ensurepip then install again
        if rc != 0:
            try:
                import ensurepip  # type: ignore
                ensurepip.bootstrap()
                rc = _pip_install(use_user=not is_root)
            except Exception:
                pass

        # If install failed and pip was missing earlier, try get-pip as a last resort
        if rc != 0 and not _has_pip(python_executable):
            gp_rc = _install_pip_via_get_pip(python_executable, use_user=not is_root)
            if gp_rc == 0:
                rc = _pip_install(use_user=not is_root)

        if rc != 0:
            # Try to import from user site by updating sys.path (in case pip installed to user site only)
            try:
                user_site = site.getusersitepackages()
                if user_site and user_site not in sys.path:
                    sys.path.append(user_site)
                    importlib.invalidate_caches()
                    importlib.import_module(package_name)
                    continue
            except Exception:
                pass
            print(f"[ERROR] Could not install required package '{package_name}'. "
                  f"Please ensure network access or install manually: {python_executable} -m pip install --user {package_name}")
            sys.exit(1)


# Ensure dependencies before importing third-party modules elsewhere
_ensure_python_packages()

import psutil
from typing import Dict, Any, Optional

from hardware_analyzer import HardwareAnalyzer
from api_client import APIClient
from clean_manager import ContainerManager

# Константы
AGENT_ID_FILE = ".agent_id"


class Agent:
    """Основной класс агента"""
    
    def __init__(self, secret_key: str, base_url: str = "https://api.gpuniq.ru"):
        self.secret_key = secret_key
        self.base_url = base_url
        self.agent_id = None
        
        # Инициализируем компоненты
        self.hardware_analyzer = HardwareAnalyzer()
        self.api_client = APIClient(base_url=base_url, secret_key=secret_key)
        self.container_manager = ContainerManager()
        
        # Загружаем сохраненный agent_id
        self._load_agent_id()
    
    def _load_agent_id(self):
        """Загружает сохраненный agent_id из файла"""
        if os.path.exists(AGENT_ID_FILE):
            with open(AGENT_ID_FILE, "r") as f:
                self.agent_id = f.read().strip()
                print(f"[INFO] Loaded agent_id from {AGENT_ID_FILE}: {self.agent_id}")
                self.api_client.set_credentials(self.agent_id, self.secret_key)
    
    def _save_agent_id(self, agent_id: str):
        """Сохраняет agent_id в файл"""
        with open(AGENT_ID_FILE, "w") as f:
            f.write(str(agent_id))
        print(f"[INFO] Saved agent_id to {AGENT_ID_FILE}: {agent_id}")
    
    def get_gpu_usage(self) -> Dict[str, Any]:
        """Получение использования GPU"""
        gpu_usage = {}
        
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
                                gpu_usage[gpu_name] = usage
            except:
                pass
            
            # Вычисляем среднее использование
            if gpu_count > 0:
                avg_usage = total_usage / gpu_count
                gpu_usage["average"] = round(avg_usage, 1)
                
        except Exception as e:
            print(f"[WARNING] GPU usage detection error: {e}")
        
        return gpu_usage
    
    def get_network_usage(self) -> Dict[str, Any]:
        """Получение использования сети"""
        usage = {}
        
        try:
            # Получаем статистику сети
            counters = psutil.net_io_counters(pernic=True)
            
            # Для Linux используем простой подход
            if os.name == 'posix':
                # Запоминаем начальные значения
                counters_before = {}
                for iface, stats in counters.items():
                    counters_before[iface] = stats.bytes_sent + stats.bytes_recv
                
                # Ждем 0.5 секунды
                time.sleep(0.5)
                
                # Получаем новые значения
                counters_after = psutil.net_io_counters(pernic=True)
                
                # Вычисляем использование для каждого интерфейса
                for iface in counters:
                    if iface in counters_before and iface in counters_after:
                        before = counters_before[iface]
                        after = counters_after[iface].bytes_sent + counters_after[iface].bytes_recv
                        delta_bytes = after - before
                        
                        # Конвертируем в мегабиты в секунду
                        delta_mbps = (delta_bytes * 8 * 2) / (1024 * 1024)
                        usage[iface] = round(delta_mbps, 2)
                    else:
                        usage[iface] = 0.0
            else:
                # Для других систем используем базовый подход
                for iface in counters:
                    usage[iface] = 0.0
                    
        except Exception as e:
            print(f"[WARNING] Network usage calculation error: {e}")
            usage = {}
        
        return usage
    
    def get_cpu_temperature(self) -> Optional[int]:
        """Get CPU temperature in Celsius as integer"""
        temperature = None
        
        try:
            if os.name == 'posix':
                # Попробуем несколько методов для Linux
                temperature_sources = [
                    "/sys/class/thermal/thermal_zone0/temp",
                    "/sys/class/hwmon/hwmon0/temp1_input",
                    "/sys/class/hwmon/hwmon1/temp1_input",
                ]
                
                for source in temperature_sources:
                    try:
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
                        sensors_output = subprocess.check_output(['sensors'], stderr=subprocess.DEVNULL).decode(errors='ignore')
                        temp_match = re.search(r'Core 0:\s*\+(\d+(?:\.\d+)?)°C', sensors_output)
                        if temp_match:
                            temperature = int(float(temp_match.group(1)))
                    except:
                        pass
                        
        except Exception as e:
            print(f"[WARNING] Failed to get CPU temperature: {e}")
        
        return temperature
    
    def collect_system_data(self) -> Dict[str, Any]:
        """Собирает полные данные о системе"""
        print("[INFO] Collecting system information...")
        
        try:
            # Получаем системную информацию
            system_info = self.hardware_analyzer.get_system_info()
            
            # Получаем данные мониторинга
            cpu_usage = psutil.cpu_percent()
            memory_usage = psutil.virtual_memory().percent
            
            # Получаем информацию о диске
            disk_usage = {}
            try:
                disk_usage = {"/": psutil.disk_usage('/').percent}
            except:
                pass
            
            # Получаем GPU usage
            gpu_usage_data = self.get_gpu_usage()
            gpu_usage = gpu_usage_data.get("average", 0) if gpu_usage_data else 0
            
            # Получаем network usage
            network_usage = self.get_network_usage()
            
            # Получаем CPU temperature
            cpu_temperature = self.get_cpu_temperature()
            
            # Получаем IP адрес и определяем локацию
            ip_address = self.hardware_analyzer.get_ip_address()
            if ip_address:
                location = self.hardware_analyzer.get_location_from_ip(ip_address)
                print(f"[INFO] Detected location: {location} (IP: {ip_address})")
            else:
                location = "Unknown"
                print("[WARNING] Could not detect IP address, using 'Unknown' location")
            
            # Формируем полные данные
            data = {
                **system_info,
                "location": location,
                "status": "online",
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "gpu_usage": gpu_usage,
                "disk_usage": disk_usage,
                "network_usage": network_usage,
                "cpu_temperature": cpu_temperature,
            }
            
            print("[INFO] System information collected successfully")
            return data
            
        except Exception as e:
            print(f"[ERROR] Failed to collect system info: {e}")
            # Возвращаем базовые данные в случае ошибки
            return {
                "hostname": "unknown",
                "ip_address": "unknown",
                "total_ram_gb": 0,
                "ram_type": "unknown",
                "hardware_info": {},
                "location": "Unknown",
                "status": "online",
                "cpu_usage": 0,
                "memory_usage": 0,
                "gpu_usage": 0,
                "disk_usage": {},
                "network_usage": {},
                "cpu_temperature": None,
            }
    
    def collect_monitoring_data(self) -> Dict[str, Any]:
        """Собирает данные мониторинга для heartbeat"""
        try:
            cpu_usage = psutil.cpu_percent()
            memory_usage = psutil.virtual_memory().percent
            
            # Получаем информацию о диске
            disk_usage = {}
            try:
                disk_usage = {"/": psutil.disk_usage('/').percent}
            except:
                pass
            
            # Получаем GPU usage
            gpu_usage_data = self.get_gpu_usage()
            gpu_usage = {}
            if gpu_usage_data:
                for gpu_id, usage in gpu_usage_data.items():
                    if gpu_id != "average":
                        gpu_usage[f"gpu{gpu_id}"] = usage
            
            # Получаем network usage
            network_usage = self.get_network_usage()
            net_up_mbps = sum(network_usage.values()) if network_usage else 0
            net_down_mbps = net_up_mbps  # Упрощенная версия
            
            return {
                "gpu_usage": gpu_usage,
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "disk_usage": disk_usage,
                "network_usage": {
                    "up_mbps": net_up_mbps,
                    "down_mbps": net_down_mbps
                }
            }
            
        except Exception as e:
            print(f"[ERROR] Failed to collect monitoring data: {e}")
            return {
                "gpu_usage": {},
                "cpu_usage": 0,
                "memory_usage": 0,
                "disk_usage": {},
                "network_usage": {"up_mbps": 0, "down_mbps": 0}
            }
    
    def process_task(self, task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Обрабатывает полученную задачу"""
        try:
            print(f"[INFO] Processing task: {task.get('id')}")
            
            task_data = task.get('task_data', {})
            container_info = task.get('container_info', {})
            
            # Получаем docker_image и ресурсы из task_data
            docker_image = task_data.get('docker_image')
            if not docker_image:
                print("[ERROR] No docker_image specified in task")
                return None

            # GPU allocation
            gpu_required = task_data.get('gpu_required', 0) or 0
            gpu_indices = task_data.get('gpu_enabled_indices') or []
            gpus_param = None
            if gpu_required and isinstance(gpu_indices, list) and len(gpu_indices) > 0:
                try:
                    gpus_param = ",".join(str(int(i)) for i in gpu_indices)
                except Exception:
                    gpus_param = "all"
            elif gpu_required:
                gpus_param = "all"

            # CPU allocation: ranges to cpuset string
            cpu_allocated_ranges = task_data.get('cpu_allocated_ranges') or []
            cpuset_cpus = None
            if isinstance(cpu_allocated_ranges, list) and len(cpu_allocated_ranges) > 0:
                try:
                    ranges = []
                    for r in cpu_allocated_ranges:
                        if isinstance(r, (list, tuple)) and len(r) == 2:
                            start, end = int(r[0]), int(r[1])
                            ranges.append(f"{start}-{end}")
                    if ranges:
                        cpuset_cpus = ",".join(ranges)
                except Exception:
                    cpuset_cpus = None

            # RAM and storage
            ram_allocated_gb = task_data.get('ram_allocated_gb')
            storage_allocated_gb = task_data.get('storage_allocated_gb')
            try:
                memory_gb = int(ram_allocated_gb) if ram_allocated_gb is not None else None
            except Exception:
                memory_gb = None
            try:
                storage_gb = int(storage_allocated_gb) if storage_allocated_gb is not None else None
            except Exception:
                storage_gb = None

            # shm-size: int(RAM/2), если RAM задан
            shm_size_gb = None
            if memory_gb is not None and memory_gb > 0:
                try:
                    shm_size_gb = max(1, int(memory_gb / 2))
                except Exception:
                    shm_size_gb = None
            
            # Получаем SSH credentials из container_info
            # Username теперь опционален и всегда используем "root" как значение по умолчанию
            ssh_username = container_info.get('ssh_username') or "root"
            ssh_password = container_info.get('ssh_password')
            ssh_port = container_info.get('ssh_port')
            ssh_host = container_info.get('ssh_host')
            
            # Username больше не обязателен; требуем только пароль и порт
            if not all([ssh_password, ssh_port]):
                print("[ERROR] Missing SSH credentials in container_info")
                return None
            
            print(f"[INFO] Using SSH credentials from task:")
            print(f"  Username: {ssh_username}")
            print(f"  Port: {ssh_port}")
            print(f"  Host: {ssh_host}")
            
            # Получаем выделенные ресурсы из задачи
            gpus_allocated = task_data.get('gpus_allocated', {})
            gpu_limit = gpus_allocated.get('count') if gpus_allocated else 0
            
            # Формируем имя контейнера (без зависимости от username)
            task_id = task.get('id', int(time.time()))
            container_name = f"task_{task_id}"
            
            # Вычисляем Jupyter порт (на 1 больше SSH порта)
            jup_port = ssh_port + 1

            # Используем ContainerManager для создания контейнера
            container_id = self.container_manager.start(
                container_name=container_name,
                ssh_port=ssh_port,
                jup_port=jup_port,
                ssh_password=ssh_password,
                jupyter_token=ssh_password,  # Используем тот же пароль для Jupyter
                ssh_username=ssh_username,
                gpus=gpus_param,
                image=docker_image,
                cpuset_cpus=cpuset_cpus,
                memory_gb=memory_gb,
                memory_swap_gb=memory_gb,
                shm_size_gb=shm_size_gb,
                storage_gb=storage_gb
            )
            
            # Формируем результат
            result = {
                'container_id': container_id,
                'container_name': container_name,
                'ssh_port': ssh_port,
                'ssh_host': ssh_host,
                'ssh_command': container_info.get('ssh_command', f"ssh root@{ssh_host} -p {ssh_port}"),
                'ssh_username': ssh_username,
                'ssh_password': ssh_password,
                'status': 'running',
                'allocated_resources': {
                    'cpu_cpuset': cpuset_cpus,
                    'ram_gb': memory_gb,
                    'gpu_count': gpu_required,
                    'gpu_devices': gpus_param,
                    'storage_gb': storage_gb,
                    'gpu_support': bool(gpus_param)
                }
            }
            
            print(f"[INFO] Container created successfully:")
            print(f"  Container ID: {result['container_id']}")
            print(f"  Container Name: {result['container_name']}")
            print(f"  SSH Host: {result['ssh_host']}")
            print(f"  SSH Port: {result['ssh_port']}")
            print(f"  SSH Command: {result['ssh_command']}")
            print(f"  Allocated Resources: {result.get('allocated_resources', 'N/A')}")
            
            return result
                
        except Exception as e:
            print(f"[ERROR] Task processing failed: {e}")
            return None
    
    def initialize(self) -> bool:
        """Инициализирует агента"""
        print("[INFO] Initializing agent...")
        
        # Проверяем и устанавливаем Docker (только один раз при инициализации)
        print("[INFO] Checking Docker installation...")
        if not self.container_manager.check_and_install_docker():
            print("[ERROR] Docker is required but not available. Please install Docker and restart the script.")
            return False
        
        # Проверяем и исправляем права Docker (только один раз при инициализации)
        print("[INFO] Checking Docker permissions...")
        if not self.container_manager.fix_docker_permissions():
            print("[WARNING] Docker permissions could not be fixed automatically.")
            print("[WARNING] You may need to run: sudo usermod -aG docker $USER")
            print("[WARNING] Then log out and log back in, or restart the system.")
            print("[WARNING] Continuing anyway, but Docker operations may fail...")
        else:
            print("[INFO] Docker permissions are OK")
        
        # Проверяем поддержку GPU в Docker (только один раз при инициализации)
        print("[INFO] Checking Docker GPU support...")
        gpu_support = self.container_manager.check_docker_gpu_support()
        if not gpu_support:
            print("[WARNING] GPU support not available in Docker, containers will run without GPU access")
        else:
            print("[INFO] Docker GPU support confirmed")
        
        # Собираем данные о системе
        system_data = self.collect_system_data()
        print(json.dumps(system_data, indent=2, ensure_ascii=False))
        
        if not self.agent_id:
            # Первый запуск — делаем confirm
            print("[INFO] First run - confirming agent with server...")
            try:
                agent_id = self.api_client.confirm_agent(system_data)
                if agent_id:
                    self.agent_id = agent_id
                    self.api_client.set_credentials(agent_id, self.secret_key)
                    self._save_agent_id(agent_id)
                else:
                    print("[ERROR] Could not obtain agent_id from server. Exiting.")
                    return False
            except Exception as e:
                print(f"[ERROR] Failed to confirm agent: {e}")
                return False
        
        # Отправляем init данные
        print(f"[INFO] Sending init data to server for agent_id: {self.agent_id}")
        try:
            success = self.api_client.send_init_data(system_data)
            if success:
                print("[INFO] Init data sent successfully")
            else:
                print("[WARNING] Failed to send init data, but continuing...")
        except Exception as e:
            print(f"[ERROR] Failed to send init data: {e}")
            # Продолжаем работу даже если init не удался
        
        return True
    
    def run(self):
        """Запускает основной цикл агента"""
        print("[INFO] Starting agent...")
        
        # Инициализируем агента
        if not self.initialize():
            print("[ERROR] Agent initialization failed")
            return
        
        # Запускаем polling в отдельном потоке
        print("[INFO] Starting polling thread...")
        try:
            polling_thread = self.api_client.start_polling_thread(self.process_task)
            print("[INFO] Polling thread started successfully")
        except Exception as e:
            print(f"[ERROR] Failed to start polling thread: {e}")
            return
        
        print("[INFO] Agent initialization completed. Starting main loop...")
        
        # Основной цикл с периодической отправкой heartbeat
        heartbeat_counter = 0
        print("[INFO] Main loop started. Agent is running...")
        
        try:
            while True:
                time.sleep(60)
                heartbeat_counter += 1
                
                # Каждые 5 минут отправляем heartbeat
                if heartbeat_counter >= 5:
                    print("[INFO] Sending heartbeat...")
                    try:
                        monitoring_data = self.collect_monitoring_data()
                        self.api_client.send_heartbeat(monitoring_data)
                    except Exception as e:
                        print(f"[WARNING] Heartbeat failed: {e}")
                    heartbeat_counter = 0
                    
        except KeyboardInterrupt:
            print("[INFO] Received interrupt signal. Shutting down...")
        except Exception as e:
            print(f"[ERROR] Main loop error: {e}")
        finally:
            # Закрываем соединения
            self.api_client.close()
            print("[INFO] Agent shutdown completed")


def main():
    """Точка входа"""
    if len(sys.argv) < 2:
        print("Usage: python agent.py <secret_key>")
        sys.exit(1)
    
    secret_key = sys.argv[1]
    
    # Создаем и запускаем агента
    agent = Agent(secret_key)
    agent.run()


if __name__ == "__main__":
    main()

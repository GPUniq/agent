#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import re
import socket
import subprocess
import time
import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Settings:
    image: str = "jupyter-ssh-gpu:latest"
    name_prefix: str = "jsg"
    ssh_port_base: int = 42200   # SSH порт = 422XX
    jup_port_base: int = 42800   # Jupyter порт = 428XX
    shm_size: str = "1g"
    ulimit_stack: str = "67108864"  # 64 MiB
    runtime: str = "nvidia"  # --runtime=nvidia
    nvidia_caps: str = "compute,utility"


class ContainerManager:
    def __init__(self, settings: Settings = Settings()):
        self.s = settings

    def _run(self, args: List[str], check: bool = True, capture_output: bool = False, quiet: bool = False) -> subprocess.CompletedProcess:
        if not quiet:
            print("[RUN]", " ".join(args))
        return subprocess.run(args, check=check, capture_output=capture_output, text=True)

    def check_and_install_docker(self) -> bool:
        """Проверяет и устанавливает Docker если необходимо"""
        try:
            # Проверяем, работает ли Docker
            result = subprocess.run(['docker', 'ps'], check=True, capture_output=True)
            print("[INFO] Docker is working correctly")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[INFO] Docker not working, attempting to fix...")
            
            # Проверяем, установлен ли Docker
            try:
                subprocess.run(['docker', '--version'], check=True, capture_output=True)
                print("[INFO] Docker is installed but not working")
                
                # Исправляем права
                if self.fix_docker_permissions():
                    print("[INFO] Docker permissions fixed successfully")
                    return True
                else:
                    print("[WARNING] Could not fix Docker permissions")
                    return False
                    
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("[INFO] Docker not found, please install Docker manually")
                return False

    def fix_docker_permissions(self) -> bool:
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
            
            return False
            
        except Exception as e:
            print(f"[ERROR] Failed to fix Docker permissions: {e}")
            return False

    def check_docker_gpu_support(self) -> bool:
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
                    
                    # Проверяем --runtime=nvidia
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

    def run_docker_container_simple(self, task: dict) -> Optional[dict]:
        """Простая версия создания Docker контейнера с SSH для задач от API"""
        try:
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
            from hardware_analyzer import HardwareAnalyzer
            hardware_analyzer = HardwareAnalyzer()
            available_resources = hardware_analyzer.get_available_resources()
            
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
            
            # Собираем docker run команду
            cmd = [
                "docker", "run", "-d",
                "--name", container_name,
                "--ipc=host", "--ulimit", "memlock=-1", "--ulimit", "stack=67108864",
                "--shm-size", "1g",
                "-p", f"{ssh_port}:22",
                "--restart", "unless-stopped",
            ]
            
            # Добавляем GPU если есть (legacy режим)
            if gpu_limit > 0:
                cmd += [
                    "--runtime", "nvidia",
                    "-e", "NVIDIA_DRIVER_CAPABILITIES=compute,utility",
                    "-e", "NVIDIA_VISIBLE_DEVICES=all"
                ]
                print(f"[INFO] GPU access enabled for {gpu_limit} GPUs using legacy --runtime=nvidia")
            
            # Добавляем образ и команду запуска
            cmd += [
                docker_image,
                'bash', '-c',
                f"DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server sudo && "
                f"mkdir -p /var/run/sshd && "
                f"useradd -m -s /bin/bash {ssh_username} && "
                f"echo '{ssh_username}:{ssh_password}' | chpasswd && "
                f"usermod -aG sudo {ssh_username} && "
                f"sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config && "
                f"sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config && "
                f"/usr/sbin/sshd -D"
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
                cmd = ['sudo'] + cmd
            
            print(f"[INFO] Starting container with command: {' '.join(cmd)}")
            
            try:
                print(f"[INFO] Executing Docker command...")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode != 0:
                    print(f"[ERROR] Docker command failed with return code {result.returncode}")
                    print(f"[ERROR] Docker stderr: {result.stderr}")
                    print(f"[ERROR] Docker stdout: {result.stdout}")
                    return None
                else:
                    container_id = result.stdout.strip()
                    print(f"[INFO] Container started with ID: {container_id}")
                
                # Ожидаем готовности SSH
                print(f"[INFO] Waiting for SSH service to be ready on port {ssh_port}...")
                if self.wait_for_ssh_ready('localhost', ssh_port):
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
                
        except Exception as e:
            print(f"[ERROR] Container creation failed: {e}")
            return None

    def wait_for_ssh_ready(self, host: str, port: int, timeout: int = 60) -> bool:
        """Ждет, пока SSH сервис будет готов к подключению"""
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

    def _exists(self, name: str) -> bool:
        out = self._run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True).stdout.splitlines()
        return name in out

    def _running(self, name: str) -> bool:
        out = self._run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True).stdout.splitlines()
        return name in out

    def _docker_images_has(self, image: str) -> bool:
        cp = self._run(["docker", "image", "inspect", image], check=False, capture_output=True, quiet=True)
        if cp.returncode == 0:
            print(f"[OK]   Образ найден: {image}")
            return True
        else:
            print(f"[ERR]  Образ не найден: {image}")
            return False


    def _container_name(self, xx: str) -> str:
        return f"{self.s.name_prefix}-{xx}"

    def _ports_from_xx(self, xx: str) -> tuple[int, int]:
        pid = int(xx)
        return self.s.ssh_port_base + pid, self.s.jup_port_base + pid

    def _port_free(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                return False
        return True

    def _assert_ports_free(self, ssh_port: int, jup_port: int) -> None:
        bad = []
        if not self._port_free(ssh_port):
            bad.append(str(ssh_port))
        if not self._port_free(jup_port):
            bad.append(str(jup_port))
        if bad:
            raise RuntimeError(f"Порты заняты: {', '.join(bad)}")

    def start(self, xx: str, gpus: Optional[str] = None) -> None:
        """
        Запустить/создать контейнер jsg-XX.
        - SSH порт:    422XX
        - Jupyter порт:428XX
        - Пароли (SSH и Jupyter token): XX
        - GPU: все (по умолчанию) или список '0,2,3'
        """
        if not re.fullmatch(r"\d\d", xx):
            raise ValueError("XX должно быть двумя цифрами (00–99). Пример: '07', '11'.")

        name = self._container_name(xx)
        ssh_port, jup_port = self._ports_from_xx(xx)

        if self._running(name):
            print(f"[INFO] Контейнер уже запущен: {name}")
            print(f"[INFO] SSH:     ssh -p {ssh_port} dev@<host>  (пароль: {xx})")
            print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {xx})")
            return

        if self._exists(name):
            print(f"[INFO] Контейнер существует, стартуем: {name}")
            self._run(["docker", "start", name])
            print(f"[OK]   Запущено.")
            print(f"[INFO] SSH:     ssh -p {ssh_port} dev@<host>  (пароль: {xx})")
            print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {xx})")
            return

        self._assert_ports_free(ssh_port, jup_port)

        if not self._docker_images_has(self.s.image):
            raise RuntimeError(
                f"Образ '{self.s.image}' не найден локально. "
                f"Собери его или docker pull (если публичный)."
            )

        work_vol = f"{name}-work"
        self._run(["docker", "volume", "create", work_vol])

        # legacy GPU runtime 
        env = [
            "-e", f"SSH_PASSWORD={xx}",
            "-e", f"JUPYTER_TOKEN={xx}",
            "-e", f"NVIDIA_DRIVER_CAPABILITIES={self.s.nvidia_caps}",
            "-e", f"NVIDIA_VISIBLE_DEVICES={'all' if not gpus else gpus}",
        ]

        args = [
            "docker", "run", "-d",
            "--name", name,
            "--runtime", self.s.runtime,
            "--ipc=host", "--ulimit", "memlock=-1", "--ulimit", f"stack={self.s.ulimit_stack}",
            "--shm-size", self.s.shm_size,
            "-p", f"{ssh_port}:22",
            "-p", f"{jup_port}:8888",
            *env,
            "-v", f"{work_vol}:/work",
            "--restart", "unless-stopped",
            self.s.image
        ]
        self._run(args)

        print("[OK]   Контейнер создан и запущен.")
        print(f"[INFO] Name:    {name}")
        print(f"[INFO] SSH:     ssh -p {ssh_port} dev@<host>  (пароль: {xx})")
        print(f"[INFO] Jupyter: http://<host>:{jup_port}/lab (token:  {xx})")

    def stop(self, xx: Optional[str] = None) -> None:
        """
        Остановить и удалить:
            - все jsg-* (stop())
            - или один jsg-XX (stop('11'))
        """
        if xx is None:
            # Соберём все контейнеры по имени
            cp = self._run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True)
            names = [n for n in cp.stdout.splitlines() if n.startswith(self.s.name_prefix + "-")]
            if not names:
                print("[INFO] Нет контейнеров с префиксом", self.s.name_prefix + "-")
                return
            # Сначала остановим те, что запущены
            running = [n for n in names if self._running(n)]
            if running:
                self._run(["docker", "stop", *running])
            # Потом удалим все найденные
            self._run(["docker", "rm", *names])
            print(f"[OK]   Удалено контейнеров: {len(names)}")
        else:
            if not re.fullmatch(r"\d\d", xx):
                raise ValueError("XX должно быть двумя цифрами (00–99).")
            name = self._container_name(xx)
            # Остановим, если запущен
            if self._running(name):
                self._run(["docker", "stop", name])
            # Удалим, если существует
            if self._exists(name):
                self._run(["docker", "rm", name])
                print("[OK]   Контейнер удалён:", name)
            else:
                print("[INFO] Контейнер не найден:", name)


def _parse_cli() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("start", help="start jsg-XX container")
    sp.add_argument("xx", help="две цифры (00..99): порты SSH=422XX, Jupyter=428XX")
    sp.add_argument("gpus", nargs="?", default=None, help="список GPU, напр. '0,2,3'. По умолчанию: все(all)")

    sp2 = sub.add_parser("stop", help="stop and remove containers")
    sp2.add_argument("xx", nargs="?", default=None, help="две цифры (если не указано — все jsg-*)")

    return p.parse_args()


def main() -> None:
    args = _parse_cli()
    mgr = ContainerManager()

    if args.cmd == "start":
        mgr.start(args.xx, gpus=args.gpus)
    elif args.cmd == "stop":
        mgr.stop(args.xx)
    else:
        raise SystemExit("Unknown command")


if __name__ == "__main__":
    main()

"""
CLI:
    python container_manager.py start XX            # все GPU
    python container_manager.py start XX 1,2,3      # только указанные GPU
    python container_manager.py stop                # остановить и удалить ВСЕ jsg-*
    python container_manager.py stop XX             # остановить и удалить jsg-XX
Если предварительно прописать chmod +x container_manager.py, то можно запускать так:
    ./container_manager.py start XX ...

As a library:
    from container_manager import ContainerManager
    m = ContainerManager()
    m.start("11", gpus="0,2")
    m.stop("11")
"""

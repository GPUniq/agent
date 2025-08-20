#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import re
import socket
import subprocess
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

#!/usr/bin/env python3

import subprocess
import re
import os

def test_cpu_detection():
    print("=== Testing CPU Detection ===")
    
    # Test 1: lscpu
    print("\n1. Testing lscpu:")
    try:
        lscpu_output = subprocess.check_output(['lscpu']).decode()
        print(lscpu_output)
        
        sockets_match = re.search(r'Socket\(s\):\s+(\d+)', lscpu_output)
        sockets = int(sockets_match.group(1)) if sockets_match else 1
        print(f"Sockets from lscpu: {sockets}")
    except Exception as e:
        print(f"lscpu failed: {e}")
    
    # Test 2: /proc/cpuinfo
    print("\n2. Testing /proc/cpuinfo:")
    try:
        with open('/proc/cpuinfo') as f:
            cpuinfo_lines = f.read()
        
        # Count physical IDs
        physical_ids = set()
        for line in cpuinfo_lines.split('\n'):
            if line.startswith('physical id'):
                physical_id = line.split(':')[1].strip()
                physical_ids.add(physical_id)
        
        print(f"Physical IDs found: {physical_ids}")
        print(f"Number of physical IDs: {len(physical_ids)}")
    except Exception as e:
        print(f"/proc/cpuinfo failed: {e}")
    
    # Test 3: dmidecode
    print("\n3. Testing dmidecode:")
    try:
        dmidecode_output = subprocess.check_output(['dmidecode', '-t', 'processor'], stderr=subprocess.DEVNULL).decode(errors='ignore')
        socket_count = dmidecode_output.count('Socket Designation:')
        print(f"Socket Designation count: {socket_count}")
    except Exception as e:
        print(f"dmidecode failed: {e}")
    
    # Test 4: /sys/devices/system/cpu/
    print("\n4. Testing /sys/devices/system/cpu/:")
    try:
        cpu_dirs = [d for d in os.listdir('/sys/devices/system/cpu/') if d.startswith('cpu') and d[3:].isdigit()]
        print(f"CPU directories: {cpu_dirs[:10]}...")  # Show first 10
        
        topology_file = '/sys/devices/system/cpu/cpu0/topology/physical_package_id'
        if os.path.exists(topology_file):
            package_ids = set()
            for cpu_dir in cpu_dirs[:10]:  # Check first 10 CPUs
                try:
                    with open(f'/sys/devices/system/cpu/{cpu_dir}/topology/physical_package_id', 'r') as f:
                        package_id = f.read().strip()
                        package_ids.add(package_id)
                except:
                    continue
            print(f"Package IDs found: {package_ids}")
            print(f"Number of packages: {len(package_ids)}")
        else:
            print("Topology file not found")
    except Exception as e:
        print(f"/sys/devices/system/cpu/ failed: {e}")
    
    # Test 5: NUMA nodes
    print("\n5. Testing NUMA nodes:")
    try:
        numa_dirs = [d for d in os.listdir('/sys/devices/system/node/') if d.startswith('node') and d[4:].isdigit()]
        print(f"NUMA directories: {numa_dirs}")
        print(f"Number of NUMA nodes: {len(numa_dirs)}")
    except Exception as e:
        print(f"NUMA nodes failed: {e}")
    
    # Test 6: numactl
    print("\n6. Testing numactl:")
    try:
        numactl_output = subprocess.check_output(['numactl', '--hardware'], stderr=subprocess.DEVNULL).decode(errors='ignore')
        print(numactl_output)
    except Exception as e:
        print(f"numactl failed: {e}")

if __name__ == "__main__":
    test_cpu_detection()

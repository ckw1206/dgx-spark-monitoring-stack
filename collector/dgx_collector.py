#!/usr/bin/env python3
import os, re, socket, subprocess, time, csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("DGX_EXPORTER_PORT", "9273"))
INTERVAL = int(os.environ.get("COLLECT_INTERVAL", "10"))
_LATEST = "# dgx custom collector starting...\n"
_PREV_CPU = {"idle": None, "total": None}

def _parse_meminfo():
    total = avail = buffers = cached = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as fh:
            for line in fh:
                key, _, val = line.partition(":")
                num = re.search(r"[0-9]+", val)
                if not num: continue
                if key == "MemTotal": total = int(num.group(0)) * 1024
                elif key == "MemAvailable": avail = int(num.group(0)) * 1024
                elif key == "Buffers": buffers = int(num.group(0)) * 1024
                elif key == "Cached": cached = int(num.group(0)) * 1024
    except OSError: pass
    return total, avail, buffers + cached

def _read_cpu_total():
    idle = total = None
    try:
        with open("/proc/stat", "r", encoding="utf-8") as fh: first = fh.readline()
        if first.startswith("cpu "):
            vals = [int(v) for v in first.split()[1:10]]
            idle = vals[3] + vals[4]; total = sum(vals[:8])
    except (OSError, ValueError, IndexError): return None, None
    return idle, total

def _cpu_info():
    arch = "arm64"; count = 0; implementer = part = ""
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as fh:
            for line in fh:
                key, _, val = line.partition(":")
                key, val = key.strip(), val.strip()
                if key == "processor": count += 1
                elif key == "CPU implementer": implementer = val
                elif key == "CPU part": part = val
    except OSError: return 0, "unknown cpu", arch
    model = f"ARM implementer {implementer} part {part}".strip()
    if implementer.lower() == "0x41":
        model = {"0xd83": "NVIDIA Grace (Arm Neoverse V2)", "0xd49": "Arm Cortex-A72",
                 "0xd4d": "Arm Cortex-A73", "0xd40": "Arm Cortex-A53", "0xd0b": "Arm Cortex-A57"}.get(part.lower(), "ARM (Arm Neoverse)")
    return count, model, arch

def _load_average():
    try:
        with open("/proc/loadavg", "r", encoding="utf-8") as fh: fields = fh.read().split()
        return float(fields[0]), float(fields[1]), float(fields[2])
    except: return None, None, None

def _parse_nvidia_smi_table():
    procs = []; gpu_used = 0; util = mem_util = temp = power = None; app_count = 0
    try:
        out = subprocess.run(["nvidia-smi"], capture_output=True, text=True, check=False).stdout
    except OSError: return gpu_used, procs, util, mem_util, temp, power, app_count
    for line in out.splitlines():
        m = re.search(r"\|\s*N/A\s+(\d+)C\s+\S+\s+([\d.]+)W\s*/\s*\S+\s*\|", line)
        if m: temp = float(m.group(1)); power = float(m.group(2))
        m = re.search(r"Not Supported\s*\|\s+(\d+)%", line)
        if m: util = int(m.group(1)) / 100.0
        m = re.search(r"^\|\s+0\s+N/A\s+N/A\s+(\d+)\s+G\s+(.*?)\s+(\d+)(MiB|GiB)\s*\|\s*$", line)
        if m:
            amount = int(m.group(3)) * (1024 if m.group(4) == "GiB" else 1)
            proc_bytes = amount * 1024 * 1024
            gpu_used += proc_bytes
            procs.append((m.group(1), "G", m.group(2).strip(), proc_bytes))
    try:
        capps = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False).stdout
    except OSError: capps = ""
    for cid, cproc, cused in csv.reader([ln for ln in capps.splitlines() if ln.strip()]):
        try:
            pid = cid.strip(); name = cproc.strip(); proc_bytes = int(cused.strip()) * 1024 * 1024
        except ValueError: continue
        app_count += 1; gpu_used += proc_bytes; procs.append((pid, "C", name, proc_bytes))
    return gpu_used, procs, util, mem_util, temp, power, app_count

def _nvidia_driver():
    info = {"name": "NVIDIA", "driver": "unknown", "cuda": "unknown", "uuid": "unknown",
            "compute_mode": "unknown", "persistence_mode": "unknown", "pstate": "unknown",
            "pci_bus_id": "unknown", "vbios": "unknown", "compute_cap": "unknown", "host": "unknown"}
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,uuid,compute_mode,"
                              "persistence_mode,pstate,pci.bus_id,vbios_version,compute_cap",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, check=False).stdout
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 9:
            info.update({"name": parts[0], "driver": parts[1], "uuid": parts[2],
                         "compute_mode": parts[3], "persistence_mode": parts[4], "pstate": parts[5],
                         "pci_bus_id": parts[6], "vbios": parts[7], "compute_cap": parts[8]})
    except OSError: pass
    if info["driver"] in ("unknown", "", "[N/A]", "N/A"):
        if os.environ.get("DGX_DRIVER_VERSION", "").strip():
            info["driver"] = os.environ["DGX_DRIVER_VERSION"].strip()
    for cuda_src in ["/usr/local/cuda/version.json", "/usr/local/cuda/version.txt",
                     "/usr/local/cuda-12/version.json", "/usr/local/cuda-13/version.json"]:
        if not os.path.isfile(cuda_src): continue
        try:
            if cuda_src.endswith(".json"):
                import json as _json
                _cuda = _json.load(open(cuda_src, encoding="utf-8")).get("cuda", {}).get("version")
                if _cuda: info["cuda"] = ".".join(str(_cuda).split(".")[:2]); break
            else:
                _cuda = open(cuda_src, encoding="utf-8").read().strip()
                if _cuda: info["cuda"] = ".".join(str(_cuda).split(".")[:2]); break
        except: continue
    if info["cuda"] in ("unknown", "", "N/A"):
        if os.environ.get("DGX_CUDA_VERSION", "").strip():
            info["cuda"] = os.environ["DGX_CUDA_VERSION"].strip()
    hostname = os.environ.get("DGX_HOST_NAME", "").strip()
    if not hostname and os.path.isfile("/etc/hostname"):
        try: hostname = open("/etc/hostname", encoding="utf-8").read().strip()
        except OSError: hostname = ""
    info["host"] = hostname or socket.gethostname()
    return info

def collect():
    global _PREV_CPU
    total, avail, buffers_cached = _parse_meminfo()
    used = total - avail
    gpu_used, procs, util, mem_util, temp, power, app_count = _parse_nvidia_smi_table()
    info = _nvidia_driver()
    L = []; esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')

    def gauge(name, help_, value, labels=None):
        lbl = "{" + ",".join(f'{k}="{esc(v)}"' for k, v in labels.items()) + "}" if labels else ""
        L.extend([f"# HELP {name} {help_}", f"# TYPE {name} gauge", f"{name}{lbl} {value}"])

    gauge("dgx_unified_memory_total_bytes", "Total unified memory (host system RAM).", total)
    gauge("dgx_unified_memory_used_bytes", "Unified memory in active use.", used)
    gauge("dgx_unified_memory_available_bytes", "Unified memory available.", avail)
    gauge("dgx_unified_memory_gpu_used_bytes", "Unified memory held by GPU processes.", gpu_used)
    L.append("# HELP dgx_unified_memory_process_used_bytes Unified memory per GPU process.")
    L.append("# TYPE dgx_unified_memory_process_used_bytes gauge")
    for pid, ptype, name, pbytes in procs:
        L.append(f'dgx_unified_memory_process_used_bytes{{pid="{pid}",type="{ptype}",process_name="{esc(name)}"}} {pbytes}')
    def rat(ratio): return f"{ratio:.6f}" if ratio is not None else "nan"
    gauge("dgx_gpu_utilization_ratio", "GPU compute utilization ratio.", rat(util))
    if mem_util is not None: gauge("dgx_gpu_memory_controller_ratio", "Memory controller util ratio.", rat(mem_util))
    if temp is not None: gauge("dgx_gpu_temperature_celsius", "GPU temperature.", f"{temp:.1f}")
    if power is not None: gauge("dgx_gpu_power_draw_watts", "GPU power draw.", f"{power:.2f}")
    gauge("dgx_gpu_compute_apps", "Number of GPU compute processes.", app_count)
    gauge("dgx_gpu_info", "Static GPU info.", 1, {"name": info["name"], "driver": info["driver"],
        "cuda": info["cuda"], "uuid": info["uuid"][:8], "pci_bus_id": info["pci_bus_id"],
        "host": info["host"], "vbios": info["vbios"], "compute_cap": info["compute_cap"],
        "pstate": info["pstate"], "compute_mode": info["compute_mode"]})
    gauge("dgx_gpu_pstate", "GPU P-state.", 1, {"pstate": info["pstate"]})
    gauge("dgx_gpu_compute_mode", "GPU compute mode.", 1, {"mode": info["compute_mode"]})
    gauge("dgx_gpu_compute_mode_enabled", "1 if Exclusive_Process.", 1 if info["compute_mode"] == "Exclusive_Process" else 0)
    gauge("dgx_gpu_persistence_mode", "GPU persistence mode.", 1, {"mode": info["persistence_mode"]})
    gauge("dgx_gpu_persistence_mode_enabled", "1 if persistence enabled.",
          1 if info["persistence_mode"].lower().startswith("enabled") else 0)
    cpu_count, cpu_model, cpu_arch = _cpu_info()
    load1, load5, load15 = _load_average()
    idle, ctotal = _read_cpu_total()
    if idle is not None and ctotal is not None:
        p_idle, p_total = _PREV_CPU["idle"], _PREV_CPU["total"]
        if p_idle is not None and p_total is not None and ctotal > p_total:
            idle_delta = idle - p_idle; total_delta = ctotal - p_total
            if total_delta > 0:
                cpu_ratio = max(0.0, min(1.0, 1.0 - (idle_delta / total_delta)))
                gauge("dgx_cpu_usage_ratio", "Host CPU utilization ratio.", f"{cpu_ratio:.6f}")
        _PREV_CPU["idle"], _PREV_CPU["total"] = idle, ctotal
    gauge("dgx_cpu_count", "Logical CPU cores.", cpu_count)
    gauge("dgx_cpu_info", "Static CPU info.", 1, {"model": cpu_model, "arch": cpu_arch, "cores": str(cpu_count)})
    if load1 is not None:
        gauge("dgx_load_average_1m", "1-minute load average.", f"{load1:.2f}")
        gauge("dgx_load_average_5m", "5-minute load average.", f"{load5:.2f}")
        gauge("dgx_load_average_15m", "15-minute load average.", f"{load15:.2f}")
    gauge("dgx_memory_total_bytes", "Total host RAM.", total)
    gauge("dgx_memory_used_bytes", "Host RAM used.", used)
    gauge("dgx_memory_available_bytes", "Host RAM available.", avail)
    gauge("dgx_memory_buffers_cached_bytes", "Host RAM buffers + cached.", buffers_cached)
    gauge("dgx_collect_success", "Collection success.", 1)
    return "\n".join(L) + "\n"

def _loop():
    global _LATEST
    while True:
        try: _LATEST = collect()
        except Exception as exc:
            _LATEST = f"# HELP dgx_collect_success\n# TYPE dgx_collect_success gauge\ndgx_collect_success 0\n# error: {exc}\n"
        time.sleep(INTERVAL)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") in ("", "/metrics", "/metrics/"):
            body = _LATEST.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else: self.send_error(404)
    def log_message(self, *args): pass

def main():
    import threading
    threading.Thread(target=_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__": main()

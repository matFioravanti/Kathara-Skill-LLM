"""Isolated, checker-only infrastructure measurements. Never imports an AUT runner."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import threading
import time
import uuid

from .checker_runner import run_checker, isolate_checker_copy, CheckerCancelled
from .config import Config
from .run_identity import describe_run
from .workspace import tree_hash, manifest, copy_lab, write_json, utc_now


@dataclass
class Source:
    path: str
    original_id: str
    aut_sha256: str
    correction_sha256: str
    source_hash: str
    devices: int
    original_run_id: str | None = None


def parse_lab(path):
    from Kathara.parser.netkit.LabParser import LabParser
    lab = LabParser().parse(str(path))
    if not lab.machines:
        raise ValueError('laboratorio senza dispositivi')
    if any((path/name).exists() for name in ('lab.dep','lab.ext','lab.startup','lab.shutdown')):
        raise ValueError('dipendenze esterne o hook host richiedono verifica manuale di isolamento')
    for machine in lab.machines.values():
        if any(key in machine.meta for key in ('bridged', 'privileged', 'port')):
            raise ValueError('dispositivo con bridge/privilegi/porte host')
    if any(getattr(link, 'external', None) for link in lab.links.values()):
        raise ValueError('collision domain esterno')
    return lab


def select_sources(root, experiment, count):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', experiment):
        raise ValueError('experiment non valido')
    candidates, rejected = [], []
    for file in (root / 'runs' / experiment).glob('*/*/small/*/*/r*/manifest.json'):
        try:
            m = json.loads(file.read_text())
            run = file.parent
            if run.is_symlink() or not run.resolve().is_relative_to((root/'runs'/experiment).resolve()):
                raise ValueError('run simbolica o esterna all’esperimento')
            if m.get('task_level') != 'small' or m.get('experiment_id') != experiment:
                continue
            if m.get('aut_execution_success') is not True:
                raise ValueError('AUT non completato')
            if m.get('pipeline_state') in ('AUT_RUNNING', 'CHECKER_RUNNING', 'FINALIZING'):
                raise ValueError('osservazione ancora in esecuzione')
            entries = manifest(run / 'lab')
            if any(v['kind'] == 'link' for v in entries.values()):
                raise ValueError('link simbolici nel laboratorio')
            digest = tree_hash(run / 'lab')
            if digest != m.get('final_lab_sha256'):
                raise ValueError('hash finale AUT assente o alterato')
            correction = run / 'evaluation/correction.yaml'
            if correction.is_symlink():
                raise ValueError('snapshot correction simbolico')
            chash = hashlib.sha256(correction.read_bytes()).hexdigest()
            if chash != m.get('correction_sha256'):
                raise ValueError('snapshot correction assente o alterato')
            from .correction_input import validate_correction
            validate_correction(correction)
            lab = parse_lab(run / 'lab')
            source = Source(str(run.resolve()), describe_run(run), digest, chash, tree_hash(run), len(lab.machines), m.get('run_id'))
            candidates.append((m.get('started_at', ''), source))
        except Exception as exc:
            rejected.append({'path': str(file.parent), 'reason': str(exc)})
    candidates.sort(key=lambda item: (item[0], item[1].path), reverse=True)
    selected = [source for _, source in candidates[:count]]
    if len(selected) < count:
        raise ValueError(f'Servono {count} AUT utilizzabili; disponibili {len(selected)}. Esclusioni: {rejected}')
    return selected, rejected


def verify_sources(sources):
    for source in sources:
        if tree_hash(Path(source.path)) != source.source_hash:
            raise RuntimeError(f'Originale cambiato durante il test: {source.path}')


def prepare(source, directory, index):
    verify_sources([source])
    run = directory / f'lab_{index:03d}_{uuid.uuid4().hex[:12]}'
    run.mkdir(parents=True)
    (run / 'logs').mkdir()
    copy_lab(Path(source.path) / 'lab', run / 'lab')
    namespace = isolate_checker_copy(run / 'lab/lab.conf')
    lab = parse_lab(run / 'lab')
    correction = run / 'evaluation/correction.yaml'
    correction.parent.mkdir()
    shutil.copy2(Path(source.path) / 'evaluation/correction.yaml', correction)
    return {'instance_id': run.name, 'original_id': source.original_id, 'original_run_id':source.original_run_id, 'source': source.path,
            'directory': str(run), 'namespace': namespace, 'lab_hash': lab.hash,
            'devices': source.devices, 'prepared_hash': tree_hash(run / 'lab')}


def amount(text):
    match = re.fullmatch(r'\s*([\d.]+)\s*([KMGT]?i?B)\s*', text, re.I)
    if not match:
        raise ValueError(f'Memoria non interpretabile: {text}')
    unit = match[2].upper()
    power = 'BKMGT'.index(unit[0]) if unit != 'B' else 0
    return float(match[1]) * ((1024 if 'I' in unit else 1000) ** power)


def read_cli(args, timeout=15):
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or f'{args[0]} failed')
    return p.stdout.strip()


def host_sample():
    out = {}
    for name, args in {
        'memory_pressure_raw': ['memory_pressure', '-Q'],
        'pressure_level': ['sysctl', '-n', 'kern.memorystatus_vm_pressure_level'],
        'swap_raw': ['sysctl', '-n', 'vm.swapusage'],
        'vm_stat': ['vm_stat'],
        'top': ['top', '-l', '1', '-n', '0'],
    }.items():
        try:
            out[name] = read_cli(args)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            out[name] = None
    top = out.pop('top') or ''
    idle = re.search(r'([\d.]+)% idle', top)
    out['host_cpu_percent'] = 100 - float(idle[1]) if idle else None
    pressure = out.get('pressure_level')
    out['host_pressure_critical'] = pressure == '4' if pressure in ('1', '2', '4') else None
    swap = re.search(r'used\s*=\s*([\d.]+[MG])', out.get('swap_raw') or '')
    out['swap_used_bytes'] = amount(swap[1] + 'iB') if swap else None
    vm = out.get('vm_stat') or ''
    size = re.search(r'page size of (\d+) bytes', vm)
    free = re.search(r'Pages free:\s*(\d+)', vm)
    out['host_free_bytes'] = int(size[1]) * int(free[1]) if size and free else None
    # Do not confuse free pages with the OS's reclaimable/available memory.
    out['host_available_bytes'] = None
    return out


class DockerProbe:
    def __init__(self, timeout=30):
        import docker
        self.client = docker.from_env(timeout=timeout)
        self.api = self.client.api
        self.info = self.api.info()
        self.timeout = timeout
        if not self.info.get('ID') or read_cli(['docker','info','--format','{{.ID}}']) != self.info['ID']:
            raise RuntimeError('Docker SDK and CLI do not identify the same engine')
        self.baseline = {c['Id'] for c in self.api.containers(all=True)}
        self.baseline_networks = {n['Id'] for n in self.api.networks()}

    def configure_timeout(self, timeout):
        self.timeout = timeout
        self.api.timeout = timeout

    def inventory(self):
        return self.api.containers(all=True), self.api.networks()

    def conflicts(self, hashes):
        containers, networks = self.inventory()
        return [x['Id'] for x in containers + networks if (x.get('Labels') or {}).get('lab_hash') in hashes]

    def sample(self, instances):
        inventory_start=time.monotonic()
        containers, _ = self.inventory()
        inventory_seconds=time.monotonic()-inventory_start
        lookup = {x['lab_hash']: x for x in instances}
        owned = [c for c in containers if (c.get('Labels') or {}).get('lab_hash') in lookup]
        running = [c for c in owned if c['State'] == 'running']
        counts = {h: sum((c.get('Labels') or {}).get('lab_hash') == h for c in running) for h in lookup}
        full = sum(counts[h] == lookup[h]['devices'] for h in lookup)
        # Docker CLI reports usage, not the configured MemUsage denominator.
        stats_error = None
        stats_start=time.monotonic()
        try:
            stats = [json.loads(line) for line in read_cli(['docker', 'stats', '--no-stream', '--format', '{{json .}}'], timeout=self.timeout).splitlines() if line]
        except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as exc:
            stats = None
            stats_error = f'{type(exc).__name__}: {exc}'
        stats_seconds=time.monotonic()-stats_start
        usage = {s['ID']: s for s in (stats or [])}
        per_lab = {h: (0.0 if stats is not None else None) for h in lookup}
        for c in running:
            stat = next((s for ident, s in usage.items() if c['Id'].startswith(ident)), None)
            if stat and per_lab[c['Labels']['lab_hash']] is not None:
                per_lab[c['Labels']['lab_hash']] += amount(stat['MemUsage'].split('/')[0])
        ps = read_cli(['ps', '-axo', 'pid=,rss=,command='])
        processes = []
        for line in ps.splitlines():
            if '-m kathara_lab_checker' in line and any(x['directory'] + '/' in line for x in instances):
                pid, rss, _ = line.strip().split(None, 2)
                processes.append({'pid': int(pid), 'rss_bytes': int(rss) * 1024})
        return {'at': utc_now(), 'monotonic': time.monotonic(), 'containers': len(running),
                'all_docker_containers': sum(c['State'] == 'running' for c in containers),
                'active_labs': sum(n > 0 for n in counts.values()), 'fully_started_labs': full,
                'checker_processes': len(processes), 'process_resources': processes,
                'per_lab_containers': counts, 'per_lab_memory_bytes_sum': per_lab,
                'container_memory_bytes_sum': sum(amount(s['MemUsage'].split('/')[0]) for s in stats) if stats is not None else None,
                'docker_cpu_percent_sum': sum(float(s['CPUPerc'].rstrip('%')) for s in stats) if stats is not None else None,
                'stats_error': stats_error,
                'docker_api_timings': {'inventory_seconds': inventory_seconds, 'stats_seconds': stats_seconds},
                'docker_global_memory_bytes': None, 'docker_memory_limit_bytes': self.info.get('MemTotal'),
                'container_stats': stats, **host_sample()}

    def cleanup(self, hashes):
        containers, networks = self.inventory()
        for c in containers:
            labels = c.get('Labels') or {}
            if c['Id'] not in self.baseline and labels.get('app') == 'kathara' and labels.get('lab_hash') in hashes:
                self.api.remove_container(c['Id'], force=True, v=True)
        for n in networks:
            labels = n.get('Labels') or {}
            if n['Id'] not in self.baseline_networks and labels.get('app') == 'kathara' and labels.get('lab_hash') in hashes:
                self.api.remove_network(n['Id'])


def guard(sample, memory_fraction):
    if sample.get('host_pressure_critical') is True:
        return 'macOS memory pressure critical'
    limit = sample.get('docker_memory_limit_bytes')
    # Conservative proxy only. Exact VM memory is deliberately unavailable.
    used = sample.get('container_memory_bytes_sum')
    if limit and used is not None and used / limit >= memory_fraction:
        return 'container memory sum reached Docker memory budget (proxy, not exact VM RAM)'
    return None


def check_instance(instance, config, stop, barrier=None, tracker=None):
    row = {**instance, 'started_at': utc_now(), 'start_monotonic': time.monotonic(),
           'checker_status': 'INFRA_FAILED', 'task_success': None, 'error': None}
    timing_done, observed = threading.Event(), {}
    def observe_log():
        markers={'deployment':'Deploying network scenario...', 'verification':'Starting tests',
                 'undeployment':'Undeploying Network Scenario'}
        while not timing_done.is_set():
            try:
                text=(Path(instance['directory'])/'logs/checker_stderr.log').read_text(errors='replace')
                for name, marker in markers.items():
                    if name not in observed and marker in text: observed[name]=time.monotonic()
            except OSError:
                pass
            timing_done.wait(.1)
    timing_thread=threading.Thread(target=observe_log,daemon=True);timing_thread.start()
    try:
        if barrier:
            barrier.wait(timeout=60)
        if stop.is_set():
            raise CheckerCancelled('guard stopped before launch')
        kwargs = {'stop_event': stop}
        if tracker is not None:
            kwargs['process_callback'] = lambda action, pid: tracker.process(action, pid)
        result = run_checker(config, Path(instance['directory']),
                             Path(instance['directory']) / 'evaluation/correction.yaml', **kwargs)
        row.update(checker_status='COMPLETED', **result)
    except Exception as exc:
        row['error'] = f'{type(exc).__name__}: {exc}'
        if isinstance(exc, CheckerCancelled) or stop.is_set():
            row['checker_status'] = 'CANCELLED'
    finally:
        timing_done.set();timing_thread.join(timeout=1)
        row['verification_seconds_observed'] = (observed['undeployment']-observed['verification']
                                                if 'undeployment' in observed and 'verification' in observed else None)
        row['log_timing_resolution_seconds'] = .1
        row['finished_at'] = utc_now()
        row['total_seconds'] = time.monotonic() - row['start_monotonic']
        if tree_hash(Path(instance['directory']) / 'lab') != instance['prepared_hash']:
            row.update(checker_status='INFRA_FAILED', error='Stress copy modified by checker')
        write_json(Path(instance['directory']) / 'outcome.json', row)
    return row


def maximum(samples, key):
    return max((s[key] for s in samples if s.get(key) is not None), default=None)


class Tracker:
    def __init__(self):
        self.lock=threading.Lock(); self.pids=set(); self.peak=0; self.containers={}; self.peak_containers=0; self.peak_labs=0; self.started_labs=set()
    def process(self, action, pid):
        with self.lock:
            if action=='start': self.pids.add(pid)
            else: self.pids.discard(pid)
            self.peak=max(self.peak,len(self.pids))
    def event(self, action, container, lab):
        with self.lock:
            if action=='start': self.containers[container]=lab; self.started_labs.add(lab)
            elif action in ('die','destroy'): self.containers.pop(container,None)
            self.peak_containers=max(self.peak_containers,len(self.containers))
            self.peak_labs=max(self.peak_labs,len(set(self.containers.values())))
    def snapshot(self):
        with self.lock: return {'active_checker_pids':sorted(self.pids),'tracked_active_containers':len(self.containers),'tracked_active_labs':len(set(self.containers.values()))}


def summarize(rows, samples, seconds, workers):
    times = [r['total_seconds'] for r in rows if r['checker_status'] == 'COMPLETED']
    successful = len(times)
    return {'workers': workers, 'completed': successful, 'total_labs': len(rows),
            'infrastructure_failures': sum(r['checker_status'] == 'INFRA_FAILED' for r in rows),
            'functional_passes': sum(r.get('task_success') is True for r in rows),
            'total_seconds': seconds, 'throughput_labs_per_minute': successful * 60 / seconds if seconds else 0,
            'checker_seconds_median': statistics.median(times) if times else None,
            'checker_seconds_p95': sorted(times)[min(len(times)-1, int(len(times)*.95))] if times else None,
            'max_checker_processes': maximum(samples,'checker_processes'),
            'max_active_labs': maximum(samples,'active_labs'),
            'max_fully_started_labs': maximum(samples,'fully_started_labs'),
            'max_containers': maximum(samples,'containers'),
            'peak_container_memory_sum_bytes': maximum(samples,'container_memory_bytes_sum'),
            'peak_docker_cpu_percent_sum': maximum(samples,'docker_cpu_percent_sum'),
            'peak_docker_global_memory_bytes': None,
            'sampled_seconds_at_target': sum(max(0, b['monotonic']-a['monotonic']) for a,b in zip(samples,samples[1:])
                                            if min(a.get('fully_started_labs',0),b.get('fully_started_labs',0)) >= workers)}


def run_level(sources, directory, workers, options, probe):
    instances = [prepare(s, directory, i+1) for i,s in enumerate(sources)]
    hashes = {x['lab_hash'] for x in instances}
    if len(hashes) != len(instances) or probe.conflicts(hashes):
        raise RuntimeError('Namespace collision: no checker started')
    config = Config(directory, {'benchmark': {'timeout_seconds': options.timeout}, 'checker': {'no_cache': True}})
    stop, monitoring_done = threading.Event(), threading.Event()
    pause = threading.Event()
    rows, samples, events, reasons, monitor_errors = [], [], [], [], []
    tracker=Tracker()
    try:
        initial=probe.sample(instances); samples.append(initial)
        reason=guard(initial, options.memory_fraction)
        if reason: reasons.append(reason); stop.set()
    except Exception as exc:
        pause.set()
        monitor_errors.append({'kind':'docker_monitor_error','error':str(exc),'at':utc_now(),'origin':'initial_inventory','checker_state':tracker.snapshot()})
    stream = probe.api.events(decode=True, filters={'type': 'container'})
    streams=[stream]; event_lost=threading.Event(); last_event=[int(time.time())]
    def event_reader():
        nonlocal stream
        blind_since=None; retries=0
        while not monitoring_done.is_set():
          try:
            for event in stream:
                attrs = event.get('Actor', {}).get('Attributes', {})
                if event.get('timeNano'):
                    last_event[0]=max(last_event[0], int(event['timeNano']/1_000_000_000))
                if attrs.get('lab_hash') not in hashes:
                    continue
                events.append(event)
                action=event.get('Action'); container=event.get('id') or event.get('Actor',{}).get('ID')
                tracker.event(action,container,attrs.get('lab_hash'))
                with (directory / 'docker_events.log').open('a') as f:
                    f.write(json.dumps(event) + '\n')
                if action == 'oom':
                    reasons.append(f"Docker OOM confermato: container={container} timestamp={event.get('timeNano')}"); stop.set()
                elif action == 'die' and attrs.get('exitCode') not in (None, '0'):
                    monitor_errors.append({'kind':'nonzero_container_exit','container_id':container,'exit_code':attrs.get('exitCode'),'at':event.get('timeNano'),'during_stop':stop.is_set(),'origin':'docker_event'})
            if not monitoring_done.is_set(): raise RuntimeError('Docker event stream ended')
          except Exception as exc:
            if not monitoring_done.is_set():
                if blind_since is None: blind_since=time.monotonic()
                event_lost.set(); pause.set(); retries+=1
                monitor_errors.append({'kind':'event_stream_error','error':str(exc),'at':utc_now(),'origin':'docker_events','retry':retries,'checker_state':tracker.snapshot()})
                if retries>=getattr(options,'monitor_max_errors',3) and time.monotonic()-blind_since>=getattr(options,'monitor_max_blind_seconds',120):
                    reasons.append('Docker event visibility lost for too long'); stop.set(); return
                monitoring_done.wait(max(.1,getattr(options,'monitor_backoff',2)))
                if monitoring_done.is_set(): return
                try:
                    # Replay the boundary second to avoid losing an OOM during reconnect.
                    stream=probe.api.events(decode=True, filters={'type':'container'}, since=max(0,last_event[0]-1)); streams.append(stream)
                    event_lost.clear(); blind_since=None; retries=0
                except Exception as reconnect_error:
                    monitor_errors.append({'kind':'event_reconnect_error','error':str(reconnect_error),'at':utc_now(),'origin':'docker_events','retry':retries})
    def monitor():
        consecutive=0; blind_since=None; stats_blind_since=None
        while not monitoring_done.is_set():
            tick = time.monotonic()
            try:
                sample = probe.sample(instances); samples.append(sample)
                consecutive=0; blind_since=None
                if not event_lost.is_set(): pause.clear()
                sample['api_duration_seconds']=time.monotonic()-tick
                sample['tracker']=tracker.snapshot()
                if sample.get('stats_error'):
                    if stats_blind_since is None: stats_blind_since=time.monotonic()
                    monitor_errors.append({'kind':'stats_timeout_or_error','error':sample['stats_error'],'at':utc_now(),'api_duration_seconds':sample['api_duration_seconds'],'checker_state':tracker.snapshot(),'origin':'docker_stats'})
                    if time.monotonic()-stats_blind_since>=getattr(options,'monitor_max_blind_seconds',120):
                        reasons.append('Docker stats unavailable for too long; memory guard unobservable'); stop.set()
                else: stats_blind_since=None
                sample['memory_guard_bytes'] = (sample.get('docker_memory_limit_bytes') or 0)*options.memory_fraction
                with (directory / 'samples.jsonl').open('a') as f:
                    f.write(json.dumps(sample) + '\n')
                reason = guard(sample, options.memory_fraction)
                if reason:
                    reasons.append(reason); stop.set()
            except Exception as exc:
                consecutive+=1; pause.set()
                if blind_since is None: blind_since=time.monotonic()
                monitor_errors.append({'kind':'docker_monitor_error','error':f'{type(exc).__name__}: {exc}','at':utc_now(),'api_duration_seconds':time.monotonic()-tick,'retry':consecutive-1,'checker_state':tracker.snapshot(),'origin':'docker_inventory'})
                samples.append({'at':utc_now(),'monotonic':time.monotonic(),'checker_processes':None,'active_labs':None,'containers':None,'container_memory_bytes_sum':None,'docker_cpu_percent_sum':None,'monitor_error':str(exc),'tracker':tracker.snapshot()})
                if consecutive>=getattr(options,'monitor_max_errors',3) and time.monotonic()-blind_since>=getattr(options,'monitor_max_blind_seconds',120):
                    reasons.append(f'Docker visibility lost for too long: {exc}'); stop.set()
            delay = min(getattr(options,'monitor_backoff',2)*2**min(max(consecutive-1,0),getattr(options,'monitor_retries',2)), options.sample_interval) if consecutive else max(.1,options.sample_interval-(time.monotonic()-tick))
            monitoring_done.wait(max(.1,delay))
    threads = [threading.Thread(target=event_reader, daemon=True), threading.Thread(target=monitor, daemon=True)]
    for thread in threads: thread.start()
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=workers)
    pending, cursor, barriers = {}, 0, []
    try:
        while (cursor < len(instances) or pending) and not stop.is_set():
            if pause.is_set():
                monitoring_done.wait(.5)
                continue
            wave = min(workers - len(pending), len(instances) - cursor)
            sync = threading.Barrier(wave) if options.start_barrier and not pending and wave > 1 else None
            if sync: barriers.append(sync)
            for instance in instances[cursor:cursor+wave]:
                if stop.is_set(): break
                pending[pool.submit(check_instance, instance, config, stop, sync, tracker)] = instance
                cursor += 1
            done, _ = wait(pending, timeout=.5, return_when=FIRST_COMPLETED)
            for future in done:
                pending.pop(future)
                try: row = future.result()
                except Exception as exc: row = {'checker_status': 'INFRA_FAILED', 'error': str(exc), 'total_seconds': 0}
                rows.append(row)
                print(f"[{directory.name}] {len(rows)}/{len(sources)} {row.get('instance_id')} {row['checker_status']}", flush=True)
            if sum(r['checker_status']=='INFRA_FAILED' for r in rows) >= options.max_infra_errors:
                reasons.append('Repeated infrastructure failures'); stop.set()
    except KeyboardInterrupt:
        reasons.append('KeyboardInterrupt'); stop.set()
    finally:
        if stop.is_set():
            for sync in barriers: sync.abort()
            for future in pending: future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        for future in pending:
            if not future.cancelled():
                try: rows.append(future.result())
                except Exception as exc: rows.append({'checker_status':'INFRA_FAILED','error':str(exc),'total_seconds':0})
        monitoring_done.set()
        for open_stream in streams: open_stream.close()
        for thread in threads: thread.join(timeout=20)
        cleanup_error = None
        try:
            probe.cleanup(hashes)
            if probe.conflicts(hashes): raise RuntimeError('Stress resources remain after cleanup')
        except Exception as exc:
            cleanup_error = str(exc); reasons.append('Cleanup failed: '+str(exc))
        try:
            verify_sources(sources)
        except Exception as exc:
            reasons.append(f'Original integrity violation: {exc}'); stop.set()
    summary = summarize(rows, samples, time.monotonic()-started, workers)
    summary.update(max_checker_processes=max(tracker.peak,maximum(samples,'checker_processes') or 0),
                   max_active_labs=max(tracker.peak_labs,maximum(samples,'active_labs') or 0),
                   max_containers=max(tracker.peak_containers,maximum(samples,'containers') or 0),
                   labs_observed_started=len(tracker.started_labs), monitoring_errors=monitor_errors,
                   monitor_timeout_count=sum('timeout' in (e.get('error','').lower()) or 'timed out' in e.get('error','').lower() for e in monitor_errors),
                   monitor_retry_count=sum(e.get('kind') in ('docker_monitor_error','stats_timeout_or_error','event_stream_error','event_reconnect_error') for e in monitor_errors))
    for instance in instances:
        if not any(r.get('instance_id')==instance['instance_id'] for r in rows):
            rows.append({**instance,'checker_status':'NOT_STARTED','task_success':None,'total_seconds':0,
                         'error':'Stopped before launch'})
    summary['total_labs'] = len(instances)
    summary.update(stop_reasons=list(dict.fromkeys(reasons)), stopped=stop.is_set(), cleanup_error=cleanup_error)
    for row in rows:
        h = row.get('lab_hash')
        own_events = [e for e in events if e.get('Actor',{}).get('Attributes',{}).get('lab_hash')==h]
        created = [e['timeNano']/1e9 for e in own_events if e.get('Action')=='create' and 'timeNano'in e]
        launched = [e['timeNano']/1e9 for e in own_events if e.get('Action')=='start' and 'timeNano'in e]
        row['startup_seconds'] = max(launched)-min(created) if len(launched)>=row.get('devices',1) and created else None
        row['checker_seconds'] = row.get('total_seconds')
        row['peak_container_memory_sum_bytes'] = max((v for s in samples if (v:=s.get('per_lab_memory_bytes_sum',{}).get(h)) is not None),default=None)
    write_json(directory / 'summary.json', summary)
    return summary, rows, samples


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row)) or ['status']
    with path.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader()
        writer.writerows({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()} for row in rows)


def reports(output, summaries, rows, samples, dry_run=False):
    successful = [s for s in summaries if s['completed']==s['total_labs'] and not s['stopped'] and not s['cleanup_error']]
    sustained = [s for s in successful if (s['max_fully_started_labs'] or 0)>=s['workers'] and s['sampled_seconds_at_target']>=10]
    # Repeated full batches and multiple levels are required for a comparative recommendation.
    grouped = {}
    for s in summaries: grouped.setdefault(s['workers'], []).append(s)
    repeated = {w:v for w,v in grouped.items() if len(v)>=2 and all(x in sustained for x in v)}
    optimum = max(repeated, key=lambda w: statistics.mean(s['throughput_labs_per_minute'] for s in repeated[w])) if len(repeated)>=2 else None
    aggregates=[{'workers':w,'repetitions':len(v),
                 'mean_throughput':statistics.mean(s['throughput_labs_per_minute'] for s in v),
                 'stdev_throughput':statistics.stdev(s['throughput_labs_per_minute'] for s in v) if len(v)>1 else None,
                 'mean_batch_seconds':statistics.mean(s['total_seconds'] for s in v)} for w,v in sorted(grouped.items())]
    plateau=None
    for previous,current in zip(aggregates,aggregates[1:]):
        if previous['workers'] in repeated and current['workers'] in repeated and previous['mean_throughput']>0:
            if current['mean_throughput']/previous['mean_throughput']<=1.05:
                plateau=current['workers'];break
    summary = {'dry_run': dry_run, 'batches': summaries,
        'aggregates':aggregates,
        'max_sustained_concurrency_observed': max((s['workers'] for s in sustained),default=None),
        'best_observed_throughput_workers': max(successful,key=lambda s:s['throughput_labs_per_minute'])['workers'] if successful else None,
        'recommended_optimum_workers': optimum, 'performance_plateau': plateau,
        'recommendation_scope':'candidate among repeated, sustained tested levels only; not a universal optimum',
        'measurement_notes': ['Docker VM total used RAM unavailable; container memory sums are not exact global RAM.',
          'Memory guard uses all-container reported usage sum / Docker MemTotal as a conservative proxy.',
          'CPU container sums can exceed 100%; host CPU is reported separately.',
          'Concurrency peaks and sustained durations are sampled lower-bound estimates.',
          'No capacity or optimum conclusion is made from a dry-run or one batch.']}
    write_json(output/'summary.json', summary); write_csv(output/'laboratories.csv',rows); write_csv(output/'measurements.csv',samples)
    for name in ('docker_events.log','stress_test.log'): (output/name).touch(exist_ok=True)
    text = '# Kathara infrastructure stress test\n\n' + ('DRY-RUN: no containers started.\n\n' if dry_run else '')
    text += '\n'.join('- '+note for note in summary['measurement_notes'])+'\n\n'
    text += '| Workers | Completed | Fully active peak | Containers peak | Labs/min |\n|---:|---:|---:|---:|---:|\n'
    for s in summaries: text += f"| {s['workers']} | {s['completed']}/{s['total_labs']} | {s['max_fully_started_labs']} | {s['max_containers']} | {s['throughput_labs_per_minute']:.2f} |\n"
    text += '\n## Errori di monitoraggio e diagnostica\n\n'
    for s in summaries:
        text += f"- {s['workers']} worker: {s.get('monitor_timeout_count',0)} timeout, {s.get('monitor_retry_count',0)} tentativi di recupero.\n"
        for error in s.get('monitoring_errors',[]): text += f"  - `{json.dumps(error,ensure_ascii=False)}`\n"
        for reason in s.get('stop_reasons',[]): text += f"  - Arresto: {reason}\n"
    text += '\nSelected originals:\n'+''.join(f"- `{r['original_id']}` — `{r.get('source',r.get('path'))}`\n" for r in rows)
    (output/'report.md').write_text(text)
    if samples:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            t=[(s['monotonic']-samples[0]['monotonic'])/60 for s in samples]
            for key,label,scale in [('container_memory_bytes_sum','Container memory sum (GiB; not VM RAM)',1024**3),
                                     ('docker_cpu_percent_sum','Container CPU sum (%)',1),('containers','Stress containers',1),
                                     ('checker_processes','Actual checker processes',1)]:
                fig,ax=plt.subplots();ax.plot(t,[s[key]/scale if s.get(key) is not None else float('nan') for s in samples]);ax.set(xlabel='Elapsed minutes',ylabel=label)
                if key=='container_memory_bytes_sum' and samples[0].get('memory_guard_bytes'):
                    ax.axhline(samples[0]['memory_guard_bytes']/scale,color='red',linestyle='--',label='Memory budget guard (proxy)');ax.legend()
                fig.tight_layout();fig.savefig(output/(key+'.png'));plt.close(fig)
            for key,label in [('total_seconds','Batch duration (s)'),('throughput_labs_per_minute','Throughput (labs/min)')]:
                fig,ax=plt.subplots();ax.scatter([s['workers'] for s in summaries],[s[key] for s in summaries]);ax.set(xlabel='Configured workers',ylabel=label)
                fig.tight_layout();fig.savefig(output/(key+'.png'));plt.close(fig)
        except ImportError:
            pass

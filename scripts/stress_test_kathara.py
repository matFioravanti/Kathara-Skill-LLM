#!/usr/bin/env python3
"""Measure checker-only Kathara capacity on isolated copies of existing Small AUTs."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_core.kathara_stress import DockerProbe, select_sources, run_level, reports, verify_sources
from benchmark_core.workspace import write_json


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', default='thesis_final')
    p.add_argument('--task-level', choices=['small'], default='small')
    p.add_argument('--num-labs', type=int, default=15)
    p.add_argument('--workers', type=int, default=15)
    p.add_argument('--levels', help='e.g. 1,2,4,6,8,10,12,15')
    p.add_argument('--repetitions', type=int, default=1)
    modes=p.add_mutually_exclusive_group()
    modes.add_argument('--dry-run', action='store_true')
    modes.add_argument('--execute', action='store_true')
    p.add_argument('--sample-interval', type=float, default=5)
    p.add_argument('--timeout', type=int, default=900)
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--selection-file', type=Path, help='reuse an existing selection.json, verifying every original hash')
    p.add_argument('--memory-fraction', type=float, default=.85)
    p.add_argument('--max-infra-errors', type=int, default=2)
    p.add_argument('--docker-timeout', type=float, default=30)
    p.add_argument('--monitor-retries', type=int, default=2)
    p.add_argument('--monitor-backoff', type=float, default=2)
    p.add_argument('--monitor-max-errors', type=int, default=3)
    p.add_argument('--monitor-max-blind-seconds', type=float, default=120)
    p.add_argument('--start-barrier', action=argparse.BooleanOptionalAction, default=True)
    return p


def safe_output(path, root):
    path=path.resolve()
    protected=[root/name for name in ('runs','scenarios','prompt','skills','.git','benchmark_core','scripts','docs')]
    protected += [root/'results/general',root/'results/cost266']
    if path==root or any(path.is_relative_to(p) or p.is_relative_to(path) for p in protected):
        raise ValueError('output-dir overlaps protected benchmark paths')
    if path.exists():
        raise ValueError('output-dir must be new; existing reports are never overwritten')
    return path


def main(argv=None, *, root=ROOT, probe_factory=DockerProbe):
    args=parser().parse_args(argv)
    output=None; summaries=[]; rows=[]; samples=[]; sources=[]; lock=None
    try:
        levels=[int(n) for n in args.levels.split(',')] if args.levels else [args.workers]
        if (args.num_labs<1 or args.repetitions<1 or args.timeout<1 or args.sample_interval<=0 or
            args.max_infra_errors<1 or args.docker_timeout<=0 or args.monitor_retries<0 or
            args.monitor_backoff<0 or args.monitor_max_errors<1 or args.monitor_max_blind_seconds<=0 or not 0<args.memory_fraction<=1 or
            not levels or any(n<1 or n>15 or n>args.num_labs for n in levels)):
            raise ValueError('Positive counts required; workers 1..15 and <= num-labs; memory-fraction in (0,1]')
        if args.selection_file:
            from benchmark_core.kathara_stress import Source
            sources=[Source(**s) for s in json.loads(args.selection_file.read_text())['sources']]
            if len(sources)!=args.num_labs or any(not Path(s.path).resolve().is_relative_to(root/'runs'/args.experiment) for s in sources):
                raise ValueError('Selection count or original experiment path mismatch')
            verify_sources(sources);rejected=[]
        else:
            sources,rejected=select_sources(root,args.experiment,args.num_labs)
        # The live benchmark takes an exclusive lock at this exact location.
        # Hold a shared lock while executing to prevent original runs changing.
        if args.execute:
            lock_root=Path(tempfile.gettempdir())/'kathara-experiment-locks';lock_root.mkdir(exist_ok=True)
            key=hashlib.sha256(f'{root.resolve()}\0{args.experiment}'.encode()).hexdigest()
            lock=(lock_root/f'{key}.lock').open('a+')
            try: fcntl.flock(lock.fileno(),fcntl.LOCK_SH|fcntl.LOCK_NB)
            except BlockingIOError: raise ValueError('Original benchmark is running: no stress checker started')
            verify_sources(sources)
        from Kathara.setting.Setting import Setting
        from Kathara.types import SharedCollisionDomainsOption
        if Setting.get_instance().shared_cds != SharedCollisionDomainsOption.NOT_SHARED:
            raise ValueError('Kathara shared collision domains enabled: isolation cannot be guaranteed')
        if Setting.get_instance().hosthome_mount or Setting.get_instance().remote_url:
            raise ValueError('Kathara host-home mounts or remote engine enabled: isolation requires manual verification')
        probe=probe_factory(timeout=args.docker_timeout) if probe_factory is DockerProbe else probe_factory()
        if hasattr(probe, 'configure_timeout'):
            probe.configure_timeout(args.docker_timeout)
        containers,networks=probe.inventory()
        from Kathara.utils import generate_urlsafe_hash
        planned_namespaces=['ParallelChecker'+uuid.uuid4().hex[:24] for _ in sources]
        if probe.conflicts({generate_urlsafe_hash(name) for name in planned_namespaces}):
            raise ValueError('Dry-run namespace conflict: no containers started')
        stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:10]
        output=safe_output(args.output_dir or root/'results/stress_tests'/stamp,root)
        output.mkdir(parents=True)
        write_json(output/'selection.json',{'sources':[asdict(s) for s in sources],'excluded':rejected,
                   'planned_namespace_probes':planned_namespaces,'options':vars(args)|{'output_dir':str(output),'selection_file':str(args.selection_file) if args.selection_file else None},
                   'docker_engine':{key:probe.info.get(key) for key in ('ServerVersion','Architecture','NCPU','MemTotal')},
                   'implementation_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (ROOT/'scripts/stress_test_kathara.py',ROOT/'benchmark_core/kathara_stress.py',ROOT/'benchmark_core/checker_runner.py')},
                   'levels':levels,'repetitions':args.repetitions,'docker_memory_limit_bytes':probe.info.get('MemTotal'),
                   'existing_container_ids':[c['Id'] for c in containers],
                   'existing_network_ids':[n['Id'] for n in networks]})
        log=output/'stress_test.log'
        def message(text):
            print(text,flush=True)
            with log.open('a') as f:f.write(text+'\n')
        message(f"{'EXECUTE' if args.execute else 'DRY-RUN'} | {len(sources)} existing Small AUTs | levels={levels} | repetitions={args.repetitions}")
        message(f'Existing Docker containers={len(containers)}, networks={len(networks)}; namespaces allocated and checked before launch.')
        message('Docker VM RAM used: unavailable; memory safety uses container-usage SUM as labelled proxy, never memory limits.')
        for i,s in enumerate(sources,1):message(f'{i:02d}. {s.original_id} | {s.path}')
        message(f'Report: {output}')
        if not args.execute:
            rows=[{'original_id':s.original_id,'source':s.path,'checker_status':'NOT_STARTED','devices':s.devices} for s in sources]
            reports(output,[],rows,[],dry_run=True)
            verify_sources(sources)
            return 0
        for workers in levels:
            for repetition in range(1,args.repetitions+1):
                directory=output/f'workers_{workers:02d}_repeat_{repetition:03d}'
                directory.mkdir()
                message(f'Starting isolated level {workers}, repetition {repetition}')
                summary,batch,measurements=run_level(sources,directory,workers,args,probe)
                summary['repetition']=repetition
                summaries.append(summary)
                rows.extend({**row,'workers':workers,'repetition':repetition} for row in batch)
                samples.extend({**s,'workers':workers,'repetition':repetition} for s in measurements)
                with (output/'docker_events.log').open('a') as dst:
                    events=directory/'docker_events.log'
                    if events.exists():dst.write(events.read_text())
                message(json.dumps(summary))
                reports(output,summaries,rows,samples)
                if summary['stopped'] or summary['cleanup_error']:
                    return 1
        verify_sources(sources)
        return int(any(s['infrastructure_failures'] for s in summaries))
    except (Exception,KeyboardInterrupt) as exc:
        print(f'Stress test stopped: {type(exc).__name__}: {exc}',file=sys.stderr)
        if output:
            write_json(output/'failure.json',{'error':f'{type(exc).__name__}: {exc}'})
            reports(output,summaries,rows,samples,dry_run=not args.execute)
        return 1
    finally:
        if lock:lock.close()


if __name__=='__main__':
    raise SystemExit(main())

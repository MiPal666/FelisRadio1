#!/usr/bin/env python3
"""Observe Radio 1 HTTP delivery only; no Cast or audio playback; optional ICY request."""
import argparse
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
from time import monotonic, time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

URL='https://stream.rcs.revma.com/stk8hrvb938uv'
MARKER='FELIS_CURL_SUMMARY '


def redact_url(url):
    parts=urlsplit(url)
    query=[(key,'REDACTED' if any(term in key.lower() for term in ('tok','cookie','auth','sign','key')) else value)
           for key,value in parse_qsl(parts.query,keep_blank_values=True)]
    return urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),''))


def header_blocks(text):
    blocks=[]
    current=None
    for line in text.splitlines():
        if line.startswith(('HTTP/','ICY ')):
            current={'status':line,'headers':{}}
            blocks.append(current)
        elif current is not None and ':' in line:
            name,value=line.split(':',1)
            name=name.strip().lower();value=value.strip()
            if name in ('set-cookie','authorization','proxy-authorization'): value='REDACTED'
            elif name=='location': value=redact_url(value)
            current['headers'].setdefault(name,[]).append(value)
    return blocks


class TransferStats:
    def __init__(self,start):
        self.start=start;self.first=None;self.last=None
        self.total=0;self.interval_bytes=0;self.max_gap=0
    def add(self,now,count):
        if count<=0:return
        if self.first is None:self.first=now
        if self.last is not None:self.max_gap=max(self.max_gap,now-self.last)
        self.last=now;self.total+=count;self.interval_bytes+=count
    def sample(self,now):
        result={'elapsed_s':round(now-self.start,3),'bytes':self.interval_bytes,
                'total_bytes':self.total,'idle_for_s':round(now-(self.last if self.last is not None else self.start),3)}
        self.interval_bytes=0
        return result
    def result(self,now):
        return {'total_bytes':self.total,
                'first_data_s':round(self.first-self.start,3) if self.first is not None else None,
                'largest_gap_between_reads_s':round(self.max_gap,3),
                'final_idle_s':round(now-(self.last if self.last is not None else self.start),3)}


def curl_command(seconds,headers,icy=False):
    command = ['curl','--silent','--show-error','--no-buffer','--location',
            '--connect-timeout','8','--max-time',str(seconds),
            '--dump-header',str(headers),'--write-out','%{stderr}\n'+MARKER+'%{json}\n',URL]
    if icy:command[-1:-1]=['--header','Icy-MetaData: 1']
    return command


def main(argv=None):
    parser=argparse.ArgumentParser(description='45-second HTTP measurement of Radio 1, with optional ICY metadata request.')
    parser.add_argument('--seconds',type=int,default=45,choices=range(1,121),metavar='1..120')
    parser.add_argument('--icy',action='store_true',help='Add only the Icy-MetaData: 1 request header')
    args=parser.parse_args(argv)
    if not shutil.which('curl'):parser.error('curl is required')
    def report(phase,**fields):
        print(json.dumps(dict(phase=phase,timestamp_ms=int(time()*1000),**fields),ensure_ascii=False),flush=True)
    with tempfile.TemporaryDirectory(prefix='felisradio1-http-') as folder, tempfile.TemporaryFile() as errors:
        headers=Path(folder)/'headers.txt'
        start=monotonic();last_sample=start
        stats=TransferStats(start)
        report('request.begin',url=URL,duration_s=args.seconds,icy_metadata_requested=args.icy)
        process=subprocess.Popen(curl_command(args.seconds,headers,args.icy),stdout=subprocess.PIPE,stderr=errors,bufsize=0)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout,selectors.EVENT_READ)
                while selector.get_map():
                    for key,_ in selector.select(timeout=max(0,1-(monotonic()-last_sample))):
                        chunk=os.read(key.fd,65536)
                        now=monotonic()
                        if chunk:
                            first=stats.first is None
                            stats.add(now,len(chunk))
                            if first:report('data.first',elapsed_s=round(now-start,3),bytes=len(chunk))
                        else:selector.unregister(key.fileobj)
                    now=monotonic()
                    if now-last_sample>=1:
                        report('data.interval',**stats.sample(now));last_sample=now
            code=process.wait(timeout=2)
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:process.kill();process.wait()
        now=monotonic()
        report('data.interval',**stats.sample(now))
        for index,block in enumerate(header_blocks(headers.read_text(errors='replace') if headers.exists() else '')):
            report('http.response',index=index,**block)
        errors.seek(0)
        stderr=errors.read().decode(errors='replace')
        summary={}
        messages=[]
        for line in stderr.splitlines():
            if line.startswith(MARKER):
                try:summary=json.loads(line[len(MARKER):])
                except ValueError:messages.append('Invalid curl summary JSON')
            elif line.strip():messages.append(line.strip())
        wanted=('http_code','num_redirects','time_namelookup','time_connect','time_appconnect',
                'time_starttransfer','time_redirect','time_total','size_download','speed_download','http_version')
        report('curl.summary',**{key:summary.get(key) for key in wanted},
               url_effective=redact_url(summary.get('url_effective','')))
        expected_timeout=code==28 and stats.total>0 and now-start>=args.seconds-0.5
        outcome='observation_limit' if expected_timeout else 'eof' if code==0 else 'error'
        report('request.end',curl_exit_code=code,outcome=outcome,**stats.result(now),messages=messages)
        return 0 if code==0 or expected_timeout else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130)

#!/usr/bin/env python3
"""One finite audio-file experiment through the app's CastManager/CastController.

The diagnostic explicitly launches and verifies Default Media Receiver.
No production playback sources or receiver IDs are changed.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import sys
import tempfile
from threading import Event, Thread
from time import monotonic, time


def byte_range(value, size):
    if value is None:
        return 0, size-1, False
    if not value.startswith('bytes=') or ',' in value:
        raise ValueError('Unsupported range')
    left, right = value[6:].split('-', 1)
    if not left:
        length = int(right)
        if length <= 0: raise ValueError('Empty suffix')
        start, end = max(0,size-length), size-1
    else:
        start, end = int(left), min(int(right),size-1) if right else size-1
    if start < 0 or start >= size or end < start:
        raise ValueError('Unsatisfiable range')
    return start,end,True


class FileHTTP(BaseHTTPRequestHandler):
    media_path = None
    media_type = 'audio/mpeg'
    media_route = '/tone.mp3'
    ignore_range = False
    omit_content_length = False
    pacing_frames = None
    report = staticmethod(lambda *a,**k: None)
    def log_message(self,*args): pass
    def log_request(self,code='-',size='-'):
        self.report('http.access',method=getattr(self,'command',None),path=getattr(self,'path',None),status=code,
                    range=getattr(self,'headers',{}).get('Range'))
    def do_HEAD(self): self.serve(False)
    def do_GET(self): self.serve(True)
    def serve(self, body):
        if self.path != self.media_route:
            self.send_error(404)
            return
        size = self.media_path.stat().st_size
        requested = self.headers.get('Range')
        try:
            start,end,partial = byte_range(None if self.ignore_range else requested,size)
        except (ValueError,TypeError):
            self.send_response(416)
            self.send_header('Content-Range','bytes */'+str(size))
            self.send_header('Content-Length','0')
            self.end_headers()
            self.report('http.response',method=self.command,status=416,range=requested)
            return
        status = 206 if partial else 200
        self.report('http.request',method=self.command,range=requested,peer_port=getattr(self,'client_address',(None,None))[1])
        self.send_response(status)
        self.send_header('Content-Type',self.media_type)
        if not self.omit_content_length:
            self.send_header('Content-Length',str(end-start+1))
        else:
            # Keep the existing HTTP/1.0 response; EOF delimits the body.
            self.close_connection=True
        self.send_header('Accept-Ranges','none' if self.ignore_range else 'bytes')
        self.send_header('Access-Control-Allow-Origin','*')
        if partial: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        sent=0
        if body:
            try:
                if self.pacing_frames is not None:
                    from aac_pacing import send_frames
                    def progress(phase,**fields):
                        self.report(phase,peer_port=getattr(self,'client_address',(None,None))[1],**fields)
                    sent=send_frames(self.pacing_frames,self.wfile,progress)
                else:
                    with self.media_path.open('rb') as source:
                        source.seek(start)
                        remaining=end-start+1
                        while remaining:
                            data=source.read(min(65536,remaining))
                            if not data: break
                            self.wfile.write(data)
                            sent+=len(data)
                            remaining-=len(data)
            except (BrokenPipeError,ConnectionResetError):
                if self.pacing_frames is not None:sent=None  # Last completed write is in http.data.sent.
                self.report('http.client_closed',bytes=sent)
        self.report('http.response',method=self.command,status=status,bytes=sent)


class ProbeHTTPServer(ThreadingHTTPServer):
    report=staticmethod(lambda *a,**k:None)
    def shutdown_request(self,request):
        try:peer_port=request.getpeername()[1]
        except OSError:peer_port=None
        super().shutdown_request(request)
        self.report('http.connection.closed',peer_port=peer_port)


class PositionPreservingMedia:
    """Diagnostic wire adapter: preserve BUFFERED's currentTime=0 for LIVE too."""
    def __init__(self, raw, report, guard=None): self.raw=raw;self.report=report;self.guard=guard
    def __getattr__(self,name): return getattr(self.raw,name)
    def play_media(self,url,mime,**kwargs):
        if self.guard:self.guard.before_load()
        kwargs.setdefault('current_time',0)
        self.report('load.wire',url=url,mime=mime,stream_type=kwargs.get('stream_type'),
                    current_time=kwargs['current_time'],autoplay=kwargs.get('autoplay'),
                    title=kwargs.get('title'),metadata=kwargs.get('metadata'))
        return self.raw.play_media(url,mime,**kwargs)
    def stop(self,**kwargs):
        # Cleanup must not stop a different receiver that replaced our test.
        if self.guard:self.guard.require()
        return self.raw.stop(**kwargs)


def buffered_load(output, stream, song, position, paused, cancelled, stream_type='BUFFERED', ack_timeout=15):
    guard=getattr(output,'probe_receiver_guard',None)
    if guard:guard.prepare()
    # Same transport and ACK checks as CastManager._load; only file stream type differs.
    output.media_controller.play_media_at(stream[0],stream[1],position=max(0,position/1000),paused=paused,
        title=str(song.get('title') or ''),thumb=None,
        metadata={'metadataType':3,'artist':str(song.get('subtitle') or ''),'albumName':''},stream_type=stream_type)
    output.media_controller.block_until_active(timeout=ack_timeout,cancelled=cancelled)
    return output.media_controller.pending[2],output.media_controller.content_type


def main(argv=None):
    parser=argparse.ArgumentParser(description='Play a verified finite audio sample through FelisRadio1 Cast components, without an RPM.')
    parser.add_argument('--name',required=True,help='Exact Cast device name')
    parser.add_argument('--host',help='Notebook LAN IPv4 if automatic route detection is unsuitable')
    parser.add_argument('--port',type=int,default=8099)
    parser.add_argument('--aac-sample',action='store_true',help='Capture Radio 1 AAC for 15 s without ICY and test it as a finite file')
    parser.add_argument('--sample-file',type=Path,help='Save/reuse one verified AAC sample for both runs')
    parser.add_argument('--stream-type',choices=['BUFFERED','LIVE'],default='BUFFERED')
    parser.add_argument('--ignore-range',action='store_true',help='Ignore every Range header and serve the entire file as HTTP 200')
    parser.add_argument('--omit-content-length',action='store_true',help='Omit only Content-Length; end the HTTP/1.0 response by closing the connection')
    parser.add_argument('--pace-aac',action='store_true',help='Send whole ADTS frames at their audio rate, without changing headers or LOAD')
    args=parser.parse_args(argv)
    if args.pace_aac and not (args.aac_sample and args.sample_file and args.stream_type=='LIVE' and args.ignore_range and args.omit_content_length):
        parser.error('--pace-aac requires the existing AAC sample, LIVE, --ignore-range and --omit-content-length')
    if args.omit_content_length and not args.ignore_range:
        parser.error('--omit-content-length requires --ignore-range for this controlled test')
    if args.stream_type=='LIVE' and (not args.aac_sample or not args.sample_file or not args.sample_file.is_file()):
        parser.error('Run BUFFERED first with --aac-sample --sample-file, then reuse that file for LIVE')
    root=Path(__file__).resolve().parents[1]
    media=root/'tools/fixtures/cast-tone.mp3'
    if not args.aac_sample and not media.is_file(): parser.error('Missing tools/fixtures/cast-tone.mp3')
    started=monotonic()
    def report(phase,**fields):
        print(json.dumps(dict(phase=phase,timestamp_ms=int(time()*1000),
              elapsed_ms=round((monotonic()-started)*1000),**fields),ensure_ascii=False),flush=True)
    from install_vendor import install
    with tempfile.TemporaryDirectory(prefix='felisradio1-file-probe-') as folder:
        media_type='audio/mpeg'
        media_route='/tone.mp3'
        title='FelisRadio1 15-second test tone'
        if args.aac_sample:
            from capture_radio_aac import capture_aac
            if args.sample_file and args.sample_file.exists():
                from capture_radio_aac import complete_adts
                media=args.sample_file
                payload=media.read_bytes()
                complete, _=complete_adts(payload)
                if complete!=payload:raise ValueError('Saved AAC sample is not a complete ADTS sequence')
                report('sample.reused')
            else:
                media=capture_aac(folder,report)
                if args.sample_file:
                    with args.sample_file.open('xb') as output:output.write(media.read_bytes())
                    media=args.sample_file
                    report('sample.saved')
            report('sample.identity',sha256=hashlib.sha256(media.read_bytes()).hexdigest(),bytes=media.stat().st_size)
            media_type='audio/aac'
            media_route='/sample.aac'
            title='FelisRadio1 captured AAC file'
        pacing_frames=None
        if args.pace_aac:
            from aac_pacing import frame_plan
            pacing_frames=frame_plan(media.read_bytes())
            report('pacing.plan',frames=len(pacing_frames),bytes=sum(len(data) for data,_ in pacing_frames),
                   audio_duration_s=sum(duration for _,duration in pacing_frames),ack_timeout_s=40)
        install(root/'vendor/runtime.zip',folder)
        sys.path[:0]=[str(root/'python'),str(Path(folder)/'python')]
        from felisradio1.cast import CastManager
        from felisradio1.cast_transport import CastOutput
        from probe_receiver import ReceiverGuard
        guards=[]
        invalid_reasons=[]
        def invalidate(reason):
            invalid_reasons.append(reason)
            done.set()
        def output_factory(raw,fallback):
            output=CastOutput(raw,fallback)
            guard=ReceiverGuard(raw,report,invalidate)
            guards.append(guard)
            output.probe_receiver_guard=guard
            output.media_controller.controller=PositionPreservingMedia(output.media_controller.controller,report,guard)
            return output
        from felisradio1.cast_discovery import devices_snapshot
        class FileManager(CastManager):
            _load=staticmethod(lambda *load_args: buffered_load(*load_args,stream_type=args.stream_type,ack_timeout=40 if args.pace_aac else 15))
        found,done=Event(),Event()
        selected=[]
        failures=[]
        manager=None
        server=None
        selection_started=[None]
        first_playing=[False]
        def receive(event,data):
            if event=='cast_devices':
                matches=[row for row in data['items'] if row['name']==args.name]
                if matches:
                    selected[:]=matches
                    found.set()
                return
            report('cast.'+event,**data)
            if data.get('state')=='PLAYING' and not first_playing[0] and selection_started[0] is not None:
                first_playing[0]=True
                report('timing.first_playing',since_select_ms=round((monotonic()-selection_started[0])*1000))
            if event=='cast_candidate': manager.commit(data['request'],0,False,True,1)
            elif event=='output_selected':
                report('receiver',app_id=getattr(manager.output.cast.status,'app_id',None))
            elif event in ('output_error','cast_play_error','cast_lost'):
                failures.append(event)
                done.set()
            elif event=='cast_ended': done.set()
        url=['']
        manager=FileManager(receive,lambda *_:(url[0],media_type),None,stream_cache_seconds=0,output_factory=output_factory)
        try:
            report('discovery.begin')
            manager.refresh()
            if not found.wait(12) or len(selected)!=1:
                raise RuntimeError('Expected exactly one matching device')
            device_id=selected[0]['id']
            with manager.discovery.lock:
                info=next(info for info in devices_snapshot(manager.discovery.browser) if str(info.uuid)==device_id)
                destination=info.host
            host=args.host
            if not host:
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as route:
                    route.connect((destination,8009))
                    host=route.getsockname()[0]
            handler=type('ProbeHTTP',(FileHTTP,),{'media_path':media,'media_type':media_type,'media_route':media_route,'ignore_range':args.ignore_range,'omit_content_length':args.omit_content_length,'pacing_frames':pacing_frames,'report':staticmethod(report)})
            server=ProbeHTTPServer(('0.0.0.0',args.port),handler)
            server.report=report
            Thread(target=server.serve_forever,daemon=True).start()
            url[0]=f'http://{host}:{server.server_port}{media_route}'
            report('http.ready',url=url[0],bytes=media.stat().st_size,mime=media_type,ignore_range=args.ignore_range,omit_content_length=args.omit_content_length,paced=args.pace_aac)
            selection_started[0]=monotonic()
            report('select.requested')
            manager.select(device_id,{'videoId':'file-probe','title':title,'subtitle':'Diagnostic file'},1)
            if not done.wait(60):
                failures.append('observation.timeout')
                report('observation.timeout')
            report('receiver.final',status=manager.snapshot())
            for guard in guards:guard.finish()
            if not guards:invalid_reasons.append('receiver.not_created')
            report('experiment.done',valid=not invalid_reasons,invalid_reasons=invalid_reasons,failures=failures)
            return 1 if failures or invalid_reasons else 0
        finally:
            for guard in guards:guard.stopped.set()
            manager.close()
            # Keep HTTP alive until in-flight LOAD and its cleanup complete.
            manager.io.shutdown(wait=True)
            if server:
                server.shutdown()
                server.server_close()


if __name__=='__main__':
    try: raise SystemExit(main())
    except KeyboardInterrupt: raise SystemExit(130)
    except Exception as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr)
        raise SystemExit(1)

"""Mobile Cast coordinator. Discovery/prepare never block the QML event loop.

Desktop transport ACK/URL matching is retained in cast_transport. All receiver
commands are serialized; generations reject late loads/commands after Stop.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, RLock, Thread
from time import monotonic
import math
from .audio import PreparationCancelled
from .cast_discovery import CastDiscovery
from .cast_transport import CastOutput
from .cast_diagnostics import record, record_failure


class CastManager:
    def __init__(self, send, resolve, fallback, discovery_factory=CastDiscovery, output_factory=CastOutput, stream_cache_seconds=120, network_epoch=0, discovery_enabled=True):
        self.stream_cache_seconds=stream_cache_seconds
        self.send=send;self.resolve=resolve;self.fallback=fallback;self.output_factory=output_factory
        self.lock=RLock();self.io=ThreadPoolExecutor(max_workers=1,thread_name_prefix='felisradio1-cast')
        self.closed=Event();self.cancel=Event();self.revision=0;self.output=None;self.stage=None
        self.switch_request=None;self.media_request=-1;self.song={};self.url=None;self.mime='audio/mp4'
        self.device_id='';self.name='';self.finished=False;self.lost=False;self.cache={};self.last_status={};self.return_resume=False
        self._bridge_status=None;self._bridge_logged=0
        self.discovery_factory=discovery_factory;self.network_epoch=network_epoch
        self.discovery_enabled=discovery_enabled;self.discovery=None
        self._start_discovery()
        Thread(target=self._poll,name='felisradio1-cast-poll',daemon=True).start()

    @property
    def active(self):
        with self.lock:return self.output is not None

    def _emit(self, event, data):
        if self.closed.is_set():return
        fields = dict(event=event, request=data.get('request'), play_request=data.get('playRequest'),
                      revision=self.revision, active=data.get('active'), state=data.get('state'),
                      has_source=data.get('hasSource'), volume=data.get('volume'), muted=data.get('muted'))
        status_key = tuple(fields.values())
        logged = event != 'cast_status' or status_key != self._bridge_status or monotonic()-self._bridge_logged >= 5
        if logged:
            record('bridge.send', **fields)
            if event == 'cast_status':self._bridge_status=status_key;self._bridge_logged=monotonic()
        try:
            self.send(event,data)
            if logged:record('bridge.sent', event=event, request=data.get('request'))
        except Exception as error:
            record_failure('bridge.failed', error, event=event, request=data.get('request'))
            raise

    def _start_discovery(self):
        if not self.discovery_enabled:return
        epoch=self.network_epoch
        self.discovery=self.discovery_factory(
            lambda rows, scanning, error='':self._devices(rows,scanning,error,epoch))
        self.discovery.start()

    def _devices(self, rows, scanning, error='', epoch=None):
        with self.lock:
            if epoch is not None and (epoch!=self.network_epoch or not self.discovery_enabled):return
            self._emit('cast_devices',dict(items=rows,scanning=scanning,error=bool(error),networkEpoch=self.network_epoch))

    def network_changed(self, epoch, available):
        with self.lock:
            if self.closed.is_set() or epoch<=self.network_epoch:return
            self._new()
            self.network_epoch=epoch;self.discovery_enabled=bool(available)
            old_discovery=self.discovery;self.discovery=None
            stage=self.stage;self.stage=None;self.switch_request=None
            old=self.output
            if old is not None:self.lost=True
            self._emit('cast_devices',dict(items=[],scanning=False,error=False,networkEpoch=epoch))
            if old is not None:
                self._emit('cast_lost',dict(request=self.media_request,networkEpoch=epoch))
            if old_discovery is not None:old_discovery.close()
            self._start_discovery()
        if stage:self._thread(lambda:self._dispose(stage['output']))

    def _thread(self, fn):
        Thread(target=fn,name='felisradio1-cast-prepare',daemon=True).start()

    def _new(self):
        with self.lock:
            self.cancel.set();self.cancel=Event();self.revision+=1
            return self.revision,self.cancel

    def _current(self, revision, cancel):
        return not self.closed.is_set() and not cancel.is_set() and revision==self.revision

    def _stream(self, video_id, cancelled):
        with self.lock:cached=self.cache.get(video_id) if self.stream_cache_seconds > 0 else None
        if cached and cached[2]>monotonic():return cached[:2]
        result=self.resolve(video_id,cancelled)
        if cancelled():raise PreparationCancelled()
        if self.stream_cache_seconds <= 0:return result
        with self.lock:
            if len(self.cache)>4:self.cache.clear()
            self.cache[video_id]=(*result,monotonic()+self.stream_cache_seconds)
        return result

    def prefetch(self, video_id):
        if not video_id:return
        revision,cancel=self.revision,self.cancel
        def work():
            try:self._stream(video_id,lambda:not self._current(revision,cancel))
            except Exception:pass
        self._thread(work)

    def refresh(self):
        with self.lock:
            if self.discovery is not None:self.discovery.refresh()
            else:self._devices([],False)

    def _dispose(self, output, touched=False):
        if output is None:return
        stopped = True
        if touched:
            try:output.media_controller.stop()
            except Exception:stopped = False
        try:output.disconnect(timeout=1)
        except Exception:pass
        return stopped

    def select(self, device_id, song, request):
        revision,cancel=self._new()
        with self.lock:
            previous=self.stage;self.stage=None;self.switch_request=request
        if previous:self._thread(lambda:self._dispose(previous['output']))
        def work():
            target=None
            try:
                record('select.connect')
                with self.lock:discovery=self.discovery
                if discovery is None:raise RuntimeError('Cast discovery unavailable')
                raw=discovery.resolve(device_id)
                target=self.output_factory(raw,self.fallback)
                raw.wait(timeout=10)
                target.media_controller.check_connection()
                record('select.connected')
                record('stream.begin')
                stream=self._stream(song['videoId'],lambda:not self._current(revision,cancel)) if song.get('videoId') else None
                record('stream.ready')
                with self.lock:
                    if not self._current(revision,cancel):raise PreparationCancelled()
                    self.stage=dict(output=target,stream=stream,song=dict(song),device_id=device_id,
                                    name=str(raw.cast_info.friendly_name or 'Cast'),revision=revision,cancel=cancel,request=request)
                    target=None
                record('select.prepared')
                self._emit('cast_candidate',dict(request=request))
            except PreparationCancelled:pass
            except Exception as error:
                record_failure('select.failed', error)
                if self._current(revision,cancel):
                    with self.lock:self.switch_request=None
                    self._emit('output_error',dict(request=request,recovered=True))
            finally:self._dispose(target)
        self._thread(work)

    @staticmethod
    def _load(output, stream, song, position, paused, cancelled):
        output.media_controller.play_media_at(stream[0],stream[1],position=max(0,position/1000),paused=paused,
            title=str(song.get('title') or ''),thumb=str(song.get('thumbnail') or '') or None,
            metadata={'metadataType':3,'artist':str(song.get('subtitle') or ''),'albumName':str(song.get('album') or '')},stream_type='LIVE')
        output.media_controller.block_until_active(timeout=15,cancelled=cancelled)
        # Desktop may replace a rejected direct URL with its authenticated fallback.
        return (output.media_controller.pending[2], output.media_controller.content_type)

    def commit(self, request, position, paused, active, play_request):
        with self.lock:
            stage=self.stage
            if not stage or stage['request']!=request:return
            self.stage=None
            old=self.output;old_stream=(self.url,self.mime);old_song=dict(self.song)
        def work():
            target=stage['output'];touched=False;old_stopped=False
            record('handoff.begin')
            current=lambda:self._current(stage['revision'],stage['cancel'])
            try:
                if not current():raise PreparationCancelled()
                if old is not None and not self.lost:
                    old.media_controller.stop();old_stopped=True
                # Stop the group before launching a former member independently.
                if old is not None and old.cast_info.cast_type=='group' and target.cast_info.cast_type=='audio':
                    target.media_controller.start_receiver(cancelled=lambda:not current())
                if not current():raise PreparationCancelled()
                if active and stage['stream']:
                    touched=True
                    stage['stream']=self._load(target,stage['stream'],stage['song'],position,paused,lambda:not current())
                with self.lock:
                    if not current():raise PreparationCancelled()
                    self.output=target;target=None;self.song=stage['song'];self.device_id=stage['device_id'];self.name=stage['name']
                    self.url,self.mime=stage['stream'] or (None,'audio/mp4');self.media_request=play_request
                    self.finished=False;self.lost=False;self.switch_request=None
                self._dispose(old)
                record('handoff.confirmed')
                self._emit('output_selected',dict(request=request,deviceId=self.device_id,name=self.name,active=active,
                    state=str(self.output.media_controller.status.player_state) if active else 'IDLE',
                    volume=float(getattr(stage['output'].status,'volume_level',1) or 0),
                    muted=bool(getattr(stage['output'].status,'volume_muted',False)),
                    playRequest=play_request,position=position,paused=paused))
            except Exception as error:
                record_failure('handoff.failed', error, cancelled=not current())
                target_stopped=self._dispose(target,touched)
                target=None
                recovered=not old_stopped and target_stopped and not self.lost
                if current() and target_stopped and old_stopped and old_stream[0] and active:
                    try:
                        self._load(old,old_stream,old_song,position,paused,lambda:not current());recovered=True
                    except Exception:pass
                if current():
                    with self.lock:self.switch_request=None
                    self._emit('output_error',dict(request=request,recovered=recovered))
            finally:self._dispose(target,touched)
        self.io.submit(work)

    def play(self, song, request):
        revision,cancel=self._new()
        with self.lock:
            output=self.output;self.media_request=request;self.finished=False
        def prepare():
            try:
                if output is None or self.lost:raise RuntimeError('No output')
                record('stream.begin')
                stream=self._stream(song['videoId'],lambda:not self._current(revision,cancel))
                record('stream.ready')
                def load():
                    try:
                        if not self._current(revision,cancel):return
                        output.media_controller.stop()
                        loaded=self._load(output,stream,song,0,False,lambda:not self._current(revision,cancel))
                        if not self._current(revision,cancel):return
                        with self.lock:self.song=dict(song);self.url,self.mime=loaded;self.finished=False
                        self._emit('cast_play_ready',dict(request=request))
                    except Exception as error:
                        record_failure('play.failed', error, cancelled=not self._current(revision,cancel))
                        if self._current(revision,cancel):self._emit('cast_play_error',dict(request=request))
                self.io.submit(load)
            except Exception as error:
                record_failure('stream.failed', error, cancelled=not self._current(revision,cancel))
                if self._current(revision,cancel):self._emit('cast_play_error',dict(request=request))
        self._thread(prepare)

    def command(self, name, value=None):
        with self.lock:output=self.output;revision=self.revision;cancel=self.cancel
        if output is None:return
        def work():
            if not self._current(revision,cancel):return
            try:
                mc=output.media_controller
                if name=='play':mc.play()
                elif name=='pause':mc.pause()
                elif name=='seek' and isinstance(value,(int,float)) and math.isfinite(value):mc.seek(max(0,value)/1000)
                elif name=='volume' and isinstance(value,(int,float)) and math.isfinite(value):output.set_volume(min(1,max(0,value)))
                elif name=='mute':output.set_volume_muted(bool(value))
            except Exception:
                if self._current(revision,cancel):self._emit('cast_command_error',{})
        self.io.submit(work)

    def stop(self):
        revision,cancel=self._new()
        with self.lock:
            output=self.output;stage=self.stage;self.stage=None;request=self.switch_request;self.switch_request=None
            self.finished=True
        if request is not None:self._emit('output_cancelled',dict(request=request))
        if stage:self._thread(lambda:self._dispose(stage['output']))
        if output is not None and not self._output_lost(output):
            def work():
                if not self._current(revision,cancel) or self._output_lost(output):return
                try:
                    output.media_controller.stop()
                    if self._current(revision,cancel):self._emit('cast_stopped',{})
                except Exception as error:
                    record_failure('stop.failed',error)
                    if self._current(revision,cancel):self._emit('cast_command_error',{})
            self.io.submit(work)

    def snapshot(self):
        with self.lock:output=self.output;request=self.media_request;url=self.url;device_id=self.device_id;epoch=self.network_epoch
        if output is None:return None
        output.media_controller.check_connection()
        status=output.media_controller.status;receiver=output.status
        owned=bool(url) and getattr(status,'content_id',None)==url
        state=str(getattr(status,'player_state','IDLE')) if owned else 'IDLE'
        position=getattr(status,'adjusted_current_time',None)
        if not isinstance(position,(int,float)):position=getattr(status,'current_time',0) or 0
        return dict(request=request,deviceId=device_id,networkEpoch=epoch,state=state,
            position=max(0,int(position*1000)) if owned else 0,duration=max(0,int((getattr(status,'duration',0) or 0)*1000)) if owned else 0,
            volume=float(getattr(receiver,'volume_level',1) or 0),muted=bool(getattr(receiver,'volume_muted',False)),
            hasSource=owned and bool(getattr(status,'media_session_id',None)) and state in ('PLAYING','PAUSED','BUFFERING'),
            idleReason=getattr(status,'idle_reason',None),
            finished=state=='IDLE' and getattr(status,'idle_reason',None)=='FINISHED' and getattr(status,'content_id',None)==url)

    def _output_lost(self, output):
        latch=getattr(output,'connection_lost',None)
        return self.lost or (latch is not None and latch.is_set())

    def return_local(self, request):
        revision,cancel=self._new()
        with self.lock:
            old=self.output;stage=self.stage;self.stage=None
            unavailable=old is not None and self._output_lost(old)
        if stage:self._thread(lambda:self._dispose(stage['output']))

        def selected():
            with self.lock:
                if not self._current(revision,cancel):return
                self.output=None;self.device_id=self.name='';self.url=None;self.song={}
                self.media_request=-1;self.lost=False;self.last_status={};self.switch_request=None
                self._emit('local_selected',dict(request=request))
            # Detach never sends STOP; disposal must not hold up local playback.
            self._thread(lambda:self._dispose(old))

        if unavailable:
            record('local.unavailable.detach')
            selected()  # Do not queue behind commands waiting for the lost network.
            return

        def work():
            try:
                if not self._current(revision,cancel):return
                if old is not None:
                    if not self._output_lost(old):old.media_controller.stop()
                selected()
            except Exception as error:
                # Loss can be detected while STOP is in flight. A healthy
                # receiver rejecting STOP still retains the old behavior.
                if self._current(revision,cancel) and self._output_lost(old):selected()
                elif self._current(revision,cancel):
                    record_failure('local.failed',error)
                    self._emit('output_error',dict(request=request,recovered=False))
        self.io.submit(work)

    def _poll(self):
        while not self.closed.wait(.5):
            if not self.active or self.lost:continue
            with self.lock:expected_output=self.output;expected_request=self.media_request
            try:
                status=self.snapshot()
                with self.lock:
                    if status is None or self.output is not expected_output or self.lost:continue
                    self.last_status=status
                    self._emit('cast_status',status)
                    if status['finished'] and not self.finished:
                        self.finished=True;self._emit('cast_ended',dict(request=status['request']))
            except Exception:
                with self.lock:
                    if self.output is not expected_output:continue
                    self.lost=True
                    self._emit('cast_lost',dict(request=expected_request,networkEpoch=self.network_epoch))

    def close(self):
        if self.closed.is_set():return
        self.closed.set();self.cancel.set()
        if self.discovery is not None:self.discovery.close()
        with self.lock:
            old=self.output;stage=self.stage;self.output=None;self.stage=None;self.cache.clear()
        # Cleanup follows any in-flight load: stopping before its late ACK can
        # otherwise leave a receiver playing after the app has gone away.
        self.io.submit(lambda:self._dispose(old,True))
        if stage:self._thread(lambda:self._dispose(stage['output']))
        self.io.shutdown(wait=False)

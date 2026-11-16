"""Capture AAC without ICY; retain complete original ADTS frames without remuxing."""
import json
from pathlib import Path
import shutil
import subprocess
from probe_radio_http import URL, header_blocks


def adts_frame_size(data, offset):
    if offset+7>len(data): return None
    if data[offset]!=255 or data[offset+1]&0xf6!=0xf0: return None
    if (data[offset+2]>>2)&15>=13: return None
    size=((data[offset+3]&3)<<11)|(data[offset+4]<<3)|(data[offset+5]>>5)
    minimum=7 if data[offset+1]&1 else 9
    return size if size>=minimum else None


def complete_adts(data):
    # A live connection can start/end in the middle of a frame. Keep the
    # original bytes of consecutive complete frames, never re-encode/remux.
    for start in range(min(len(data),65536)):
        size=adts_frame_size(data,start)
        if size and start+size<len(data) and adts_frame_size(data,start+size): break
    else: raise ValueError('No consecutive AAC ADTS frames found')
    end=start;count=0
    while end<len(data):
        size=adts_frame_size(data,end)
        if size is None:
            if len(data)-end<7:break
            raise ValueError('Unexpected data between AAC ADTS frames')
        if end+size>len(data):break
        end+=size;count+=1
    if count<2: raise ValueError('Insufficient complete AAC frames')
    return data[start:end],dict(frames=count,leading_bytes_removed=start,trailing_bytes_removed=len(data)-end)


def capture_aac(folder, report, run=subprocess.run):
    for binary in ('curl','ffprobe','ffmpeg'):
        if not shutil.which(binary):raise RuntimeError('Missing command: '+binary)
    folder=Path(folder)
    raw=folder/'radio1-capture.raw'
    headers=folder/'radio1-capture.headers'
    sample=folder/'radio1-sample.aac'
    report('capture.begin',duration_s=15,icy_metadata_requested=False)
    result=run(['curl','--silent','--show-error','--location','--connect-timeout','8',
        '--max-time','15','--dump-header',str(headers),'--output',str(raw),URL],capture_output=True,text=True)
    if result.returncode not in (0,28) or not raw.is_file() or raw.stat().st_size==0:
        raise RuntimeError('AAC capture failed; curl exit '+str(result.returncode))
    blocks=header_blocks(headers.read_text(errors='replace'))
    if not blocks or ' 200 ' not in blocks[-1]['status']:
        raise ValueError('AAC capture did not receive HTTP 200')
    response=blocks[-1]['headers']
    if response.get('content-type',[''])[0].split(';',1)[0].strip().lower()!='audio/aac':
        raise ValueError('Captured response is not audio/aac')
    if 'icy-metaint' in response:raise ValueError('Unexpected ICY blocks in no-ICY capture')
    payload,trim=complete_adts(raw.read_bytes())
    sample.write_bytes(payload)
    probe=run(['ffprobe','-v','error','-show_entries','format=duration,size:stream=codec_name,profile,sample_rate,channels',
        '-of','json',str(sample)],capture_output=True,text=True,check=True)
    info=json.loads(probe.stdout)
    if not info.get('streams') or any(s.get('codec_name')!='aac' for s in info['streams']):
        raise ValueError('ffprobe did not confirm AAC')
    decode=run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-i',str(sample),'-f','null','-'],
        capture_output=True,text=True)
    if decode.returncode or decode.stderr.strip():raise ValueError('Captured AAC did not decode cleanly')
    report('capture.verified',bytes=len(payload),**trim,probe=info)
    return sample

"""Pace intact ADTS frames using their core sample rate and raw-block count."""
from time import monotonic, sleep
from capture_radio_aac import adts_frame_size

SAMPLE_RATES=(96000,88200,64000,48000,44100,32000,24000,22050,16000,12000,11025,8000,7350)


def frame_plan(data):
    frames=[];offset=0
    while offset<len(data):
        size=adts_frame_size(data,offset)
        if size is None or offset+size>len(data):raise ValueError('Incomplete ADTS sample for pacing')
        rate=SAMPLE_RATES[(data[offset+2]>>2)&15]
        blocks=1+(data[offset+6]&3)
        duration=1024*blocks/rate
        frames.append((data[offset:offset+size],duration))
        offset+=size
    if not frames:raise ValueError('Empty ADTS sample')
    return frames


def send_frames(frames,writer,report,clock=monotonic,wait=sleep):
    started=clock();audio_time=0;sent=0
    for number,(data,duration) in enumerate(frames,1):
        delay=started+audio_time-clock()
        if delay>0:wait(delay)
        writer.write(data)
        writer.flush()
        sent+=len(data)
        report('http.data.sent',frame=number,bytes=len(data),total_bytes=sent,
               audio_offset_s=round(audio_time,6),send_elapsed_s=round(clock()-started,6))
        audio_time+=duration
    delay=started+audio_time-clock()
    if delay>0:wait(delay)
    report('http.body.complete',bytes=sent,audio_duration_s=round(audio_time,6),
           send_elapsed_s=round(clock()-started,6))
    return sent

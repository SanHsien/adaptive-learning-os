"""Opt-in real Whisper MP4/WebM smoke using locally synthesized speech."""
import json
import subprocess
import tempfile
from pathlib import Path

import av

from local_server import ROOT, launch_worker, stop_process_tree
from real_whisper_resource_smoke import long_audio, validate_timeline
from transcribe_local import SAMPLE_RATE, decode_bounded


def main():
    interpreter = ROOT / '.venv' / 'Scripts' / 'python.exe'
    with tempfile.TemporaryDirectory(prefix='adaptive-video-smoke-') as folder:
        directory = Path(folder)
        audio = directory / 'speech.m4a'
        long_audio(audio, 30)
        for suffix, video_codec, audio_codec in (
            ('mp4', 'mpeg4', 'aac'), ('webm', 'libvpx', 'libopus')
        ):
            source = directory / f'synthetic.{suffix}'
            target = directory / f'{suffix}.srt'
            subprocess.run(
                ['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                 'color=c=blue:s=64x64:r=10:d=30', '-i', str(audio),
                 '-c:v', video_codec, '-c:a', audio_codec, '-shortest', str(source)],
                check=True, timeout=60, capture_output=True)
            with av.open(str(source)) as container:
                assert len(container.streams.video) == 1
                assert sum(1 for _ in container.decode(video=0)) == 300
            samples = len(decode_bounded(source))
            assert abs(samples - 30 * SAMPLE_RATE) <= SAMPLE_RATE // 10
            process = launch_worker(
                [str(interpreter), str(ROOT / 'tools' / 'transcribe_local.py'),
                 str(source), '--output', str(target), '--model', 'small'])
            try:
                _, error = process.communicate(timeout=180)
                assert process.returncode == 0, repr(error[-400:])
                cues, end = validate_timeline(target, 30)
            finally:
                stop_process_tree(process)
                process.communicate(timeout=15)
            print(json.dumps({'format': suffix, 'samples': samples,
                              'cues': cues, 'last_cue_seconds': end}), flush=True)


if __name__ == '__main__':
    main()

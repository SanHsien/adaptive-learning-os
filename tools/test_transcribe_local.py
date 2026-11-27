import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import patch

from transcribe_local import TranscriptionLimitError, render_srt, timestamp, transcribe


class TranscriptionTests(unittest.TestCase):
    def test_timestamp_and_format(self):
        self.assertEqual(timestamp(61.25), '00:01:01,250')
        self.assertEqual(render_srt([SimpleNamespace(start=0, end=1.2, text=' 測試 語音 ')]),
                         '1\n00:00:00,000 --> 00:00:01,200\n測試 語音\n')

    def test_empty_and_invalid_segments_rejected(self):
        with self.assertRaises(ValueError):
            render_srt([SimpleNamespace(start=0, end=1, text=' ')])
        with self.assertRaises(ValueError):
            render_srt([SimpleNamespace(start=2, end=1, text='測試')])

    def test_srt_limit_stops_consuming_segments(self):
        def segments():
            yield SimpleNamespace(start=0, end=1, text='a' * 60000)
            yield SimpleNamespace(start=1, end=2, text='b' * 60000)
            self.fail('Consumed segments after limit')
        with self.assertRaises(TranscriptionLimitError):
            render_srt(segments())

    def test_bounded_decode_real_wav(self):
        import importlib.util
        import wave
        if not importlib.util.find_spec('av') or not importlib.util.find_spec('numpy'):
            self.skipTest('Optional PyAV and NumPy dependencies')
        from transcribe_local import decode_bounded
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.wav'
            with wave.open(str(path), 'wb') as wav:
                wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\x00\x00' * 32000)
            self.assertEqual(len(decode_bounded(path, max_seconds=2)), 32000)
            with self.assertRaises(TranscriptionLimitError):
                decode_bounded(path, max_seconds=1)

    def test_bounded_decode_compressed_audio(self):
        import importlib.util
        if not importlib.util.find_spec('av') or not importlib.util.find_spec('numpy'):
            self.skipTest('Optional PyAV and NumPy dependencies')
        import av
        import numpy as np
        from transcribe_local import decode_bounded
        formats = [('mp3', 'mp3'), ('m4a', 'aac'), ('mp4', 'aac'), ('webm', 'libopus')]
        with tempfile.TemporaryDirectory() as folder:
            for suffix, codec in formats:
                with self.subTest(format=suffix):
                    path = Path(folder) / f'synthetic.{suffix}'
                    with av.open(str(path), 'w') as container:
                        stream = container.add_stream(codec, rate=48000)
                        stream.layout = 'mono'
                        for _ in range(20):
                            frame = av.AudioFrame.from_ndarray(
                                np.zeros((1, 4800), dtype=np.int16), format='s16', layout='mono')
                            frame.sample_rate = 48000
                            for packet in stream.encode(frame):
                                container.mux(packet)
                        for packet in stream.encode(None):
                            container.mux(packet)
                    audio = decode_bounded(path, max_seconds=3)
                    self.assertGreaterEqual(len(audio), 30000)
                    self.assertLess(len(audio), 48000)
                    with self.assertRaises(TranscriptionLimitError):
                        decode_bounded(path, max_seconds=1)

    def test_actual_hour_decode_boundary(self):
        import importlib.util
        if not importlib.util.find_spec('av') or not importlib.util.find_spec('numpy'):
            self.skipTest('Optional PyAV and NumPy dependencies')
        import av
        import numpy as np
        from transcribe_local import decode_bounded, MAX_BYTES, MAX_AUDIO_SECONDS, SAMPLE_RATE
        with tempfile.TemporaryDirectory() as folder:
            for seconds in (MAX_AUDIO_SECONDS, MAX_AUDIO_SECONDS + 1):
                with self.subTest(seconds=seconds):
                    path = Path(folder) / f'boundary-{seconds}.m4a'
                    with av.open(str(path), 'w') as container:
                        stream = container.add_stream('alac', rate=SAMPLE_RATE)
                        stream.layout = 'mono'
                        for _ in range(seconds):
                            frame = av.AudioFrame.from_ndarray(
                                np.zeros((1, SAMPLE_RATE), dtype=np.int16), format='s16', layout='mono')
                            frame.sample_rate = SAMPLE_RATE
                            for packet in stream.encode(frame):
                                container.mux(packet)
                        for packet in stream.encode(None):
                            container.mux(packet)
                    self.assertLessEqual(path.stat().st_size, MAX_BYTES)
                    if seconds == MAX_AUDIO_SECONDS:
                        self.assertEqual(len(decode_bounded(path)), seconds * SAMPLE_RATE)
                    else:
                        with self.assertRaises(TranscriptionLimitError):
                            decode_bounded(path)
                    path.unlink()

    def test_video_with_multiple_audio_tracks(self):
        import importlib.util
        if not importlib.util.find_spec('av') or not importlib.util.find_spec('numpy'):
            self.skipTest('Optional PyAV and NumPy dependencies')
        import av
        import numpy as np
        from transcribe_local import decode_bounded
        with tempfile.TemporaryDirectory() as folder:
            for suffix, video_codec, audio_codec in [('mp4', 'mpeg4', 'aac'), ('webm', 'libvpx', 'libopus')]:
                with self.subTest(format=suffix):
                    path = Path(folder) / f'video.{suffix}'
                    with av.open(str(path), 'w') as container:
                        video = container.add_stream(video_codec, rate=10)
                        video.width = video.height = 64
                        video.pix_fmt = 'yuv420p'
                        tracks = [container.add_stream(audio_codec, rate=48000) for _ in range(2)]
                        for track in tracks:
                            track.layout = 'mono'
                        for index in range(20):
                            frame = av.VideoFrame.from_ndarray(
                                np.full((64, 64, 3), index * 10, dtype=np.uint8), format='rgb24')
                            for packet in video.encode(frame):
                                container.mux(packet)
                            for track, amplitude in zip(tracks, (0, 12000)):
                                frame = av.AudioFrame.from_ndarray(
                                    np.full((1, 4800), amplitude, dtype=np.int16), format='s16', layout='mono')
                                frame.sample_rate = 48000
                                for packet in track.encode(frame):
                                    container.mux(packet)
                        for stream in [video, *tracks]:
                            for packet in stream.encode(None):
                                container.mux(packet)
                    with av.open(str(path)) as container:
                        self.assertEqual(len(container.streams.audio), 2)
                        self.assertEqual(sum(1 for _ in container.decode(video=0)), 20)
                    audio = decode_bounded(path, max_seconds=3)
                    self.assertGreaterEqual(len(audio), 30000)
                    self.assertLess(len(audio), 48000)
                    self.assertLess(float(np.max(np.abs(audio))), 0.001)
                    with av.open(str(path)) as container:
                        peak = max(float(np.max(np.abs(frame.to_ndarray())))
                                   for frame in container.decode(audio=1))
                        self.assertGreater(peak, 0.1)
                    with self.assertRaises(TranscriptionLimitError):
                        decode_bounded(path, max_seconds=1)

    def test_invalid_media_does_not_create_subtitles(self):
        import importlib.util
        if not importlib.util.find_spec('av') or not importlib.util.find_spec('numpy'):
            self.skipTest('Optional PyAV and NumPy dependencies')
        import av
        import numpy as np
        from unittest.mock import Mock
        fake_module = ModuleType('faster_whisper')
        fake_module.WhisperModel = Mock()
        with tempfile.TemporaryDirectory() as folder:
            video_path = Path(folder) / 'silent.mp4'
            with av.open(str(video_path), 'w') as container:
                video = container.add_stream('mpeg4', rate=10)
                video.width = video.height = 64
                video.pix_fmt = 'yuv420p'
                frame = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format='rgb24')
                for packet in video.encode(frame):
                    container.mux(packet)
                for packet in video.encode(None):
                    container.mux(packet)
            corrupt = Path(folder) / 'corrupt.mp4'
            corrupt.write_bytes(b'not a media container')
            with patch.dict(sys.modules, {'faster_whisper': fake_module}):
                for source in (video_path, corrupt):
                    with self.subTest(source=source.name):
                        dest = source.with_suffix('.srt')
                        with self.assertRaises((IndexError, ValueError, av.FFmpegError)):
                            transcribe(source, dest)
                        self.assertFalse(dest.exists())
                dest = Path(folder) / 'limited.srt'
                with patch('transcribe_local.decode_bounded', side_effect=TranscriptionLimitError('limit')):
                    with self.assertRaises(TranscriptionLimitError):
                        transcribe(video_path, dest)
                self.assertFalse(dest.exists())
                fake_module.WhisperModel.assert_not_called()

    def test_input_validation_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'lesson.mp3'
            source.write_bytes(b'ID3')
            dest = Path(folder) / 'lesson.srt'
            dest.write_text('existing', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                transcribe(source, dest)
            self.assertEqual(dest.read_text(encoding='utf-8'), 'existing')
            with self.assertRaises(ValueError):
                transcribe(source, Path(folder) / 'lesson.txt')

    def test_model_result_writes_only_explicit_srt(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'lesson.wav'
            source.write_bytes(b'RIFF0000WAVE')
            dest = Path(folder) / 'lesson.srt'
            fake_module = ModuleType('faster_whisper')

            class FakeWhisper:
                def __init__(self, *_args, **_kwargs):
                    pass

                def transcribe(self, *_args, **_kwargs):
                    return iter([SimpleNamespace(start=0, end=1, text='合成語音')]), None

            fake_module.WhisperModel = FakeWhisper
            with patch.dict(sys.modules, {'faster_whisper': fake_module}), patch('transcribe_local.decode_bounded', return_value=object()):
                self.assertEqual(transcribe(source, dest), dest.resolve())
            self.assertIn('合成語音', dest.read_text(encoding='utf-8'))
            self.assertEqual(source.read_bytes(), b'RIFF0000WAVE')


if __name__ == '__main__':
    unittest.main()

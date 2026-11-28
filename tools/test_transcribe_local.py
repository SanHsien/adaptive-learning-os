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

    def test_iso_box_sizes(self):
        import io
        from transcribe_local import validate_iso_boxes
        for data in (b'\x00\x00\x00\x08free',
                     b'\x00\x00\x00\x01free' + (16).to_bytes(8, 'big'),
                     b'\x00\x00\x00\x00mdatpayload'):
            validate_iso_boxes(io.BytesIO(data))
        for data in (b'123', b'\x00\x00\x00\x01free',
                     b'\x00\x00\x00\x01free' + (0).to_bytes(8, 'big'),
                     b'\x00\x00\x00\x09free', b'\x00\x00\x00\x08uuid'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                validate_iso_boxes(io.BytesIO(data))

    def test_truncated_faststart_media_rejected_before_model(self):
        import importlib.util
        if not importlib.util.find_spec('av') or not importlib.util.find_spec('numpy'):
            self.skipTest('Optional PyAV and NumPy dependencies')
        import av
        import numpy as np
        from unittest.mock import Mock
        from transcribe_local import decode_bounded
        fake_module = ModuleType('faster_whisper')
        fake_module.WhisperModel = Mock()
        with tempfile.TemporaryDirectory() as folder:
            for suffix in ('m4a', 'mp4'):
                with self.subTest(format=suffix):
                    source = Path(folder) / f'synthetic.{suffix}'
                    with av.open(str(source), 'w', options={'movflags': 'faststart'}) as container:
                        stream = container.add_stream('aac', rate=48000)
                        stream.layout = 'mono'
                        for index in range(20):
                            frame = av.AudioFrame.from_ndarray(
                                np.full((1, 4800), index * 100, dtype=np.int16), format='s16', layout='mono')
                            frame.sample_rate = 48000
                            for packet in stream.encode(frame):
                                container.mux(packet)
                        for packet in stream.encode(None):
                            container.mux(packet)
                    self.assertGreaterEqual(len(decode_bounded(source)), 30000)
                    with av.open(str(source)) as container:
                        ends = [packet.pos + packet.size for packet in container.demux(container.streams.audio[0]) if packet.size]
                    source.write_bytes(source.read_bytes()[:ends[10]])
                    dest = source.with_suffix('.srt')
                    with patch.dict(sys.modules, {'faster_whisper': fake_module}):
                        with self.assertRaisesRegex(ValueError, 'MP4/M4A.*截斷'):
                            transcribe(source, dest)
                    self.assertFalse(dest.exists())
        fake_module.WhisperModel.assert_not_called()

    def test_webm_declared_segment_truncation(self):
        import importlib.util
        if not importlib.util.find_spec('av') or not importlib.util.find_spec('numpy'):
            self.skipTest('Optional PyAV and NumPy dependencies')
        import av
        import numpy as np
        from unittest.mock import Mock
        from transcribe_local import decode_bounded
        fake_module = ModuleType('faster_whisper')
        fake_module.WhisperModel = Mock()
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'synthetic.webm'
            with av.open(str(source), 'w') as container:
                stream = container.add_stream('libopus', rate=48000)
                stream.layout = 'mono'
                for index in range(20):
                    frame = av.AudioFrame.from_ndarray(
                        np.full((1, 4800), index * 100, dtype=np.int16), format='s16', layout='mono')
                    frame.sample_rate = 48000
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode(None):
                    container.mux(packet)
            self.assertGreaterEqual(len(decode_bounded(source)), 30000)
            source.write_bytes(source.read_bytes()[:source.stat().st_size // 2])
            dest = source.with_suffix('.srt')
            with patch.dict(sys.modules, {'faster_whisper': fake_module}):
                with self.assertRaisesRegex(ValueError, 'WebM.*截斷'):
                    transcribe(source, dest)
            self.assertFalse(dest.exists())
        fake_module.WhisperModel.assert_not_called()

    def test_webm_unknown_segment_size(self):
        import io
        from transcribe_local import validate_webm_bounds
        validate_webm_bounds(io.BytesIO(bytes.fromhex('1a45dfa38018538067ff')))
        with self.assertRaises(ValueError):
            validate_webm_bounds(io.BytesIO(bytes.fromhex('1a45dfa381')))

    def test_mp3_declared_byte_count(self):
        import importlib.util
        if not importlib.util.find_spec('av') or not importlib.util.find_spec('numpy'):
            self.skipTest('Optional PyAV and NumPy dependencies')
        import av
        import numpy as np
        from unittest.mock import Mock
        from transcribe_local import decode_bounded
        fake_module = ModuleType('faster_whisper')
        fake_module.WhisperModel = Mock()
        with tempfile.TemporaryDirectory() as folder:
            for options in ({}, {'id3v2_version': '0'}, {'write_xing': '0'}):
                with self.subTest(options=options):
                    source = Path(folder) / 'synthetic.mp3'
                    with av.open(str(source), 'w', options=options) as container:
                        stream = container.add_stream('mp3', rate=48000)
                        stream.layout = 'mono'
                        for index in range(20):
                            frame = av.AudioFrame.from_ndarray(
                                np.full((1, 4800), index * 100, dtype=np.int16), format='s16', layout='mono')
                            frame.sample_rate = 48000
                            for packet in stream.encode(frame):
                                container.mux(packet)
                        for packet in stream.encode(None):
                            container.mux(packet)
                    self.assertGreaterEqual(len(decode_bounded(source)), 30000)
                    if options.get('write_xing') == '0':
                        continue
                    with av.open(str(source)) as container:
                        ends = [packet.pos + packet.size for packet in container.demux(container.streams.audio[0]) if packet.size]
                    source.write_bytes(source.read_bytes()[:ends[10]])
                    dest = source.with_suffix('.srt')
                    with patch.dict(sys.modules, {'faster_whisper': fake_module}):
                        with self.assertRaisesRegex(ValueError, 'MP3.*截斷'):
                            transcribe(source, dest)
                    self.assertFalse(dest.exists())
        fake_module.WhisperModel.assert_not_called()

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
            import wave
            truncated = Path(folder) / 'truncated.wav'
            with wave.open(str(truncated), 'wb') as wav:
                wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                wav.writeframes(b'\x00\x00' * 32000)
            original_wav = truncated.read_bytes()
            truncated.write_bytes(original_wav[:32044])
            aligned = Path(folder) / 'aligned-truncation.wav'
            aligned.write_bytes(original_wav[:44 + 4096])
            with av.open(str(aligned)) as container:
                packets = list(container.demux(container.streams.audio[0]))
                self.assertFalse(any(packet.is_corrupt for packet in packets))
            with patch.dict(sys.modules, {'faster_whisper': fake_module}):
                with self.assertRaisesRegex(ValueError, 'WAV.*截斷'):
                    transcribe(aligned, aligned.with_suffix('.srt'))
                self.assertFalse(aligned.with_suffix('.srt').exists())
                for source in (video_path, corrupt, truncated):
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


    def test_chunked_inference_offsets_and_bounds(self):
        from transcribe_local import transcribe_segments

        class FakeModel:
            def __init__(self):
                self.chunks = []

            def transcribe(self, chunk, **kwargs):
                self.chunks.append(list(chunk))
                return iter([SimpleNamespace(start=0, end=0.5, text='speech')]), None

        model = FakeModel()
        with patch('transcribe_local.SAMPLE_RATE', 2), patch('transcribe_local.INFERENCE_CHUNK_SECONDS', 2):
            segments = list(transcribe_segments(model, list(range(9)), 'zh'))
        self.assertEqual(model.chunks, [[0, 1, 2, 3], [4, 5, 6, 7], [8]])
        self.assertEqual([(s.start, s.end) for s in segments], [(0, .5), (2, 2.5), (4, 4.5)])

    def test_chunk_boundary_and_overlapping_model_cues(self):
        from transcribe_local import transcribe_segments

        class FakeModel:
            def transcribe(self, chunk, **kwargs):
                return iter([
                    SimpleNamespace(start=0, end=1, text='first'),
                    SimpleNamespace(start=.9, end=2.1, text='second'),
                ]), None

        with patch('transcribe_local.SAMPLE_RATE', 2), patch('transcribe_local.INFERENCE_CHUNK_SECONDS', 2):
            segments = list(transcribe_segments(FakeModel(), [0] * 8, 'zh'))
        self.assertEqual([(s.start, s.end) for s in segments],
                         [(0, 1), (1, 2), (2, 3), (3, 4)])
        self.assertEqual(render_srt(segments).count('-->'), 4)

    def test_srt_rejects_overlap_and_submillisecond_cues(self):
        for segments in (
            [SimpleNamespace(start=0, end=1, text='a'),
             SimpleNamespace(start=.9, end=2, text='b')],
            [SimpleNamespace(start=0, end=.0001, text='a')],
        ):
            with self.subTest(segments=segments), self.assertRaises(ValueError):
                render_srt(segments)

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
            with patch.dict(sys.modules, {'faster_whisper': fake_module}), patch('transcribe_local.decode_bounded', return_value=[0] * 16000):
                self.assertEqual(transcribe(source, dest), dest.resolve())
            self.assertIn('合成語音', dest.read_text(encoding='utf-8'))
            self.assertEqual(source.read_bytes(), b'RIFF0000WAVE')


if __name__ == '__main__':
    unittest.main()

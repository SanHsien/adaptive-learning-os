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

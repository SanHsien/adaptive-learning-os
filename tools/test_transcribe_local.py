import tempfile
import unittest
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import patch

from transcribe_local import render_srt, timestamp, transcribe


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
            with patch.dict(sys.modules, {'faster_whisper': fake_module}):
                self.assertEqual(transcribe(source, dest), dest.resolve())
            self.assertIn('合成語音', dest.read_text(encoding='utf-8'))
            self.assertEqual(source.read_bytes(), b'RIFF0000WAVE')


if __name__ == '__main__':
    unittest.main()

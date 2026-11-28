"""Optional offline-media transcription companion. Audio never leaves this process."""

import argparse
import io
from pathlib import Path


SUPPORTED = {'.mp3', '.wav', '.m4a', '.mp4', '.webm'}
MAX_BYTES = 100 * 1024 * 1024
MAX_AUDIO_SECONDS = 3600
SAMPLE_RATE = 16000
MAX_SRT_CHARS = 100000
MAX_SRT_BYTES = 400000
LIMIT_EXIT_CODE = 75


class TranscriptionLimitError(ValueError):
    pass


def validate_iso_boxes(media):
    """Check top-level ISO BMFF box bounds without reading payloads."""
    end = media.seek(0, io.SEEK_END)
    offset = 0
    while offset < end:
        media.seek(offset)
        header = media.read(8)
        if len(header) != 8:
            raise ValueError('MP4/M4A 區塊標頭截斷')
        size = int.from_bytes(header[:4], 'big')
        minimum = 8
        if size == 1:
            extended = media.read(8)
            if len(extended) != 8:
                raise ValueError('MP4/M4A 延伸區塊標頭截斷')
            size = int.from_bytes(extended, 'big')
            minimum += 8
        elif size == 0:
            size = end - offset
        if header[4:8] == b'uuid':
            minimum += 16
        if size < minimum or size > end - offset:
            raise ValueError('MP4/M4A 區塊長度無效或檔案截斷')
        offset += size


def read_ebml_vint(media, *, element_id=False):
    first = media.read(1)
    if not first or first == b'\x00':
        raise ValueError('WebM 區塊標頭無效或截斷')
    width = 9 - first[0].bit_length()
    rest = media.read(width - 1)
    if len(rest) != width - 1 or (element_id and width > 4):
        raise ValueError('WebM 區塊標頭無效或截斷')
    value = int.from_bytes(first + rest, 'big')
    if element_id:
        return value
    value &= (1 << (7 * width)) - 1
    return None if value == (1 << (7 * width)) - 1 else value


def validate_webm_bounds(media):
    """Check declared top-level EBML element sizes; allow streaming segments."""
    end = media.seek(0, io.SEEK_END)
    media.seek(0)
    while media.tell() < end:
        element = read_ebml_vint(media, element_id=True)
        size = read_ebml_vint(media)
        if size is None:
            if element != 0x18538067:
                raise ValueError('WebM 區塊長度無效')
            return
        if size > end - media.tell():
            raise ValueError('WebM 宣告長度超過實際檔案，影音已截斷')
        media.seek(size, io.SEEK_CUR)


def validate_mp3_declared_length(media):
    """Reject a first-frame Xing/Info byte count exceeding the remaining file."""
    end = media.seek(0, io.SEEK_END)
    media.seek(0)
    tag = media.read(10)
    offset = 0
    if tag[:3] == b'ID3':
        if len(tag) != 10 or any(byte & 0x80 for byte in tag[6:10]):
            raise ValueError('MP3 ID3 標頭無效或截斷')
        offset = 10 + sum(byte << (7 * (3 - index)) for index, byte in enumerate(tag[6:10]))
        if tag[3] == 4 and tag[5] & 0x10:
            offset += 10
        if offset > end:
            raise ValueError('MP3 ID3 宣告長度超過實際檔案，音訊已截斷')
    media.seek(offset)
    frame = media.read(4)
    if len(frame) != 4 or frame[0] != 0xff or frame[1] & 0xe0 != 0xe0:
        return
    version = (frame[1] >> 3) & 3
    layer = (frame[1] >> 1) & 3
    if version == 1 or layer != 1:
        return
    # Only inspect the conventional first-frame metadata position.
    mono = frame[3] >> 6 == 3
    side_info = (17 if mono else 32) if version == 3 else (9 if mono else 17)
    crc = 0 if frame[1] & 1 else 2
    media.seek(offset + 4 + crc + side_info)
    marker = media.read(8)
    if len(marker) != 8 or marker[:4] not in (b'Xing', b'Info'):
        return
    flags = int.from_bytes(marker[4:], 'big')
    if flags & 1:
        media.read(4)  # Optional frame count precedes byte count.
    if flags & 2:
        count = media.read(4)
        if len(count) != 4 or int.from_bytes(count, 'big') > end - offset:
            raise ValueError('MP3 宣告長度超過實際檔案，音訊已截斷')


def decode_bounded(source, max_seconds=MAX_AUDIO_SECONDS):
    """Decode mono PCM incrementally; enforce actual samples, not metadata."""
    import av
    import numpy as np

    # RIFF/WAVE can end on a complete PCM packet without a corruption flag.
    with Path(source).open('rb') as media:
        header = media.read(12)
        if header[:4] == b'RIFF' and header[8:12] == b'WAVE':
            declared_size = int.from_bytes(header[4:8], 'little') + 8
            if declared_size > media.seek(0, io.SEEK_END):
                raise ValueError('WAV 宣告長度超過實際檔案，音訊已截斷')
        if header[4:8] == b'ftyp':
            validate_iso_boxes(media)
        if header[:4] == b'\x1a\x45\xdf\xa3':
            validate_webm_bounds(media)
        if Path(source).suffix.lower() == '.mp3':
            validate_mp3_declared_length(media)
    resampler = av.AudioResampler(format='s16', layout='mono', rate=SAMPLE_RATE)
    limit = max_seconds * SAMPLE_RATE * 2
    with io.BytesIO() as buffer, av.open(str(source), mode='r') as container:
        def append_frames(frames):
            for frame in frames:
                if buffer.tell() + frame.samples * 2 > limit:
                    raise TranscriptionLimitError('音訊超過 60 分鐘，請分段轉錄')
                buffer.write(frame.to_ndarray().tobytes())

        if not container.streams.audio:
            raise ValueError('影音沒有可解碼的音訊')
        for packet in container.demux(container.streams.audio[0]):
            if packet.is_corrupt:
                raise ValueError('影音音訊資料損毀或截斷')
            for frame in packet.decode():
                if frame.is_corrupt:
                    raise ValueError('影音音訊資料損毀或截斷')
                frame.pts = None
                append_frames(resampler.resample(frame))
        append_frames(resampler.resample(None))
        if not buffer.tell():
            raise ValueError('影音沒有可解碼的音訊')
        return np.frombuffer(buffer.getvalue(), dtype=np.int16).astype(np.float32) / 32768.0


def timestamp(seconds):
    if not isinstance(seconds, (int, float)) or not 0 <= seconds < 24 * 3600:
        raise ValueError('無效的字幕時間碼（影片長度需小於 24 小時）')
    millis = round(seconds * 1000)
    hours, remainder = divmod(millis, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, milliseconds = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}'


def render_srt(segments):
    blocks = []
    chars = size = 0
    for segment in segments:
        start, end, words = segment.start, segment.end, segment.text.strip()
        if not words:
            continue
        if end <= start:
            raise ValueError('辨識結果時間碼無效')
        # Avoid allowing model text to mimic extra SRT cues.
        words = ' '.join(words.split())
        block = f'{len(blocks) + 1}\n{timestamp(start)} --> {timestamp(end)}\n{words}'
        separator = 2 if blocks else 1  # Include the final newline.
        chars += len(block) + separator
        size += len(block.encode('utf-8')) + separator
        if chars > MAX_SRT_CHARS or size > MAX_SRT_BYTES:
            raise TranscriptionLimitError('逐字稿過長，請分段轉錄')
        blocks.append(block)
    if not blocks:
        raise ValueError('沒有辨識到語音，未產生逐字稿')
    return '\n\n'.join(blocks) + '\n'


def transcribe(input_path, output_path, model_name='small', language='zh', device='cpu'):
    source = Path(input_path).resolve(strict=True)
    target = Path(output_path).resolve()
    if not source.is_file() or source.suffix.lower() not in SUPPORTED:
        raise ValueError('僅支援 MP3、WAV、M4A、MP4、WebM')
    if not 0 < source.stat().st_size <= MAX_BYTES:
        raise ValueError('影音必須為 1 至 100 MB 內的非空檔案')
    if target.exists():
        raise FileExistsError('輸出檔已存在；請更換 --output，避免覆寫教材')
    if target == source or target.suffix.lower() != '.srt':
        raise ValueError('輸出必須是另一個 .srt 檔案')
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('請先安裝本機語音辨識套件：python -m pip install faster-whisper') from exc
    audio = decode_bounded(source)
    model = WhisperModel(model_name, device=device, compute_type='int8')
    segments, _ = model.transcribe(audio, language=language, vad_filter=True)
    result = render_srt(segments)
    # Exclusive create prevents overwriting a file created concurrently.
    with target.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(result)
    return target


def main():
    parser = argparse.ArgumentParser(description='本機 Whisper 轉錄：音訊不會上傳，模型首次執行可能下載')
    parser.add_argument('input', help='本機 MP3/WAV/M4A/MP4/WebM（上限 100 MB）')
    parser.add_argument('--output', help='輸出的 SRT 路徑，預設與影音同名')
    parser.add_argument('--model', default='small', help='模型名稱或已下載的本機模型資料夾')
    parser.add_argument('--language', default='zh', help='語言代碼，預設 zh')
    parser.add_argument('--device', default='cpu', choices=('cpu', 'cuda'))
    args = parser.parse_args()
    source = Path(args.input)
    try:
        result = transcribe(source, args.output or source.with_suffix('.srt'), args.model, args.language, args.device)
    except TranscriptionLimitError as exc:
        parser.exit(LIMIT_EXIT_CODE, str(exc) + '\n')
    print(f'逐字稿已產生：{result}（請校對後匯入正確家人及科目）')


if __name__ == '__main__':
    main()

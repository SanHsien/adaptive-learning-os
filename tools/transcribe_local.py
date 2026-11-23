"""Optional offline-media transcription companion. Audio never leaves this process."""

import argparse
from pathlib import Path


SUPPORTED = {'.mp3', '.wav', '.m4a', '.mp4', '.webm'}
MAX_BYTES = 100 * 1024 * 1024


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
    for segment in segments:
        start, end, words = segment.start, segment.end, segment.text.strip()
        if not words:
            continue
        if end <= start:
            raise ValueError('辨識結果時間碼無效')
        # Avoid allowing model text to mimic extra SRT cues.
        words = ' '.join(words.split())
        blocks.append(f'{len(blocks) + 1}\n{timestamp(start)} --> {timestamp(end)}\n{words}')
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
    model = WhisperModel(model_name, device=device, compute_type='int8')
    segments, _ = model.transcribe(str(source), language=language, vad_filter=True)
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
    result = transcribe(source, args.output or source.with_suffix('.srt'), args.model, args.language, args.device)
    print(f'逐字稿已產生：{result}（請校對後匯入正確家人及科目）')


if __name__ == '__main__':
    main()

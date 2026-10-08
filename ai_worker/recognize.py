"""One short-lived process per file: releases model memory after recognition."""
import json
import subprocess
import sys
import wave
from pathlib import Path


def recognize(kind, filename):
    if kind == 'voice':
        wav = str(Path(filename).with_suffix('.wav'))
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-protocol_whitelist', 'file,pipe',
                        '-format_whitelist', 'ogg,wav,mp3,flac,matroska,webm,mov,aac', '-i', filename,
                        '-t', '31', '-ar', '16000', '-ac', '1', wav],
                       check=True, capture_output=True, timeout=20)
        with wave.open(wav) as audio:
            if audio.getnframes() / audio.getframerate() > 30.5:
                raise ValueError('Аудио должно быть не длиннее 30 секунд.')
        from faster_whisper import WhisperModel
        model = WhisperModel('/models/whisper-base', device='cpu', compute_type='int8', cpu_threads=1)
        segments, _ = model.transcribe(wav, language='ru', beam_size=3, vad_filter=True,
                                       condition_on_previous_text=False)
        return ' '.join(s.text.strip() for s in segments)[:6000]
    from PIL import Image, ImageOps
    import pytesseract
    Image.MAX_IMAGE_PIXELS = 12_000_000
    import warnings
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    with Image.open(filename) as original:
        if original.format not in {'JPEG', 'PNG', 'WEBP'}:
            raise ValueError('Нужен чек в JPEG, PNG или WEBP.')
        im = ImageOps.exif_transpose(original)
        im.thumbnail((1800, 2400))
        im = ImageOps.autocontrast(ImageOps.grayscale(im))
        return pytesseract.image_to_string(im, lang='rus+eng', config='--psm 6', timeout=40)[:6000]


if __name__ == '__main__':
    try:
        print(json.dumps({'text': recognize(sys.argv[1], sys.argv[2])}, ensure_ascii=False))
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
    except Exception:
        print(json.dumps({'error': 'Не удалось распознать файл. Попробуйте более чёткую запись или фото.'}, ensure_ascii=False))

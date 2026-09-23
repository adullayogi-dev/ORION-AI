"""Orion speech-to-text - offline Whisper on GPU/CPU with Google fallback."""

import os
import sysconfig
import glob
import threading

import numpy as np

WHISPER_MODEL = os.environ.get("ORION_WHISPER_MODEL", "small")

_model = None
_model_lock = threading.Lock()
_nvidia_paths_prepared = False


def _prepare_nvidia_paths():
    """Make faster-whisper's CUDA DLLs loadable on Windows."""
    global _nvidia_paths_prepared
    if _nvidia_paths_prepared:
        return
    _nvidia_paths_prepared = True

    site = sysconfig.get_paths().get("purelib", "")
    if not site or not os.path.isdir(site):
        return

    directories = []
    for pattern in ("nvidia/**/bin", "nvidia/**/lib"):
        for base in glob.glob(os.path.join(site, pattern), recursive=True):
            absolute = os.path.abspath(base)
            if os.path.isdir(absolute) and absolute not in directories:
                directories.append(absolute)

    if directories:
        os.environ["PATH"] = (
            os.pathsep.join(directories) + os.pathsep + os.environ.get("PATH", "")
        )


def _load_model():
    global _model
    with _model_lock:
        if _model is None:
            _prepare_nvidia_paths()
            from faster_whisper import WhisperModel
            _model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")
        return _model


def transcribe(audio_int16, sample_rate=16000):
    """Transcribe raw int16 mono PCM audio into text (whisper, local).

    Returns an empty string when nothing intelligible was heard.
    """
    audio = np.frombuffer(audio_int16, dtype=np.int16)
    audio = audio.astype(np.float32) / 32768.0

    try:
        model = _load_model()
        segments, _info = model.transcribe(audio, beam_size=5)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text
    except Exception as error:
        print("WHISPER ERROR:", error)
        return ""


def recognize(audio_data, language="en-IN"):
    """Offline-first recognition with Google Speech as a fallback.

    Args:
        audio_data: speech_recognition.AudioData instance.
    Returns:
        (text, engine) where text is "" when unrecognised.
    """
    import speech_recognition as sr

    try:
        text = transcribe(audio_data.get_wav_data(convert_rate=16000, convert_width=2) or
                          audio_data.get_raw_data(convert_rate=16000, convert_width=2), 16000)
        if text:
            return text, "whisper"
    except Exception as error:
        print("STT MODULE ERROR:", error)

    recognizer = sr.Recognizer()
    recognizer.operation_timeout = 4
    for lang in (language, "en-US"):
        try:
            text = recognizer.recognize_google(audio_data, language=lang)
            if text and text.strip():
                return text.strip(), "google"
        except sr.UnknownValueError:
            continue
        except sr.RequestError as error:
            print("Google STT unavailable:", error)
            break
    return "", "none"


if __name__ == "__main__":
    print("Model:", WHISPER_MODEL, "(loaded on first use)")
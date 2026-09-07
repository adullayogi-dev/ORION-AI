import sounddevice as sd
import speech_recognition as sr
import wave

SAMPLE_RATE = 16000
DURATION = 5
FILE_NAME = "voice.wav"

print("ORION is listening... 🎤")
print("Speak now!")

recording = sd.rec(
    int(DURATION * SAMPLE_RATE),
    samplerate=SAMPLE_RATE,
    channels=1,
    dtype="int16"
)

sd.wait()

with wave.open(FILE_NAME, "wb") as file:
    file.setnchannels(1)
    file.setsampwidth(2)
    file.setframerate(SAMPLE_RATE)
    file.writeframes(recording.tobytes())

print("Processing your voice...")

recognizer = sr.Recognizer()

with sr.AudioFile(FILE_NAME) as source:
    audio = recognizer.record(source)

try:
    text = recognizer.recognize_google(audio)
    print("You said:", text)

except sr.UnknownValueError:
    print("Sorry, I couldn't understand you.")

except sr.RequestError as error:
    print("Speech recognition service error:", error)

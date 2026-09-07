import win32com.client
import winsound

print("Creating Orion voice audio file...")

speaker = win32com.client.Dispatch("SAPI.SpVoice")

# Select Zira
voices = speaker.GetVoices()

for i in range(voices.Count):
    voice = voices.Item(i)

    if "Zira" in voice.GetDescription():
        speaker.Voice = voice
        print("Zira selected!")
        break

# Create WAV file
stream = win32com.client.Dispatch("SAPI.SpFileStream")

stream.Open(
    "orion_voice.wav",
    3,      # create/write
    False
)

speaker.AudioOutputStream = stream

speaker.Speak(
    "Hello. I am Orion. This is an audio test."
)

stream.Close()

print("Audio file created:")
print("orion_voice.wav")

print("Playing audio now...")

winsound.PlaySound(
    "orion_voice.wav",
    winsound.SND_FILENAME
)

print("Audio test finished.")

import win32com.client

print("Starting Windows Zira voice test...")

speaker = win32com.client.Dispatch("SAPI.SpVoice")

voices = speaker.GetVoices()

print("\nAvailable Windows voices:")

for i in range(voices.Count):
    voice = voices.Item(i)
    print(i, ":", voice.GetDescription())

# Find Zira
for i in range(voices.Count):
    voice = voices.Item(i)

    if "Zira" in voice.GetDescription():
        speaker.Voice = voice
        print("\n>>> Zira selected!")
        break

# Slightly fast
speaker.Rate = 2

# Full volume
speaker.Volume = 100

print("\nORION is speaking now...")

speaker.Speak(
    "Hello. I am Orion. This is my Windows voice test."
)

print("Voice test finished.")

import pyttsx3

engine = pyttsx3.init()

voices = engine.getProperty("voices")
engine.setProperty("voice", voices[1].id)

# Speed: lower = slower and usually clearer
engine.setProperty("rate", 188)

# Volume: 0.0 to 1.0
engine.setProperty("volume", 1.0)

engine.say("Hello. I am Orion, your personal AI assistant. How can I help you?")
engine.runAndWait()

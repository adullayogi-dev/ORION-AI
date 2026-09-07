from local_brain import ask_ai


print("ORION LOCAL AI TEST")
print("------------------")

question = input("YOU: ")

answer = ask_ai(question)

print("ORION:", answer)

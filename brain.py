from openai import OpenAI

client = OpenAI()


def ask_ai(question):

    response = client.responses.create(
        model="gpt-5.6",
        instructions=(
            "You are Orion, a personal AI assistant. "
            "You are speaking through a voice assistant, "
            "so keep your answers clear, natural, and reasonably short."
        ),
        input=question
    )

    return response.output_text

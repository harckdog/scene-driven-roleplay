from openai import OpenAI
from config import API_KEY, BASE_URL, MODEL
from prompts import SYSTEM_PROMPT, USER_PROFILE


client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)


messages = [
    {
        "role": "system",
        "content": SYSTEM_PROMPT + USER_PROFILE
    }
]


while True:
    user_input = input("\nUser: ")

    if user_input == "exit":
        break

    messages.append(
        {
            "role": "user",
            "content": user_input
        }
    )

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages
    )

    answer = response.choices[0].message.content

    print("\nAssistant:", answer)

    messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )
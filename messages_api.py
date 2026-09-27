import os
from anthropic import Anthropic
from dotenv import load_dotenv
from learning_tools import get_current_time

load_dotenv()

client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

user_input = input("What would you like to ask: ")
context=[{"content": user_input, "role": "user"}]


while user_input != "X" and user_input != "x":

    message = client.messages.create(
        max_tokens=1024,
        messages=context,
        model="claude-haiku-4-5-20251001",
        system="Whenever the user asks for the time, respond with: 'get_current_time'. Prefix meanings: 'TOOL' means the assistant is asking for information via a tool (don't add this yourself) and 'TOOL RESPONSE' is the response to that request."
    )

    if "get_current_time" in message.content[0].text:
        message.content[0].text = "TOOL: " + message.content[0].text
        context.append({"content": message.content, "role":"assistant"})
        context.append({"role": "user", "content": "TOOL RESPONSE: " + get_current_time()})

        message = client.messages.create(
            max_tokens=1024,
            messages=context,
            model="claude-haiku-4-5-20251001",
            system="Whenever the user asks for the time, respond with: 'get_current_time'. Prefix meanings: 'TOOL' means the assistant is asking for information via a tool (don't add this yourself) and 'TOOL RESPONSE' is the response to that request."
    )

    print(f"Assistant: {message.content[0].text}\nInput Tokens: {message.usage.input_tokens} & Output Tokens: {message.usage.output_tokens}\n")
    context.append({"content":message.content, "role":"assistant"})
    
    user = input("User: ")
    if user != "X" and user != "x":
        context.append({"content":user, "role":"user"})
        
    user_input = user

for prompt in context:
    print(prompt)
    print()
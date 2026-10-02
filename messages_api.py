import os
from anthropic import Anthropic
from dotenv import load_dotenv
from learning_tools import get_current_time

load_dotenv()

client = Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)


tool_to_func_map = {
    "get_current_time": get_current_time
}

timing_tool = {
    "name": "get_current_time",
    "description": "Get currrent time for any given timezone. Use this when the user asks for time.",
    "input_schema":{
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "The city for which to get the current time. Give timezones in the format 'America/Toronto' not 'EST' or 'Toronto'."
            }
        },
        "required": ["city"]
    }
}


def ask_model(context):
    return client.messages.create(
        max_tokens=1024,
        messages=context,
        model="claude-haiku-4-5-20251001",
        tools=[timing_tool]
    )

context = []
HIT_LIMIT = 5   # model calls allowed per turn (one user question -> one answer from assistant)

def run_agent(context, HIT_LIMIT):
    
    # first user input. if it is 'X' or 'x', the program terminates
    user_input = input("User: ")
    if user_input != "X" and user_input != "x":
        context.append({"content":user_input, "role":"user"})
    else: return
    print()

    # start the user-assistant interaction loop
    while user_input != "X" and user_input != "x":
        
        model_calls = 0     # if model_calls >= HIT_LIMIT, end the turn
        status = "done"     # how this turn ended: "done", "hit_limit", "cut_off"
        message = ask_model(context)
        model_calls += 1
        context.append({"role": "assistant", "content": message.content})
        if message.stop_reason == "max_tokens":
            status = "cut_off"

        while message.stop_reason == "tool_use":

            tool_answer = []
            for c in message.content:
                if c.type == "tool_use":
                    try:
                        output = tool_to_func_map[c.name](**c.input)
                        tool_answer.append({"type": "tool_result", "tool_use_id": c.id, "content": output})
                    
                    except Exception as e:
                        tool_answer.append({
                            "type": "tool_result",
                            "tool_use_id": c.id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        })

            context.append({"role": "user", "content": tool_answer})
            
            if model_calls >= HIT_LIMIT:
                status = "hit_limit"
                context.append({"role": "assistant", "content": "I stopped because I hit the model call limit."})
                break

            message = ask_model(context)
            model_calls += 1
            context.append({"role": "assistant", "content": message.content})
            if message.stop_reason == "max_tokens":
                status = "cut_off"

        # print the assistant's answer if the turn finished normally or was cut off (partial answer)
        if status == "done" or status == "cut_off":
            print(f"{context[-1]['content'][0].text}\n")
        
        if status == "hit_limit":
            print(f"{context[-1]['content']}\n")

        print(f"STATUS: {status}")
        print(f"Model calls: {model_calls}\n")
        print()

        user_input = input("User: ")
        if user_input != "X" and user_input != "x":
            context.append({"content":user_input, "role":"user"})
        
        else: return
        print()
        

run_agent(context, HIT_LIMIT)
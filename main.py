import asyncio
from flask import Flask, render_template, request
import openai
from dotenv import load_dotenv
import os

app = Flask(__name__)

load_dotenv()
client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
assistant_id = os.getenv('ASSISTANT_ID')
thread_id = os.getenv('THREAD_ID')

response_cache = None
last_plan_parameters = None

def format_workout_plan(plan):
    """
    Formats the workout plan for display in the HTML template.

    This function takes a workout plan as input and formats it for display in the HTML template.
    It does this by splitting the plan into lines, stripping whitespace from each line, and removing any empty lines.
    It then wraps each line in a <li> tag within a <ul> if the line starts with a dash, or a <p> tag otherwise.

    Args:
        plan (str): The workout plan to be formatted.

    Returns:
        list: The formatted workout plan, with each line as a separate string in the list.
    """
    weeks_split = plan.split("\n")
    weeks_split = [week.strip() for week in weeks_split]
    weeks_split = [week for week in weeks_split if week]

    formatted_plan = []
    for week in weeks_split:
        if week.startswith('-'):
            if formatted_plan and not formatted_plan[-1].endswith('</ul>'):
                formatted_plan.append('</ul>')
            if not formatted_plan or not formatted_plan[-1].endswith('</ul>'):
                formatted_plan.append('<ul>')
            formatted_plan.append('<li>' + week[1:] + '</li>')  # remove the dash
        else:
            if formatted_plan and formatted_plan[-1].endswith('</ul>'):
                formatted_plan.append('</ul>')
            formatted_plan.append('<p>' + week + '</p>')
    if formatted_plan and not formatted_plan[-1].endswith('</ul>'):
        formatted_plan.append('</ul>')

    return formatted_plan

@app.route("/", methods=["GET", "POST"])
def index():
    """
    Handles the index route.

    This function handles both GET and POST requests to the root ("/") route.
    If the request method is POST, it retrieves the form data, generates a workout plan using the `generate_and_send_message` function, and renders the result template with the workout plan.
    If the request method is GET, it simply renders the index template.

    Args:
        None

    Returns:
        str: The rendered HTML template.
    """
    if request.method == "POST":
        weeks = int(request.form.get("weeks"))
        goal = request.form.get("goal")
        location = request.form.get("location")
        weight_to_lose = int(request.form.get("weight")) if goal == "Weight loss" else None
        formatted_response = asyncio.run(generate_and_send_message(weeks, goal, location, weight_to_lose))
        return render_template("result.html", response=formatted_response)
    return render_template("index.html")

async def generate_and_send_message(weeks, goal, location, weight_to_lose=None):
    """
    Generates and sends a message to the OpenAI API, optimizing the prompt for better results.

    This function checks if the workout plan parameters have changed since the last API call.
    If they have, it calls the `generate_workout_plan` function with an optimized prompt to generate a new workout plan and update the cache.
    If the parameters have not changed, it returns the cached response.

    Args:
        weeks (int): The number of weeks for the workout plan.
        goal (str): The fitness goal for the workout plan. Can be "Weight loss" or "Muscle gain".
        location (str): The location where the workouts will be performed.
        weight_to_lose (int, optional): The amount of weight to lose in kilograms. Only required if the goal is "Weight loss".

    Returns:
        list: The formatted workout plan.
    """
    global response_cache, last_plan_parameters

    new_plan_parameters = (weeks, goal, location, weight_to_lose)

    if response_cache is None or last_plan_parameters != new_plan_parameters:
        # Optimize the prompt for better results
        if goal == "Weight loss":
            prompt = f"Create a detailed {weeks}-week workout plan to help the user lose {weight_to_lose} kilograms at {location}. The plan should include a mix of cardio, strength training, and flexibility exercises tailored to the user's fitness level and goals."
        elif goal == "Muscle gain":
            prompt = f"Create a comprehensive {weeks}-week workout plan to help the user gain muscle mass at {location}. The plan should include a progressive resistance training program, along with complementary cardio and recovery activities."
        else:
            prompt = f"Create a {weeks}-week workout plan for the user at {location} that focuses on their goal of {goal}."

        response_cache = await generate_workout_plan(prompt)
        last_plan_parameters = new_plan_parameters

    return response_cache

async def generate_workout_plan(prompt):
    """
    Generates a workout plan using the OpenAI API with the provided prompt.

    This function sends the prompt to the OpenAI API and waits for the API to generate a workout plan.
    Once the plan is generated, it is formatted for display in the HTML template.

    Args:
        prompt (str): The prompt to be sent to the OpenAI API.

    Returns:
        list: The formatted workout plan.
    """
    send_message_to_thread(prompt)
    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=assistant_id,
                                          instructions="Please generate a workout plan based on the provided prompt.")
    await wait_for_run_completion_async(client=client, thread_id=thread_id, run_id=run.id)
    response = await get_last_message_async()
    formatted_response = format_workout_plan(response)
    return formatted_response


def send_message_to_thread(message):
    """
    Sends a message to the OpenAI API.

    This function takes a message as input and sends it to the OpenAI API. The message is sent as a user role to the thread specified by the thread_id.

    Args:
        message (str): The message to be sent to the OpenAI API.

    Returns:
        None
    """
    client.beta.threads.messages.create(thread_id=thread_id, role="user", content=message)
async def wait_for_run_completion_async(client, thread_id, run_id, sleep_interval=5):
    """
    Waits for the OpenAI API to complete a run.

    This function continuously checks if a run on the OpenAI API has completed. It does this by retrieving the run using its ID and checking if it has a completion timestamp.
    If the run has not completed, the function waits for a specified interval before checking again.
    If an error occurs while retrieving the run, the function prints the error and breaks the loop.

    Args:
        client (openai.OpenAI): The OpenAI client.
        thread_id (str): The ID of the thread.
        run_id (str): The ID of the run.
        sleep_interval (int, optional): The interval in seconds to wait between checks. Defaults to 5.

    Returns:
        None
    """
    while True:
        try:
            run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
            if run.completed_at:
                break
        except Exception as e:
            print(f"An error occurred while retrieving the run: {e}")
            break
        await asyncio.sleep(sleep_interval)
async def get_last_message_async():
    """
    Gets the last message from the OpenAI API.

    This function retrieves the list of messages from the OpenAI API for the specified thread. It then selects the first message from the list, which is the most recent message.
    It extracts the text value from the message content and returns it.

    Args:
        None

    Returns:
        str: The text value of the most recent message from the OpenAI API.
    """
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    last_message = messages.data[0]
    response = last_message.content[0].text.value
    return response

if __name__ == "__main__":
    app.run(debug=True)
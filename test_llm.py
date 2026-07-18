from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()          # reads your key from .env
client = OpenAI()      # picks up OPENAI_API_KEY automatically

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Say 'key works' and nothing else."}],
)

print(response.choices[0].message.content)
import os

from discord.ext import commands
from dotenv import load_dotenv

from utils import *

load_dotenv()
TOKEN = os.getenv('TOKEN')

client = commands.Bot(intents=discord.Intents.all(), help_command=None)


@client.event
async def on_application_command_error(ctx: discord.ApplicationContext, exception):
    if isinstance(exception, discord.errors.ApplicationCommandInvokeError):
        if "403 Forbidden" in str(exception):
            await ctx.respond("No permisson", ephemeral=True)
            return
        raise exception
    elif isinstance(exception, discord.errors.CheckFailure):
        await ctx.respond(
            embed=ExtraEmbed(ctx.user, description=f"No permisson"),
            ephemeral=True)
        return
    else:
        raise exception


@client.event
async def on_ready():
    print(f'{client.user} started | Ping: {client.latency * 1000}')
    await client.change_presence(activity=discord.CustomActivity(name="Register now!"))


for _ in os.listdir("cogs"):
    try:
        if _ == "__pycache__": continue
        client.load_extension(f"cogs.{_[:-3]}")
    except Exception as e:
        print(e)

client.run(TOKEN)

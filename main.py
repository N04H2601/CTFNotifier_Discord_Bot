import asyncio
import json
import os
import sys
import requests
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from dotenv import load_dotenv
import urllib3
import pytz


class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class CustomDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        super().__init__(object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, obj):
        for key, value in obj.items():
            if isinstance(value, str):
                try:
                    obj[key] = datetime.fromisoformat(value)
                except ValueError:
                    pass
        return obj


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)
bot.remove_command("help")

try:
    with open("events.json") as f:
        events = json.load(f, cls=CustomDecoder)
except:
    events = {}


@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="upcoming CTF events"
        )
    )
    await bot.get_channel(CHANNEL_ID).send(
        "Hello, I am CTF Bot 🤖\nTo see the list of commands, type `/help`."
    )
    await bot.get_channel(CHANNEL_ID).send(file=discord.File("hello.gif"))
    check_agenda.start()


@bot.command()
async def add(ctx, url):
    try:
        url = url.replace("/event/", "/api/v1/events/") + (
            "/" if not url.endswith("/") else ""
        )
        response = requests.get(
            url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5, verify=False
        )
        response.raise_for_status()
        event = response.json()
        event_name = (
            event["title"].strip().replace(" ", "-").replace('"', "").replace("'", "")
        )
        finish_time = datetime.strptime(event["finish"], "%Y-%m-%dT%H:%M:%S%z")
        if finish_time < datetime.now(finish_time.tzinfo):
            await ctx.send("Error: Event has already finished.")
        elif event_name not in events:
            events[event_name] = {
                "ctftime_url": event["ctftime_url"],
                "url": event["url"],
                "start": datetime.strptime(event["start"], "%Y-%m-%dT%H:%M:%S%z"),
                "finish": finish_time,
                "format": event["format"],
                "organizers": ", ".join([o["name"] for o in event["organizers"]]),
                "weight": event["weight"],
                "description": event["description"],
                "participants": event["participants"],
                "reminder_sent": False,
                "good_luck_sent": False,
                "congratulations_sent": False,
                "ending_soon_sent": False,
            }
            await ctx.send(f"Event `{event_name}` added.")
            with open("events.json", "w") as f:
                json.dump(events, f, indent=4, cls=CustomEncoder)
        else:
            await ctx.send(f"Event `{event_name}` already exists.")
    except requests.exceptions.HTTPError as error:
        await ctx.send(f"Error: {error.response.status_code} {error.response.reason}")
    except requests.exceptions.RequestException as error:
        await ctx.send(f"Error: {error}")


@bot.command()
async def agenda(ctx):
    if events:
        embed = discord.Embed(
            title="📅 CTF events", description="List of CTF events.\n", color=0x7289DA
        )
        for event_name, event in events.items():
            embed.add_field(
                name=f"**{event_name}**",
                value=f"Start: {(event['start'] + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M')} CEST\nEnd: {(event['finish'] + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M')} CEST",
                inline=False,
            )
        await ctx.send(embed=embed)
    else:
        await ctx.send("No events added yet.")


@bot.command()
async def details(ctx, event_name):
    if event_name in events:
        event = events[event_name]
        embed = discord.Embed(
            title=f"🛡️ {event_name} 🛡️",
            description=f"{event['description']}.\n",
            color=0x7289DA,
        )
        embed.add_field(
            name="**Start (CEST)**",
            value=(event["start"] + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
            inline=True,
        )
        embed.add_field(
            name="**End (CEST)**",
            value=(event["finish"] + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
            inline=True,
        )
        embed.add_field(name="**Format**", value=event["format"], inline=True)
        embed.add_field(name="**Organizers**", value=event["organizers"], inline=True)
        embed.add_field(name="**Weight**", value=event["weight"], inline=True)
        embed.add_field(
            name="**Participants**", value=event["participants"], inline=True
        )
        embed.add_field(
            name="**CTFtime**",
            value=f"[CTFtime Link]({event['ctftime_url']})",
            inline=True,
        )
        embed.add_field(
            name="**URL**", value=f"[Event Link]({event['url']})", inline=True
        )
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"Event `{event_name}` not found.")


@bot.command()
async def remove(ctx, event_name):
    if event_name in events:
        del events[event_name]
        await ctx.send(f"Event `{event_name}` removed.")
        with open("events.json", "w") as f:
            json.dump(events, f, indent=4, cls=CustomEncoder)
    else:
        await ctx.send(f"Event `{event_name}` not found.")


@bot.command()
async def clear(ctx):
    embed = discord.Embed(
        title="⚠️ Warning",
        description="Are you sure you want to clear all events?",
        color=0xFF0000,
    )
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("✅")
    await msg.add_reaction("❌")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"]

    try:
        reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)
    except asyncio.TimeoutError:
        await msg.delete()
    else:
        if str(reaction.emoji) == "✅":
            events.clear()
            await ctx.send("All events cleared.")
            with open("events.json", "w") as f:
                json.dump(events, f, indent=4)
        elif str(reaction.emoji) == "❌":
            await ctx.send("Clearing events cancelled.")
        await msg.delete()


@bot.command()
async def upcoming(ctx):
    try:
        response = requests.get(
            "https://ctftime.org/api/v1/events/?limit=15",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=5,
            verify=False,
        )
        response.raise_for_status()
        events_list = response.json()
        embed = discord.Embed(
            title="📅 Upcoming CTF events",
            description="List of upcoming CTF events.\n",
            color=0x7289DA,
        )
        for event in events_list:
            event_name = event["title"]
            event_weight = event["weight"]
            official_url = event.get("url", "Not available")
            start_time = datetime.fromisoformat(event["start"])
            end_time = datetime.fromisoformat(event["finish"])
            embed.add_field(
                name=f"**{event_name}**",
                value=f"Weight: {event_weight}\nStart: {(start_time + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M')} CEST\nEnd: {(end_time + timedelta(hours=2)).strftime('%Y-%m-%d %H:%M')} CEST\n[CTFtime Link]({event['ctftime_url']}), [Event Link]({official_url})",
                inline=False,
            )
        await ctx.send(embed=embed)
    except requests.exceptions.HTTPError as error:
        await ctx.send(f"Error: {error.response.status_code} {error.response.reason}")
    except requests.exceptions.RequestException as error:
        await ctx.send(f"Error: {error}")


@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="📚 Available commands",
        description="List of available commands for this bot.\n",
        color=0x7289DA,
    )
    embed.add_field(
        name="``/add <ctftime-url>``", value="Add a CTF event", inline=False
    )
    embed.add_field(name="``/agenda``", value="List the added CTF events", inline=False)
    embed.add_field(
        name="``/details <event-name>``",
        value="Show details for a specific event",
        inline=False,
    )
    embed.add_field(
        name="``/remove <event-name>``", value="Remove a specific event", inline=False
    )
    embed.add_field(name="``/clear``", value="Remove all events", inline=False)
    embed.add_field(
        name="``/upcoming``", value="Show upcoming CTF events", inline=False
    )
    embed.add_field(name="``/help``", value="Show this help message", inline=False)
    await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(
            "Command not found. Type `/help` for a list of available commands."
        )


@bot.event
async def on_message(message):
    if message.content == "N04H":
        await message.channel.send("Stegano boy")
    elif message.content == "Ayweth20":
        await message.channel.send("Web master")
    elif message.content == "Tibogri78":
        await message.channel.send("Forensics master")

    await bot.process_commands(message)


@tasks.loop(seconds=10)
async def check_agenda():
    tz = pytz.timezone("Europe/Paris")

    events_to_delete = []

    for event_name, event in events.items():
        start_time = event["start"].astimezone(tz)
        end_time = event["finish"].astimezone(tz)
        now = datetime.now(tz)

        if (
            not event.get("reminder_sent")
            and start_time - timedelta(hours=1) <= now < start_time
        ):
            channel = bot.get_channel(CHANNEL_ID)
            embed = discord.Embed(
                title=f"🚨 `{event_name}` starts in 1 hour!",
                description=f"Don't forget to prepare for the CTF at {start_time.strftime('%Y-%m-%d %H:%M:%S')}!",
                color=0xFF0000,
            )
            await channel.send(embed=embed)
            event["reminder_sent"] = True
        elif not event.get("good_luck_sent") and start_time <= now < end_time:
            channel = bot.get_channel(CHANNEL_ID)
            embed = discord.Embed(
                title=f"🍀 Good luck for `{event_name}` everyone!",
                description=f"The CTF is currently ongoing until {end_time.strftime('%Y-%m-%d %H:%M:%S')}.",
                color=0x00FF00,
            )
            await channel.send(embed=embed)
            event["good_luck_sent"] = True
        elif not event.get(
            "congratulations_sent"
        ) and end_time <= now < end_time + timedelta(hours=1):
            channel = bot.get_channel(CHANNEL_ID)
            embed = discord.Embed(
                title=f"🎉 Congratulations for `{event_name}` everyone!",
                description=f"The CTF ended at {end_time.strftime('%Y-%m-%d %H:%M:%S')}.",
                color=0x00FFFF,
            )
            await channel.send(embed=embed)
            event["congratulations_sent"] = True
            events_to_delete.append(event_name)
        elif (
            not event.get("ending_soon_sent")
            and end_time - timedelta(hours=1) <= now < end_time
        ):
            channel = bot.get_channel(CHANNEL_ID)
            embed = discord.Embed(
                title=f"⏰ `{event_name}` ends in 1 hour!",
                description=f"Hurry up and submit your flags before the CTF ends at {end_time.strftime('%Y-%m-%d %H:%M:%S')}!",
                color=0xFFA500,
            )
            await channel.send(embed=embed)
            event["ending_soon_sent"] = True

    for event_name in events_to_delete:
        del events[event_name]
        with open("events.json", "w") as f:
            json.dump(events, f, indent=4)


bot.run(TOKEN)

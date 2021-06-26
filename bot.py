# Bot permissions: manage channels, view channels, send messages, read message history

import os
import discord
from dotenv import load_dotenv
from discord.ext import commands, tasks
import time
from datetime import datetime, timezone

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

bot = commands.Bot(command_prefix='a!')


########## REGULAR FUNCTIONS ##########

def getCategory(name, ctx):
    for category in ctx.message.guild.categories:
            if(category.name.lower() == name.lower()):
                return category
    return None

def makeFile():
    
    message_file_exists = os.path.isfile("archives.txt")

    if(not message_file_exists):
        f = open("archives.txt", "x")
        f.close()


def readArchive(id, arg): # Arguments: 0=id (never used), 1=archive category name, 2=timeout time
    makeFile()

    f = open("archives.txt", "r")
    db = f.read().split("\n")
    # print(len(db))

    f.close()

    for server in db:
        # print(server)
        line = server.split()
        if len(line) > 1:
            if line[0] == str(id):
                return line[arg]
    return None

def writeArchive(id, category, timeout):
    makeFile()
    f = open("archives.txt", "r")
    db = f.read().split("\n")
    f.close()

    f = open("archives.txt", "w")

    found = False
    index = 0
    for server in db:
        line = server.split()
        if len(line) > 1:
            if line[0] == id:
                db[index] = id + " " + category + " " + timeout
                found = True
            f.write(db[index] + "\n")

    if not found:
        f.write(id + " " + category + " " + timeout + "\n")
    
    f.close()

def isMessage(message):
    return message.author != bot.user

def isNumMessage(message):
    return isMessage(message) and message.content.isnumeric()

########## BOT FUNCTIONS ##########

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.command()
async def archiehelp(ctx):

    descrip = "Hi there! I'm Archie, a Discord bot that archives inactive channels.\n\n" + \
        "After you set me up, I will check on your server every day and archive channels that haven't been active for a while.\n\n" + \
        "All of this is automatic, so you don't have to worry about calling on me too often, but here are some commands you can use yourself."
    embed = discord.Embed(title="Archie", description=descrip, color=0xff4912)
    embed.add_field(name="a!config", value=" - Set archive category and channel timeout.", inline=False)
    embed.add_field(name="a!archive", value=" - Manually archive the current channel.", inline=False)
    embed.add_field(name="a!archiehelp", value=" - Display the help menu.\n\n" + \
        "Archived channels are only moved, never deleted, so you can restore an archived channel simply by sending a message in it.", inline=False)

    await ctx.message.channel.send(embed=embed)

@bot.command()
async def config(ctx):

    await ctx.message.channel.send("What is the name of your archive category? (NOT case sensitive)")
    cat_name = (await bot.wait_for("message", check=isMessage, timeout=60.0)).content

    await ctx.message.channel.send("After how many days should channels be archived? (Must be a full number)")
    timeout = (await bot.wait_for("message", check=isNumMessage, timeout=60.0)).content
    
    id = str(ctx.message.guild.id)
    if getCategory(cat_name, ctx) == None:
        await ctx.message.channel.send("Category **" + cat_name + "** created.")
        category = await ctx.message.guild.create_category(cat_name)

    writeArchive(id, cat_name, timeout)
    
    await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive. Channels inactive for **" + timeout + "** days will be moved to **" + cat_name.upper() + "**.")

@bot.command()
async def archive(ctx):

    id = str(ctx.message.guild.id)
    archive = getCategory(readArchive(id, 1), ctx)
    if archive == None:
        await ctx.message.channel.send("An archive category does not exist. Please use **a!setup** to create one.")
    else:
        await ctx.message.channel.edit(category=archive)
        await ctx.message.channel.send("This channel has been archived.")

@bot.command()
async def getLast(channel):

    message = await channel.fetch_message(channel.last_message_id)
    id = str(message.guild.id)
    timestamp = message.created_at
    # await channel.send(str(timestamp))
    now = datetime.now(timezone.utc)
    now = now.replace(tzinfo=None)
    time_since = now - timestamp
    time_since = time_since.total_seconds()
    timeout = int(readArchive(id, 2))
    return time_since > 60 * 60 * 24 * timeout
    # await channel.send(time_since)

@bot.command()
async def setTimeout(ctx):

    id = str(ctx.message.guild.id)


@tasks.loop(hours=24)
async def autoArchive():

    activeservers = bot.guilds
    for guild in activeservers:
        id = str(guild.id)
        for channel in guild.channels:
            if str(channel.type) == 'text':
                stale = await getLast(channel)
                if stale:
                    lastMessage = await channel.fetch_message(channel.last_message_id)
                    ctx = await bot.get_context(lastMessage)
                    archive = getCategory(readArchive(id, 1), ctx)
                    if archive == None:
                        # await ctx.message.channel.send("An archive category does not exist. Please use **a!setup** to create one.")
                        return
                    else:
                        await channel.edit(category=archive)

@bot.event
async def on_message(message):

    ctx = await bot.get_context(message)
    id = str(ctx.message.guild.id)

    try:
        archive = getCategory(readArchive(id, 1), ctx)

        # If the message is in a category and the category name is the archive and the message was sent by the user and the message is not a category name
        if message.channel.category != None and message.channel.category.name == archive.name and message.author != bot.user and getCategory(message.content, ctx) == None:

            await message.channel.send("This channel has been archived! Please name the channel you would like to move it back to.")

            def check(message):
                return isMessage(message) and getCategory(message.content, ctx) != None

            cat_name = (await bot.wait_for("message", check=check, timeout=60.0)).content
            await message.channel.edit(category=getCategory(cat_name, ctx))

            await message.channel.send("Channel restored to **" + cat_name.upper() + "**.")
        
        await bot.process_commands(message)
    
    except:

        await bot.process_commands(message)

autoArchive.start()
bot.run(TOKEN)

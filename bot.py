# Bot permissions: manage channels, view channels, send messages, read message history

import os
import discord
from dotenv import load_dotenv
from discord.ext import commands, tasks
import time
from datetime import datetime, timezone

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

activity = discord.Game(name="a!help")

bot = commands.Bot(command_prefix='a!', activity=activity)

bot.remove_command("help")


########## REGULAR FUNCTIONS ##########

# Return category object from string name
def getCategory(name, ctx):
    for category in ctx.message.guild.categories:
            if(category.name.lower() == name.lower()):
                return category
    return None

# Create file to record archive channels for each server if one does not exist
def makeFile():
    message_file_exists = os.path.isfile("archives.txt")
    if(not message_file_exists):
        f = open("archives.txt", "x")
        f.close()

# Get information about how Archie should behave in each server
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

# (Over)write information on how Archie should behave in each server
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
async def help(ctx):

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

    # Get archive category name
    await ctx.message.channel.send("What is the name of your archive category? (NOT case sensitive)")
    cat_name = (await bot.wait_for("message", check=isMessage, timeout=60.0)).content

    # Get timeout time
    await ctx.message.channel.send("After how many days should channels be archived? (Must be a full number)")
    timeout = (await bot.wait_for("message", check=isNumMessage, timeout=60.0)).content
    
    id = str(ctx.message.guild.id)
    if getCategory(cat_name, ctx) == None: # If the archive category does not yet exist, create it
        await ctx.message.channel.send("Category **" + cat_name + "** created.")
        category = await ctx.message.guild.create_category(cat_name)

    # Save information to archives.txt
    writeArchive(id, cat_name, timeout)
    
    await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive. Channels inactive for **" + timeout + "** days will be moved to **" + cat_name.upper() + "**.")

# Manually archive a channel
@bot.command()
async def archive(ctx):

    id = str(ctx.message.guild.id)

    # Get designated archive category
    archive = getCategory(readArchive(id, 1), ctx)
    if archive == None:
        await ctx.message.channel.send("An archive category does not exist. Please use **a!setup** to create one.")
    else:
        # Move to archive category
        await ctx.message.channel.edit(category=archive)
        await ctx.message.channel.send("This channel has been archived.")

# Get time since last message
async def getLast(channel):

    # Get last message
    message = await channel.fetch_message(channel.last_message_id)
    id = str(message.guild.id)
    timestamp = message.created_at

    # Get current time
    now = datetime.now(timezone.utc)
    now = now.replace(tzinfo=None)

    # Get time difference and convert to seconds
    time_since = now - timestamp
    time_since = time_since.total_seconds()

    # Retrieve timeout time and check if channel has timed out
    timeout = int(readArchive(id, 2))
    return time_since > 60 * 60 * 24 * timeout

@bot.command()
async def setTimeout(ctx):

    id = str(ctx.message.guild.id)


# Automatically archive inactive channels after 12 hours
@tasks.loop(hours=12)
async def autoArchive():

    # Run this in all of the servers Archie is active in
    activeservers = bot.guilds
    for guild in activeservers:

        id = str(guild.id)

        # Go through every text channel
        for channel in guild.channels:
            if str(channel.type) == 'text':
                inactive = await getLast(channel)
                if inactive:

                    # These two lines exist mainly to get the context
                    lastMessage = await channel.fetch_message(channel.last_message_id)
                    ctx = await bot.get_context(lastMessage)

                    # Get the archive category
                    archive = getCategory(readArchive(id, 1), ctx)
                    if archive == None:
                        # await ctx.message.channel.send("An archive category does not exist. Please use **a!setup** to create one.")
                        return
                    else:

                        # Move to archive category
                        await channel.edit(category=archive)

@bot.event
async def on_message(message):

    # Get context and current guild
    ctx = await bot.get_context(message)
    id = str(ctx.message.guild.id)

    try: # If an archive category exists
        archive = getCategory(readArchive(id, 1), ctx)

        # If the message is in a category and the category name is the archive and the message was sent by the user and the message is not a category name
        if message.channel.category != None and message.channel.category.name == archive.name and message.author != bot.user and getCategory(message.content, ctx) == None:

            await message.channel.send("This channel has been archived! Please name the channel you would like to move it back to.")

            def check(message): # Check if the mesage was not sent by Archie and that the message is an actual category
                return isMessage(message) and getCategory(message.content, ctx) != None

            # Get the category we want to restore the channel to and move channel
            cat_name = (await bot.wait_for("message", check=check, timeout=60.0)).content
            await message.channel.edit(category=getCategory(cat_name, ctx))

            await message.channel.send("Channel restored to **" + cat_name.upper() + "**.")
        
        await bot.process_commands(message) # Process commands
    
    except: # If an archive category doesn't exist, just process possible commands
        await bot.process_commands(message)

autoArchive.start() # Start 12-hour auto-archiver
bot.run(TOKEN)

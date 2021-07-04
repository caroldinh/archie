# Bot permissions: manage channels, view channels, send messages, read message history

import os
import discord
from dotenv import load_dotenv
from discord.ext import commands, tasks
from discord.ext.commands import has_permissions, MissingPermissions
import time
from datetime import datetime, timezone
import psycopg2
from psycopg2 import OperationalError
import asyncio

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
# DATABASE_URL = os.getenv('DATABASE_URL')

activity = discord.Game(name="a!help | v.2.1.6")

bot = commands.Bot(command_prefix='a!', activity=activity)

connection = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')

bot.remove_command("help")

# Return category object from string name
def getCategory(name, ctx):
    for category in ctx.message.guild.categories:
            if(category.name.lower() == name.lower()):
                return category
    return None

async def getLogChannel(id):
    guild = bot.get_guild(id)
    for channel in guild.channels:
        if(channel.name == "archie-logs"):
                return channel
    channel = await guild.create_text_channel('archie-logs')
    return channel

def isMessage(message):
    return message.author != bot.user

def isNumMessage(message):
    return isMessage(message) and message.content.isnumeric()

async def getTimeSince(message):

    id = message.guild.id
    timestamp = message.created_at

    # Get current time
    now = datetime.now(timezone.utc)
    now = now.replace(tzinfo=None)

    # Get time difference and convert to seconds
    time_since = now - timestamp
    time_since = time_since.total_seconds()

    return time_since

async def daysSinceActive(channel):

    # Get last message
    if channel.last_message_id == None: # If there are no messages in channel
        return 0

    message = await channel.fetch_message(channel.last_message_id)
    
    time_since = int((await getTimeSince(message) / (60 * 60 * 24)))

    return time_since

# Get time since last message
async def checkTimedOut(channel, timeout):

    days_since = await daysSinceActive(channel)
    return days_since > timeout

def execute_query(connection, query):
    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute(query)
        print("Query executed successfully")
    except OperationalError as e:
        print(f"The error '{e}' occurred")

def execute_read_query(connection, query):
    cursor = connection.cursor()
    result = None
    try:
        cursor.execute(query)
        result = cursor.fetchall()
        return result
    except OperationalError as e:
        print(f"The error '{e}' occurred")

def addServer(id, category, timeout):

    create_servers_table = """
    CREATE TABLE IF NOT EXISTS servers (
    id BIGINT PRIMARY KEY,
    archive TEXT NOT NULL, 
    timeout INTEGER,
    permanent_categories TEXT,
    permanent_channels TEXT,
    delete_time INTEGER
    )
    """

    execute_query(connection, create_servers_table)

    servers = [(id, category, timeout, "", "", -1)]

    insert_query = (
        f"INSERT INTO servers (id, archive, timeout, permanent_categories, permanent_channels) VALUES ({id}, '{category}', {timeout}, '', '', -1)"
    )

    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute(insert_query, servers)
    except:
        updateServer(id, "archive", f"'{category}'")
        updateServer(id, "timeout", timeout)

def readServer(id):

    select_server = (f"SELECT * FROM servers WHERE id={id}")
    server = execute_read_query(connection, select_server)

    # print(server)

    if(len(server) > 0):
        return server[0]       # Returns a tuple where server[0] = id, server[1] = archive channel, server[2] = timeout, 
                                # server[3] = permanent categories, server[4] = permanent channels, server[5] = deletion time
    else:
        return None

def updateServer(id, key, newValue):

    update_server = (f"""
        UPDATE servers
        SET {key} = {newValue}
        WHERE id = {id}
    """)

    execute_query(connection,  update_server)


########## BOT FUNCTIONS ##########

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await autoArchive()
    print("Autoarchive done")

@bot.command()
async def help(ctx):

    descrip = "Hi there! :wave: I'm Archie, a Discord bot that archives inactive channels.\n\n" + \
        "After you set me up, I will check on your server every day and archive channels that haven't been active for a while.\n\n" + \
        "All of this is automatic, so you don't have to worry about calling on me too often, but here are some commands you can use yourself."
    embed = discord.Embed(title="Archie", description=descrip, color=0xff4912)
    embed.add_field(name="a!config", value=":open_file_folder: Set archive category and channel timeout.", inline=False)
    embed.add_field(name="a!archive (a!arch)", value=":open_file_folder: Manually archive the current channel.", inline=False)
    embed.add_field(name="a!set <CATEGORY NAME>", value=":open_file_folder: Set the archive category. Ex: a!set archive", inline=False)
    embed.add_field(name="a!timeout <TIME (DAYS)>", value=":open_file_folder: Set the channel timeout. Ex: a!timeout 30", inline=False)
    embed.add_field(name="a!limit", value=":open_file_folder: Limit which categories and channels can be automatically archived.", inline=False)
    embed.add_field(name="a!deleteafter <TIME (DAYS)>", value=":open_file_folder: Delete archived channels after they have been inactive for a set amount of time.", inline=False)
    # embed.add_field(name="a!categories", value=" - List all categories in server.", inline=False)
    embed.add_field(name="a!help", value=":open_file_folder: Display the help menu.\n\n" + \
        "You can restore an archived channel simply by sending a message in it.", inline=False)

    await ctx.message.channel.send(embed=embed)

async def getCatList(ctx):

    id = ctx.message.guild.id

    catList = []
    catDisplay = []
    count = 1
    archive = readServer(id)[1]
    for category in ctx.message.guild.categories:
        if category.name != archive: # Exclude the archive category
            catDisplay.append(f"[{count}] {category.name.upper()}")
            catList.append(category.name)
            count += 1
    return [catList, catDisplay]

async def inputCat(ctx):

    id = ctx.message.guild.id

    # Get list of all categories
    result = await getCatList(ctx)
    catList = result[0]
    catDisplay = result[1]
    
    # Display this in an embed
    descrip = f"Enter a number 1-{len(catList)}.\n\n" + "\n".join(catDisplay)
    embed = discord.Embed(title="Categories", description=descrip, color=0xff4912)
    await ctx.message.channel.send(embed=embed)

    # Get input from user
    def check(message):
        return isNumMessage(message) and int(message.content) > 0 and int(message.content) <= len(catList)

    try:
        cat_num = int((await bot.wait_for("message", check=check, timeout=20.0)).content)
        if cat_num:
            return catList[cat_num - 1]
    except asyncio.TimeoutError:
        await ctx.message.channel.send("Sorry, you took too long!")
        return None

async def inputCatList(ctx):

    id = ctx.message.guild.id

    # Get list of all categories
    result = await getCatList(ctx)
    catList = result[0]
    catDisplay = result[1]
    
    # Display this in an embed
    descrip = f"Enter list of numbers 1-{len(catList)} separated by spaces, i.e., \"1 2 3\".\n\n" + "\n".join(catDisplay)
    embed = discord.Embed(title="Categories", description=descrip, color=0xff4912)
    await ctx.message.channel.send(embed=embed)

    # print(catList)

    # Get input from user
    def check(message):
        message = message.content.split()
        for m in message:
            # print(m)
            if(not(m.isnumeric() and int(m) > 0 and int(m) <= len(catList))):
                return False
        return True

    try:
        cats = (await bot.wait_for("message", check=check, timeout=20.0)).content
        cats = cats.split()
        categories = []
        for c in cats:
            categories.append(catList[int(c) - 1])
        # print(categories)
        return categories
    except asyncio.TimeoutError:
        await ctx.message.channel.send("Sorry, you took too long!")
        return None

@bot.command()
@has_permissions(manage_guild=True)
async def config(ctx):

    # Get archive category name
    await ctx.message.channel.send("What is the name of your archive category? (NOT case sensitive)")
    try:
        cat_name = (await bot.wait_for("message", check=isMessage, timeout=20.0)).content

        # Get timeout time
        await ctx.message.channel.send("After how many days should channels be archived? (Must be a full number)")
        timeout = (await bot.wait_for("message", check=isNumMessage, timeout=20.0)).content
        
        id = ctx.message.guild.id
        if getCategory(cat_name, ctx) == None: # If the archive category does not yet exist, create it
            await ctx.message.channel.send("Category **" + cat_name + "** created.")
            category = await ctx.message.guild.create_category(cat_name)

        # Save information to archives.txt
        # writeArchive(id, cat_name, timeout)
        addServer(id, cat_name, timeout)
        
        await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive. Channels inactive for **" + timeout + "** days will be moved to **" + cat_name.upper() + "**.")
    
    except asyncio.TimeoutError:
        await ctx.message.channel.send("Sorry, you took too long!")
        return None

@bot.command()
@has_permissions(manage_guild=True)
async def set(ctx, cat_name):
    id = ctx.message.guild.id
    updateServer(id, "archive", f"'{cat_name}'")
    await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive.")

@bot.command()
@has_permissions(manage_guild=True)
async def timeout(ctx, timeout):
    id = ctx.message.guild.id
    updateServer(id, "timeout", timeout)
    await ctx.message.channel.send(f"Channels inactive for **{timeout}** days will be archived.")

@bot.command()
@has_permissions(manage_guild=True)
async def limit(ctx):

    id = ctx.message.guild.id

    await ctx.message.channel.send("List which categories should NOT be automatically archived.")

    cats = await inputCatList(ctx)
    if cats:
        cats = "\n".join(cats)
        updateServer(id, "permanent_categories", f"'{cats}'")
        await ctx.message.channel.send(f"The following categories will NOT be automatically archived:\n**{cats.upper()}**")

# Manually archive a channel
@bot.command()
@has_permissions(manage_guild=True)
async def archive(ctx):

    id = ctx.message.guild.id
    # print("Archiving...")

    # Get designated archive category
    archive = getCategory(readServer(id)[1], ctx)
    if archive == None:
        await ctx.message.channel.send("An archive category does not exist. Please use **a!setup** to create one.")
    else:
        # Move to archive category if there is space in the archive
        if(len(archive.channels) < 50):
            await ctx.message.channel.edit(category=archive)
            await ctx.message.channel.send("This channel has been archived.")
        else:
           await ctx.message.channel.send(f"Your archive channel **{archive.name.upper()}** is full. Please make space in your archive or create a new one.")

# Shortened version of archive
@bot.command()
@has_permissions(manage_guild=True)
async def arch(ctx):
    await archive(ctx)

'''
# Empty archive
@bot.command()
@has_permissions(manage_guild=True)
async def empty(ctx, days):
    await archive(ctx)
'''
@bot.command()
@has_permissions(manage_guild=True)
async def deleteafter(ctx, days):
    id = ctx.message.guild.id
    timeout = readServer(id)[2]
    if(int(days) >= timeout + 7):
        updateServer(id, "delete_time", int(days))
        await ctx.message.channel.send(f"Archived channels inactive for **{days}** days will be deleted.")
    else:
        await ctx.message.channel.send(f"Deletion time must be greater than {timeout+7}.")


@config.error
@archive.error
@set.error
@timeout.error
@limit.error
@deleteafter.error
async def permissions_error(ctx, error):
    if isinstance(error, MissingPermissions):
        await ctx.message.channel.send("You don't have permission to do this!")

# Automatically archive inactive channels after 24 hours
# @tasks.loop(hours=24)
async def autoArchive():

    # Update connection in case DATABASE_URL changed
    connection = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')

    # Run this in all of the servers Archie is active in
    activeservers = bot.guilds
    for guild in activeservers:

        id = guild.id
        archive = 0
        server = readServer(id)
        archiveIsFull = False

        logChannel = None

        if(guild.system_channel):
            logChannel = guild.system_channel
        else:
            logChannel = await getLogChannel(id)

        if(server != None and len(server) > 1): # If that server is in the database

            permanent_categories = server[3].split("\n")
            timeout = server[2]
            delete_time = server[5]

            error = False

            # Go through every text channel
            for channel in guild.channels:
               
                try:
                    if(not archiveIsFull and str(channel.type) == 'text' and (channel.category == None or not (channel.category.name in permanent_categories))):

                        if(channel.category != None and channel.category.name == server[1]):
                            if(delete_time != None and delete_time > timeout): # Check if a delete time has been set

                                days_since = await daysSinceActive(channel) # Check days since last active
                                
                                if days_since + 2 >= delete_time:
                                
                                    if days_since >= delete_time:
                                        await channel.delete()
                                        # pass
                                    
                                    else:
                                        days_until = delete_time - days_since
                                        await logChannel.send(f"**{channel.name}** (<#{channel.id}>) will be deleted in **{days_until} day(s)** if it remains inactive.")
                            else:
                                print("Delete time not set")
                        
                        else: 
                            inactive = await checkTimedOut(channel, timeout)
                            if inactive:

                                # These two lines exist mainly to get the context
                                lastMessage = await channel.fetch_message(channel.last_message_id)
                                ctx = await bot.get_context(lastMessage)

                                # Get the archive category. If there is no archive category, nothing happens.
                                if archive == 0:
                                    archive = getCategory(server[1], ctx)

                                if archive != None:
                                    # Move to archive category
                                    if(len(archive.channels) < 50): # Unless the archive category is full
                                        await channel.edit(category=archive)
                                    else:
                                        archiveIsFull = True
                except Exception as e:
                    if not error:
                        await logChannel.send("Error in auto-archiving channels.")
                        error = True
                    print(e)
            
            if archiveIsFull:
                    logChannel.send(f"Your archive channel **{archive.name.upper()}** is full. Please make space in your archive or create a new one.")


@bot.event
async def on_message(message):

    # Update connection in case DATABASE_URL changed
    connection = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')

    # Get context and current guild
    ctx = await bot.get_context(message)
    id = ctx.message.guild.id

    try: # If an archive category exists
        archive = getCategory(readServer(id)[1], ctx)

        history = await ctx.message.channel.history(limit=2).flatten()
        previous_message = history[1]
        print(previous_message)

        # If the message is in a category and 
        # the category name is the archive and 
        # the message was sent by the user and 
        # the message is not a response to the bot 
            # assuming the response has not timed out

        if message.channel.category != None and \
        message.channel.category.name == archive.name and \
        message.author != bot.user and \
        (previous_message.author != bot.user or \
        await getTimeSince(previous_message) >= 20):

            await message.channel.send("This channel has been archived! Which category would you like to restore it to?")

            # Get the category we want to restore the channel to and move channel
            cat_name = await inputCat(ctx)
            if cat_name:
                await message.channel.edit(category=getCategory(cat_name, ctx))
                await message.channel.send("Channel restored to **" + cat_name.upper() + "**.")
        
        await bot.process_commands(message) # Process commands
    
    except: # If an archive category doesn't exist, just process possible commands
        await bot.process_commands(message)

# autoArchive.start() # Start 24-hour auto-archiver
bot.run(TOKEN)
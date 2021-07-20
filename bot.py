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

activity = discord.Game(name="a!help | v.2.2.2")

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

    # execute_query(connection, create_servers_table)

    servers = [(id, category, timeout)]

    insert_query = (
        f"INSERT INTO servers (id, archive, timeout) VALUES ({id}, '{category}', {timeout})"
    )

    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute(insert_query, servers)
    except:
        updateServer(id, archive=f"'{category}'", timeout=timeout)

def readServer(id):

    select_server = (f"SELECT * FROM servers WHERE id={id}")
    connection = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
    server = execute_read_query(connection, select_server)

    # print(server)

    if(len(server) > 0):
        return server[0]       # Returns a tuple where server[0] = id, server[1] = archive channel, server[2] = timeout, 
                                # server[3] = permanent categories, server[4] = permanent channels (not yet used), server[5] = deletion time
    else:
        return None

def updateServer(id, **kwargs):

    update_server = "UPDATE servers\nSET "
    count = 0

    for key in kwargs:
        update_server += f"{key} = {kwargs.get(key)}"
        count += 1
        if(count == len(kwargs)):
            update_server += "\n"
        else:
            update_server += ",\n"

    update_server += f"WHERE id = {id}"
    connection = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
    execute_query(connection, update_server)


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
        "All of this is automatic, so you don't have to worry about calling on me too often, but here are some commands you can use yourself.\n\n" + \
        "Run **a!config** to get started.\n\n"
    embed = discord.Embed(title="Archie", description=descrip, color=0xff4912)
    embed.add_field(name="`a!config`", value=":open_file_folder: Configure Archie on your server. You may also run `a!config <CATEGORY NAME> <TIME (DAYS)>` as a shortcut.", inline=False)
    embed.add_field(name="`a!archive`", value=":open_file_folder: Manually archive the current channel. Type 'readonly' at the end of the command to make the channel read-only, i.e. `a!archive readonly`.", inline=False)
    embed.add_field(name="`a!set <CATEGORY NAME>`", value=":open_file_folder: Set the archive category. Ex: a!set archive", inline=False)
    embed.add_field(name="`a!timeout <TIME (DAYS)>`", value=":open_file_folder: Set the channel timeout. Ex: a!timeout 30", inline=False)
    embed.add_field(name="`a!freeze`", value=":open_file_folder: 'Freeze' categories to prevent Archie from modifying them automatically.", inline=False)
    embed.add_field(name="`a!delete <TIME (DAYS)>`", value=":open_file_folder: Delete archived channels after they have been inactive for a set amount of time. Read-only channels cannot be automatically deleted.", inline=False)
    embed.add_field(name="`a!lock`", value=":open_file_folder: Make an archived channel read-only. Can be reversed with `a!unlock`.", inline=False)
    embed.add_field(name="`a!info`", value=":open_file_folder: Display the configurations for this server.", inline=False)
    # embed.add_field(name="a!categories", value=" - List all categories in server.", inline=False)
    embed.add_field(name="`a!help`", value=":open_file_folder: Display the help menu.\n\n" + \
        "You can restore an archived channel simply by sending a message in it.", inline=False)

    await ctx.message.channel.send(embed=embed)

async def getCatList(ctx, exclude_frozen):

    id = ctx.message.guild.id

    catList = []
    catDisplay = []
    count = 1
    server = readServer(id)
    archive = server[1]
    if(exclude_frozen):
        frozen = server[3]
        if(frozen == None):
            frozen = []
        else:
            frozen = frozen.split("\n")
    else:
        frozen = []
    for category in ctx.message.guild.categories:
        if category.name != archive and not category.name in frozen: # Exclude the archive category and frozen categories
            catDisplay.append(f"[{count}] {category.name.upper()}")
            catList.append(category.name)
            count += 1
    return [catList, catDisplay]

async def inputCat(ctx, exclude_frozen=False):

    id = ctx.message.guild.id

    # Get list of all categories
    result = await getCatList(ctx, exclude_frozen)
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

async def inputCatList(ctx, exclude_frozen=False):

    id = ctx.message.guild.id

    # Get list of all categories
    result = await getCatList(ctx, exclude_frozen)
    catList = result[0]
    catDisplay = result[1]
    
    # Display this in an embed
    descrip = f"Enter list of numbers 1-{len(catList)} separated by spaces, i.e., \"1 2 3\", or type \"0\" to select nothing.\n\n" + "\n".join(catDisplay)
    embed = discord.Embed(title="Categories", description=descrip, color=0xff4912)
    await ctx.message.channel.send(embed=embed)

    # print(catList)

    # Get input from user
    def check(message):
        message = message.content.split()
        for m in message:
            #print(m)
            if(not(m.isnumeric() and int(m) >= 0 and int(m) <= len(catList))):
                # print("False")
                return False
        return True

    try:
        cats = (await bot.wait_for("message", check=check, timeout=20.0)).content
        cats = cats.split()
        categories = []
        # print("Len:",len(cats))
        if(len(cats) == 1 and int(cats[0]) == 0):
            # print("0")
            return []
        for c in cats:
            if(int(c) != 0):
                categories.append(catList[int(c) - 1])
        # print(categories)
        return categories
    except asyncio.TimeoutError:
        await ctx.message.channel.send("Sorry, you took too long!")
        return None

@bot.command()
@has_permissions(manage_guild=True)
async def config(ctx, *args):

    if(len(args) == 0):
        # Get archive category name
        await ctx.message.channel.send("What is the name of your archive category? (NOT case sensitive)")
        try:
            cat_name = (await bot.wait_for("message", check=isMessage, timeout=20.0)).content

            # Get timeout time
            await ctx.message.channel.send("After how many days should channels be archived? (Must be a full number)")
            timeout = (await bot.wait_for("message", check=isNumMessage, timeout=20.0)).content
            
            id = ctx.message.guild.id
            if getCategory(cat_name, ctx) == None: # If the archive category does not yet exist, create it
                await ctx.message.channel.send("Category **" + cat_name.upper() + "** created.")
                category = await ctx.message.guild.create_category(cat_name)

            # Save information to archives.txt
            # writeArchive(id, cat_name, timeout)
            addServer(id, cat_name, timeout)
            
            await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive. Channels inactive for **" + timeout + "** days will be moved to **" + cat_name.upper() + "**.")
        
        except asyncio.TimeoutError:
            await ctx.message.channel.send("Sorry, you took too long!")
            return None

        except Exception as e:
            print(e)

    elif(len(args) == 2):

        cat_name = args[0]
        timeout = args[1]
        id = ctx.message.guild.id
        if getCategory(cat_name, ctx) == None: # If the archive category does not yet exist, create it
            await ctx.message.channel.send("Category **" + cat_name.upper() + "** created.")
            category = await ctx.message.guild.create_category(cat_name)
        try:
            addServer(id, cat_name, timeout)
            await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive. Channels inactive for **" + timeout + "** days will be moved to **" + cat_name.upper() + "**.")
        except Exception as e:
            print(e)
    else:
        await ctx.message.channel.send("a!config takes either 0 arguments or 2. Example: `a!config archive 30` sets ARCHIVE as the archive category and 30 as the timeout in days. If you are unsure, `a!config` will walk you through the setup.")



@bot.command()
@has_permissions(manage_guild=True)
async def set(ctx, cat_name):
    id = ctx.message.guild.id
    if getCategory(cat_name, ctx) == None: # If the archive category does not yet exist, create it
        await ctx.message.channel.send("Category **" + cat_name.upper() + "** created.")
        category = await ctx.message.guild.create_category(cat_name)
    updateServer(id, archive=f"'{cat_name}'")
    await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive.")

@bot.command()
@has_permissions(manage_guild=True)
async def timeout(ctx, timeout):
    id = ctx.message.guild.id
    updateServer(id, "timeout", timeout)
    await ctx.message.channel.send(f"Channels inactive for **{timeout}** days will be archived.")

@bot.command()
@has_permissions(manage_guild=True)
async def lock(ctx):
    id = ctx.message.guild.id
    if(getCategory(readServer(id)[1], ctx) == ctx.message.channel.category):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.message.channel.send("This channel has been locked.")
    else:
        await ctx.message.channel.send("`a!lock` can only be run on archived channels.")

@bot.command()
@has_permissions(manage_guild=True)
async def unlock(ctx):
    overwrite = ctx.message.channel.overwrites_for(ctx.message.guild.default_role)
    if(overwrite.send_messages == False):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.message.channel.send("This channel has been unlocked.")
    else:
        await ctx.message.channel.send("This channel is already unlocked.")

@bot.command()
@has_permissions(manage_guild=True)
async def freeze(ctx):

    id = ctx.message.guild.id

    await ctx.message.channel.send("List which categories to freeze.")

    cats = await inputCatList(ctx)
    if cats != []:
        cats = "\n".join(cats)
        updateServer(id, permanent_categories=f"'{cats}'")
        await ctx.message.channel.send(f"The following categories will NOT be automatically modified by Archie (you may still manually archive channels in this category using `a!arch`):\n**{cats.upper()}**")
    else:
        # print("Setting to none")
        updateServer(id, permanent_categories='NULL')
        await ctx.message.channel.send(f"No categories were selected. All categories may now be automatically modified by Archie.")

@bot.command(aliases=['stats', 'data'])
async def info(ctx):
    id = ctx.message.guild.id
    server = readServer(id)

    if(server == None):
        print("None")
        server = ["None", "None", "None", "None", "None", "None"]

    embed = discord.Embed(title=f"Archie Configuration Information", description=f"Archie's configuration info for **{ctx.message.guild.name}.**", color=0xff4912)
    embed.add_field(name="`Archive`", value=f"{server[1]}\n*- Archived channels are moved to the category **{server[1].upper()}**.*", inline=False)
    embed.add_field(name="`Archive Timeout`", value=f"{server[2]}\n*- Channels are archived after **{server[2]} days** of inactivity.*", inline=False)
    embed.add_field(name="`Deletion Timeout`", value=f"{server[5]}\n*- Channels are deleted from the archive after **{server[5]} days** of inactivity.*", inline=False)
    embed.add_field(name="`Frozen`", value=f"{server[3]}\n*- These categories cannot be modified.*\n\nIf any value is 'None', that means you have not configured it yet.", inline=False)

    await ctx.message.channel.send(embed=embed)


# Manually archive a channel
@bot.command(aliases=['arch'])
@has_permissions(manage_guild=True)
async def archive(ctx, readonly=None):

    print(readonly)
    if str(readonly).lower() == "readonly":
        readonly = True

    id = ctx.message.guild.id
    # print("Archiving...")

    # Get designated archive category
    archive = getCategory(readServer(id)[1], ctx)
    if archive == None:
        await ctx.message.channel.send("An archive category does not exist. Please use **a!config** to create one.")
    else:
        # Move to archive category if there is space in the archive
        if(len(archive.channels) < 50):
            await ctx.message.channel.edit(category=archive)
            await ctx.message.channel.send("This channel has been archived.")
            if(readonly == True):
                await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
                await ctx.message.channel.send("This channel is now read-only.")
        else:
           await ctx.message.channel.send(f"Your archive channel **{archive.name.upper()}** is full. Please make space in your archive or create a new one.")

@bot.command()
@has_permissions(manage_guild=True)
async def delete(ctx, days):
    id = ctx.message.guild.id
    timeout = readServer(id)[2]
    if(int(days) >= timeout + 7):
        updateServer(id, delete_time=int(days))
        await ctx.message.channel.send(f"Archived channels inactive for **{days}** days will be deleted.")
    else:
        await ctx.message.channel.send(f"Deletion time must be greater than {timeout+7}.")


@config.error
@archive.error
@set.error
@timeout.error
@freeze.error
@delete.error
@lock.error
@unlock.error
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

            permanent_categories = server[3]
            if permanent_categories:
                permanent_categories = permanent_categories.split("\n")
            else:
                permanent_categories = []
            timeout = server[2]
            delete_time = server[5]

            error = False

            # Go through every text channel
            for channel in guild.channels:
               
                try:    # If the channel is in a text channel that is not frozen
                    if(str(channel.type) == 'text' and (channel.category == None or not (channel.category.name in permanent_categories))):

                        # Code to delete inactive channels
                        overwrite = channel.overwrites_for(guild.default_role)
                        if(channel.category != None and channel.category.name == server[1] and overwrite.send_messages == True): # If the channel is in the archive and is not readonly
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
                        
                        # Code to archive inactive channels if channel is not full
                        elif not archiveIsFull: 
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
        #print(previous_message)

        # If the message is in a category and 
        # the category name is the archive and 
        # the message was sent by the user and
        # the message is not a response to the bot (if the user sends a message after the bot, the message must not be a question or an embed)
        # or, if it is a response to the bot, the question has timed out
        # And the message is not a command

        # print(previous_message.embeds)

        previous_content = previous_message.content

        if(len(previous_message.embeds) != 0):
            previous_content = previous_message.embeds[0].description

        if message.channel.category != None and \
        message.channel.category.name == archive.name and \
        message.author != bot.user and \
        (previous_message.author != bot.user or 
        (previous_message.author == bot.user and not "?" in previous_content and not "enter" in previous_content.lower()) 
        or await getTimeSince(previous_message) >= 20) and \
        message.content[:2] != "a!":

            await message.channel.send("This channel has been archived! Which category would you like to restore it to?")

            # Get the category we want to restore the channel to and move channel
            cat_name = await inputCat(ctx, True)
            if cat_name:
                await message.channel.edit(category=getCategory(cat_name, ctx))
                await message.channel.send("Channel restored to **" + cat_name.upper() + "**.")
            
            overwrite = message.channel.overwrites_for(message.guild.default_role)
            if(overwrite.send_messages == False):
                await message.channel.send("Run `a!unlock` to unlock this channel.")
        
        await bot.process_commands(message) # Process commands
    
    except: # If an archive category doesn't exist, just process possible commands
        await bot.process_commands(message)

# autoArchive.start() # Start 24-hour auto-archiver
bot.run(TOKEN)
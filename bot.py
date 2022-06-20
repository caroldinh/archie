# Bot permissions: manage channels, view channels, send messages, read message history - value: 68624

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
from psycopg2 import sql


DEBUG = os.getenv('DEBUG')

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
# DATABASE_URL = os.getenv('DATABASE_URL')

activity = discord.Game(name="a!help | v.2.3.0")

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

def getTimeSince(message):

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
    
    time_since = int((getTimeSince(message) / (60 * 60 * 24)))

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

    if timeout:
        server = [id, category, timeout]
        insert_query = "INSERT INTO servers (id, archive, timeout) VALUES (%s, %s, %s)"
    else:
        server = [id, category]
        insert_query = "INSERT INTO servers (id, archive, timeout) VALUES (%s, %s, NULL)"

    print(insert_query)

    connection = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute(insert_query, server)
    except Exception as e:
        print(f"The error '{e}' occurred")
        updateServer(id, archive=category, timeout=timeout)

def readServer(id):

    select_server = (f"SELECT * FROM servers WHERE id={id}")
    connection = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
    server = execute_read_query(connection, select_server)

    if(len(server) > 0):
        return server[0]       # Returns a tuple where server[0] = id, server[1] = archive channel, server[2] = timeout, 
                                # server[3] = permanent categories, server[4] = permanent channels (not yet used), server[5] = deletion time
    else:
        return None

def updateServer(id, **kwargs):

    update_server = "UPDATE servers\nSET "
    count = 0

    connection = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')

    new_values = []
    
    for key in kwargs:
    
        if(key == "archive"):
            update_server += "archive = %s"
        elif(key=="timeout"):
            if(kwargs.get(key) != 'NULL'):
                update_server += "timeout = %s"
            else:
                update_server += "timeout = NULL"
        elif(key=="permanent_categories"):
            if(kwargs.get(key) != 'NULL'):
                update_server += "permanent_categories = %s"
            else:
                update_server += "permanent_categories = NULL"
        elif(key=="delete_time"):
            if(kwargs.get(key) != 'NULL'):
                update_server += "delete_time = %s"
            else:
                update_server += "delete_time = NULL"

        new_values.append(kwargs.get(key))

        count += 1
        if(count == len(kwargs)):
            update_server += "\n"
        else:
            update_server += ",\n"

    update_server += f"WHERE id = {id}"

    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute(update_server, new_values)
        print("Query executed successfully")
    except OperationalError as e:
        print(f"The error '{e}' occurred")

async def clearMessages(ctx, delete_from, delete_until):

    print("Starting clear")
    if (delete_from == None):
        history = await ctx.message.channel.history(limit=1).flatten()
        if(len(history) > 0):
            delete_from = history[0]

    # Wait 3 seconds before starting to delete
    await asyncio.sleep(3)
    start_found = False
    previous_message = -1
    messages_to_skip = 0
    
    while (previous_message != None and previous_message != delete_until):
        history = await ctx.message.channel.history(limit=(1 + messages_to_skip)).flatten()
        if(len(history) > 0):
            previous_message = history[-1]
            if (not start_found and previous_message == delete_from):
                start_found = True
            elif (not start_found):
                messages_to_skip += 1
            if(getTimeSince(previous_message) > getTimeSince(delete_until)):
                previous_message = None
            else:
                if (start_found): # Do nothing until you've reached delete_from
                    await previous_message.delete()
        else:
            previous_message = None

async def clearSimple(ctx, message_count=2):
    history = await ctx.message.channel.history(limit=message_count).flatten()
    await asyncio.sleep(3)
    for message in history:
        await message.delete()

########## BOT FUNCTIONS ##########

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    if (not DEBUG):
        await autoArchive()
        print("Autoarchive done")

@bot.command()
async def help(ctx):

    descrip = "Hi there! :wave: I'm Archie, a Discord bot that archives inactive channels.\n\n" + \
        "After you set me up, I will check on your server every day and archive channels that haven't been active for a while.\n\n" + \
        "All of this is automatic, so you don't have to worry about calling on me too often, but here are some commands you can use yourself.\n\n" + \
        "Run **a!config** to get started.\n\n"
    embed = discord.Embed(title="Archie", description=descrip, color=0xff4912)
    embed.add_field(name="`a!config`", value=":open_file_folder: Configure Archie on your server. (`a!config <CATEGORY NAME>`, `a!config <TIME (DAYS)>`, and `a!config <CATEGORY NAME> <TIME (DAYS)>` are valid.)", inline=False)
    embed.add_field(name="`a!archive`", value=":open_file_folder: Manually archive the current channel. Type 'readonly' at the end of the command to make the channel read-only, i.e. `a!archive readonly`.", inline=False)
    embed.add_field(name="`a!freeze`", value=":open_file_folder: 'Freeze' categories to prevent Archie from modifying them automatically.", inline=False)
    embed.add_field(name="`a!delete <TIME (DAYS)>`", value=":open_file_folder: Delete archived channels after they have been inactive for a set amount of time. `a!delete 0` removes the deletion timeout. Read-only channels cannot be automatically deleted.", inline=False)
    embed.add_field(name="`a!lock`", value=":open_file_folder: Make an archived channel read-only. Can be reversed with `a!unlock`.", inline=False)
    embed.add_field(name="`a!info`", value=":open_file_folder: Display the configurations for this server.", inline=False)
    # embed.add_field(name="a!categories", value=" - List all categories in server.", inline=False)
    embed.add_field(name="`a!help`", value=":open_file_folder: Display the help menu.\n\n" + \
        "You can restore an archived channel simply by sending a message in it.\n\n" + \
        "For more information, visit Archie on Top.gg: https://top.gg/bot/857027766976118806", inline=False)

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

    # Get input from user
    def check(message):
        message = message.content.split()
        for m in message:
            if(not(m.isnumeric() and int(m) >= 0 and int(m) <= len(catList))):
                return False
        return True

    try:
        cats = (await bot.wait_for("message", check=check, timeout=20.0)).content
        cats = cats.split()
        categories = []
        if(len(cats) == 1 and int(cats[0]) == 0):
            return []
        for c in cats:
            if(int(c) != 0):
                categories.append(catList[int(c) - 1])
        return categories
    except asyncio.TimeoutError:
        await ctx.message.channel.send("Sorry, you took too long!")
        return None
    

@bot.command()
@has_permissions(manage_guild=True)
async def config(ctx, *args):

    if(len(args) == 0):
        # Get archive category name
        delete_until = await ctx.message.channel.send("What is the name of your archive category? (NOT case sensitive)")
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
            await updateDeleteTime(ctx)

        except asyncio.TimeoutError:
            await ctx.message.channel.send("Sorry, you took too long!")
            return None

        except Exception as e:
            print(e)

    elif(len(args) == 1):

        arg = args[0]
        id = ctx.message.guild.id

        if(arg.isnumeric()):
            if(readServer(id) == None):
                await ctx.message.channel.send("Please set an archive category before setting a timeout.")
                await clearSimple(ctx)
            else:
                arg = int(arg)
                await setTimeout(ctx, arg)
                await updateDeleteTime(ctx)
        else:
            if(readServer(id) == None):
                addServer(id, arg, None)
            await setArchive(ctx, arg)

    elif(len(args) == 2):

        cat_name = args[0]
        timeout = args[1]

        if(not timeout.isnumeric()):
            await ctx.message.channel.send("Your second argument must be a number.")
            await clearSimple(ctx)
        else:
            timeout = str(int(timeout))
            id = ctx.message.guild.id
            if getCategory(cat_name, ctx) == None: # If the archive category does not yet exist, create it
                await ctx.message.channel.send("Category **" + cat_name.upper() + "** created.")
                category = await ctx.message.guild.create_category(cat_name)
            try:
                addServer(id, cat_name, timeout)
                await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive. Channels inactive for **" + timeout + "** days will be moved to **" + cat_name.upper() + "**.")
                await updateDeleteTime(ctx)
            except Exception as e:
                print(e)
    else:
        await ctx.message.channel.send("a!config takes either 0 arguments or 2. Example: `a!config archive 30` sets ARCHIVE as the archive category and 30 as the timeout in days. If you are unsure, `a!config` will walk you through the setup.")
        await clearSimple(ctx)

async def updateDeleteTime(ctx):
    id = ctx.message.guild.id
    server = readServer(id)
    timeout = server[2]
    delete_time = server[5]
    if(delete_time and delete_time < timeout + 7):
        updateServer(id, delete_time=(timeout+7))
        await ctx.message.channel.send(f"Deletion timeout changed from **{delete_time}** to **{timeout+7}**. Use `a!delete` to update.")

async def setArchive(ctx, cat_name):
    id = ctx.message.guild.id
    if getCategory(cat_name, ctx) == None: # If the archive category does not yet exist, create it
        await ctx.message.channel.send("Category **" + cat_name.upper() + "** created.")
        category = await ctx.message.guild.create_category(cat_name)
    updateServer(id, archive=cat_name)
    await ctx.message.channel.send("Category **" + cat_name.upper() + "** set as server archive.")

async def setTimeout(ctx, timeout):
    id = ctx.message.guild.id
    updateServer(id, timeout=timeout)
    await ctx.message.channel.send(f"Channels inactive for **{timeout}** days will be archived.")

# @bot.command()
@has_permissions(manage_guild=True)
async def pin(ctx):
    bot_member = ctx.message.guild.get_member(bot.user.id)
    bot_role = bot_member.roles[0]
    if(not bot_role.is_bot_managed()):
        for role in bot_member.roles:
            if(role.is_bot_managed()):
                bot_role = role
    permissions = ctx.message.channel.overwrites_for(bot_role)
    permissions.manage_channels=False
    await ctx.channel.set_permissions(bot.user, overwrite=permissions)
    await ctx.message.channel.send("This channel can no longer be automatically archived.")

@bot.command()
@has_permissions(manage_channels=True)
async def lock(ctx):
    id = ctx.message.guild.id
    if(getCategory(readServer(id)[1], ctx) == ctx.message.channel.category):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
        await ctx.message.channel.send("This channel has been locked.")
    else:
        await ctx.message.channel.send("`a!lock` can only be run on archived channels.")
        await clearSimple(ctx)

@bot.command()
@has_permissions(manage_channels=True)
async def unlock(ctx):
    overwrite = ctx.message.channel.overwrites_for(ctx.message.guild.default_role)
    if(overwrite.send_messages == False):
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
        await ctx.message.channel.send("This channel has been unlocked.")
    else:
        await ctx.message.channel.send("This channel is already unlocked.")
        await clearSimple(ctx)

@bot.command()
@has_permissions(manage_guild=True)
async def freeze(ctx):

    id = ctx.message.guild.id

    delete_until = await ctx.message.channel.send("List which categories to freeze.")

    cats = await inputCatList(ctx)
    if cats != []:
        cats = "\n".join(cats)
        updateServer(id, permanent_categories=cats)

        await clearMessages(ctx, None, delete_until)
        await ctx.message.channel.send(f"The following categories will NOT be automatically modified by Archie (you may still manually archive channels in this category using `a!arch`):\n**{cats.upper()}**")
    else:
        updateServer(id, permanent_categories='NULL')
        await clearMessages(ctx, None, delete_until)
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
@has_permissions(manage_channels=True)
async def archive(ctx, readonly=None):

    if str(readonly).lower() == "readonly":
        readonly = True

    id = ctx.message.guild.id

    # Get designated archive category
    archive = getCategory(readServer(id)[1], ctx)
    if archive == None:
        await ctx.message.channel.send("An archive category does not exist. Please use **a!config** to create one.")
        await clearSimple(ctx)
    else:
        # Move to archive category if there is space in the archive
        if(len(archive.channels) < 50):
            await ctx.message.channel.edit(category=archive)
            await ctx.message.channel.send("This channel has been archived.")
            message_count = 2
            if(readonly == True):
                await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
                await ctx.message.channel.send("This channel is now read-only.")
                message_count = 3
            await clearSimple(ctx, message_count)
        else:
           await ctx.message.channel.send(f"Your archive category **{archive.name.upper()}** is full. Please make space in your archive or create a new one.")
           await clearSimple(ctx)

@bot.command()
@has_permissions(manage_guild=True)
async def delete(ctx, days):
    id = ctx.message.guild.id
    timeout = readServer(id)[2]
    if not timeout:
        await ctx.message.channel.send("Please set an inactivity timeout with `a!config` before setting a deletion timeout.")
    elif(int(days) >= timeout + 7):
        updateServer(id, delete_time=int(days))
        await ctx.message.channel.send(f"Archived channels inactive for **{days}** days will be deleted.")
    elif(int(days) == 0):
        updateServer(id, delete_time='NULL')
        await ctx.message.channel.send("Archived channels will no longer be deleted.")
    else:
        await ctx.message.channel.send(f"Deletion time must be greater than {timeout+7}.")
        await clearSimple(ctx)


@config.error
@archive.error
@freeze.error
@delete.error
@lock.error
@unlock.error
async def permissions_error(ctx, error):
    if isinstance(error, MissingPermissions):
        await ctx.message.channel.send("You don't have permission to do this!")
        await clearSimple(ctx)

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

                # Check if Archie has the permissions to manage this channel
                bot_member = guild.get_member(bot.user.id)
                bot_role = bot_member.roles[0]
                if(not bot_role.is_bot_managed()):
                    for role in bot_member.roles:
                        if(role.is_bot_managed()):
                            bot_role = role
                permissions = channel.overwrites_for(bot_role).manage_channels
               
                try:    # If the channel is in a text channel that is not frozen
                    if(permissions != False and str(channel.type) == 'text' and (channel.category == None or not (channel.category.name in permanent_categories))):

                        # Code to delete inactive channels
                        overwrite = channel.overwrites_for(guild.default_role)
                        if(channel.category != None and channel.category.name == server[1] and not overwrite.send_messages == False): # If the channel is in the archive and is not readonly

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
                                pass
                        
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
                    print(channel.name)
                    # await logChannel.send("Error in archiving channels. Please set up an archive category and a timeout with `a!config`.")
                    if not isinstance(e, discord.errors.Forbidden) and not isinstance(e, discord.errors.NotFound):
                        if not error:
                            await logChannel.send("Could not auto-archive. Please set up an archive category and a timeout with `a!config`.")
                            error = True
                    print(e)
            
            if archiveIsFull:
                    logChannel.send(f"Your archive category **{archive.name.upper()}** is full. Please make space in your archive or create a new one.")


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
        previous_message = None
        if(len(history) > 1):
            previous_message = history[1]
        # If the message is in a category and 
        # the category name is the archive and 
        # the message was sent by the user and
        # the message is not a response to the bot (if the user sends a message after the bot, the message must not be a question or an embed)
        # or, if it is a response to the bot, the question has timed out
        # And the message is not a command

        if previous_message:
            previous_content = previous_message.content

            if(len(previous_message.embeds) != 0):
                previous_content = previous_message.embeds[0].description

        if message.channel.category != None and \
        message.channel.category.name == archive.name and \
        message.author != bot.user and \
        (previous_message == None or \
        (previous_message.author != bot.user or \
        (previous_message.author == bot.user and not "?" in previous_content and not "enter" in previous_content.lower()) or \
        getTimeSince(previous_message) >= 20)) and \
        message.content[:2] != "a!":

            delete_until = await message.channel.send("This channel has been archived! Which category would you like to restore it to?")
            delete_from = None

            # Get the category we want to restore the channel to and move channel
            cat_name = await inputCat(ctx, True)
            if cat_name:
                await message.channel.edit(category=getCategory(cat_name, ctx))
                delete_from = await message.channel.send("Channel restored to **" + cat_name.upper() + "**.")
            
            overwrite = message.channel.overwrites_for(message.guild.default_role)
            if(overwrite.send_messages == False):
                await unlock(ctx)
            
            if(delete_from == None):
                history = await ctx.message.channel.history(limit=1).flatten()
                if(len(history) > 0):
                    delete_from = history[0]

            await clearMessages(ctx, delete_from, delete_until)
        
        await bot.process_commands(message) # Process commands
    
    except: # If an archive category doesn't exist, just process possible commands
        await bot.process_commands(message)

# autoArchive.start() # Start 24-hour auto-archiver
bot.run(TOKEN)
import discord
from discord.ext import commands, tasks
import requests
import os
import zipfile
import logging
import shutil
import aiohttp
import json
from datetime import datetime, timedelta
from collections import deque

intents = discord.Intents.all()

# Configure logging
logging.basicConfig(level=logging.INFO)  # Adjust log level as needed
logger = logging.getLogger(__name__)

bot = commands.Bot(command_prefix='/', intents=intents)  # Bot command prefix

USER_DATA_FILE = 'user_data.json'
isshonk_queue = deque()
blahaj_queue = {}

# Load user data from JSON file
def load_user_data():
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, 'r') as file:
            return json.load(file)
    return {}

# Save user data to JSON file
def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as file:
        json.dump(data, file, indent=4)

user_data = load_user_data()

# Ensure user data exists for a specific user
def ensure_user_data(user_id):
    if str(user_id) not in user_data:
        user_data[str(user_id)] = {
            'points': 0,
            'premium': False,
            'banned': False,
            'isshonk_uses': 0,
            'isshonk_reset': '',
            'daily_reset': '',
            'shonks': []
        }
        save_user_data(user_data)
    else:
        # Ensure all keys are present
        user_data[str(user_id)].setdefault('points', 0)
        user_data[str(user_id)].setdefault('premium', False)
        user_data[str(user_id)].setdefault('banned', False)
        user_data[str(user_id)].setdefault('isshonk_uses', 0)
        user_data[str(user_id)].setdefault('isshonk_reset', '')
        user_data[str(user_id)].setdefault('daily_reset', '')
        user_data[str(user_id)].setdefault('shonks', [])
        save_user_data(user_data)

# Add points to user
def add_points(user_id, points):
    ensure_user_data(user_id)
    user_data[str(user_id)]['points'] += points
    save_user_data(user_data)

# Check if user has premium status
def is_premium(user_id):
    ensure_user_data(user_id)
    return user_data[str(user_id)]['premium']

# Check if user is banned
def is_banned(user_id):
    ensure_user_data(user_id)
    return user_data[str(user_id)]['banned']

# Reset monthly usage for non-premium users
def reset_isshonk_uses(user_id):
    now = datetime.utcnow()
    if user_data[str(user_id)]['isshonk_reset']:
        reset_date = datetime.fromisoformat(user_data[str(user_id)]['isshonk_reset'])
        if now > reset_date + timedelta(days=30):
            user_data[str(user_id)]['isshonk_uses'] = 0
            user_data[str(user_id)]['isshonk_reset'] = now.isoformat()
            save_user_data(user_data)
    else:
        user_data[str(user_id)]['isshonk_reset'] = now.isoformat()
        save_user_data(user_data)

@tasks.loop(minutes=10)  # Adjust the interval as needed
async def download_blahaj_images():
    try:
        async with aiohttp.ClientSession() as session:
            # Fetch a random Blahaj image from the API
            async with session.get("https://blahaj.transgirl.dev/images/random") as response:
                response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

                data = await response.json()
                image_url = data["url"]

                # Download the image
                async with session.get(image_url) as image_response:
                    image_response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

                    # Ensure 'storage' directory exists
                    if not os.path.exists('storage'):
                        os.makedirs('storage')

                    # Save the image to storage
                    filename = image_url.split('/')[-1]  # Extract filename from URL
                    filepath = os.path.join('storage', filename)

                    with open(filepath, 'wb') as f:
                        f.write(await image_response.read())

                    logger.info(f"Downloaded and saved: {filename}")

    except aiohttp.ClientError as e:
        logger.error(f"Error occurred while fetching Blahaj image: {e}")
    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    # Start the background task to download Blahaj images
    download_blahaj_images.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    user_id = str(message.author.id)

    # Check if the user is banned
    if is_banned(user_id):
        return

    # Award points for each message
    add_points(message.author.id, 1)

    await bot.process_commands(message)

@bot.command(name='balance')
async def balance_command(ctx):
    ensure_user_data(ctx.author.id)
    if is_banned(ctx.author.id):
        await ctx.send("You are banned from using this bot.")
        return

    points = user_data[str(ctx.author.id)]['points']
    await ctx.send(f"You have {points} :3's.")

@bot.command(name='isshonk')
async def isshonk_command(ctx, option: str = None):
    ensure_user_data(ctx.author.id)
    user_id = str(ctx.author.id)

    if is_banned(user_id):
        await ctx.send("You are banned from using this bot.")
        return

    if option == '-q':
        # Check queue position
        if user_id in [item[0] for item in isshonk_queue]:
            position = [item[0] for item in isshonk_queue].index(user_id) + 1
            await ctx.send(f"You are position {position} in the isshonk queue.")
        else:
            await ctx.send("You have no queued isshonk request.")
        return

    # Reset uses if necessary
    reset_isshonk_uses(user_id)

    if not is_premium(user_id) and user_data[user_id]['isshonk_uses'] >= 5:
        await ctx.send("You have reached the monthly limit of 5 uses for this command.")
        return

    if not ctx.message.attachments:
        await ctx.send("You need to attach an image to use this command.")
        return

    if user_id in [item[0] for item in isshonk_queue]:
        await ctx.send("You already have a queued isshonk request.")
        return

    image_url = ctx.message.attachments[0].url

    # Add to queue
    isshonk_queue.append((user_id, image_url))
    await ctx.send("Your isshonk request has been queued.")

    # Process queue
    while isshonk_queue:
        current_user_id, current_image_url = isshonk_queue.popleft()

        if current_user_id == user_id:
            # Prompt in the console for a response
            response = input("Is this a Shonk? (yes/no): ").strip().lower()

            if response == 'yes':
                await ctx.send("Yes, this is a Shonk!")
            elif response == 'no':
                await ctx.send("No, this is not a Shonk.")
            else:
                await ctx.send("Invalid response received. Please try again.")

            # Update usage count
            if not is_premium(user_id):
                user_data[user_id]['isshonk_uses'] += 1
                save_user_data(user_data)

@bot.command(name='blahaj')
async def blahaj_command(ctx, option: str = None):
    ensure_user_data(ctx.author.id)
    user_id = str(ctx.author.id)

    if is_banned(user_id):
        await ctx.send("You are banned from using this bot.")
        return

    try:
        # Fetch a random Blahaj image from the API
        response = requests.get("https://blahaj.transgirl.dev/images/random")
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        data = response.json()
        image_url = data["url"]

        # Ensure 'storage' directory exists
        if not os.path.exists('storage'):
            os.makedirs('storage')

        # Save the image to storage
        filename = image_url.split('/')[-1]  # Extract filename from URL
        filepath = os.path.join('storage', filename)

        with open(filepath, 'wb') as f:
            f.write(response.content)

        await ctx.send(image_url)

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error occurred: {e}")
        await ctx.send(f"Failed to fetch Blahaj image. HTTP error occurred: {e}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error occurred: {e}")
        await ctx.send(f"Failed to fetch Blahaj image. Request error occurred: {e}")

    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        await ctx.send(f"Failed to fetch Blahaj image. An unexpected error occurred: {e}")

@bot.command(name='shonklib')
async def shonklib_command(ctx, option: str = None):
    ensure_user_data(ctx.author.id)
    user_id = str(ctx.author.id)

    if is_banned(user_id):
        await ctx.send("You are banned from using this bot.")
        return

    try:
        if option == '-d':
            # Zip the contents of the 'storage' directory
            files = []
            for root, dirs, filenames in os.walk('storage'):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    file_size = os.path.getsize(file_path)
                    files.append((file_path, file_size))

            # Sort files by size in descending order
            files.sort(key=lambda x: x[1], reverse=True)

            # Partition files into zip parts under 8MB each
            partitions = []
            for file_path, file_size in files:
                placed = False
                for partition in partitions:
                    if partition['size'] + file_size <= 8 * 1024 * 1024:  # 8MB
                        partition['files'].append(file_path)
                        partition['size'] += file_size
                        placed = True
                        break
                if not placed:
                    new_partition = {'files': [file_path], 'size': file_size}
                    partitions.append(new_partition)

            # Ensure 'temp_storage' directory exists
            if not os.path.exists('temp_storage'):
                os.makedirs('temp_storage')

            # Create zip files for each partition
            for i, partition in enumerate(partitions, start=1):
                zip_filename = f'shonklib_part_{i}.zip'
                zip_filepath = os.path.join('temp_storage', zip_filename)
                with zipfile.ZipFile(zip_filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in partition['files']:
                        zipf.write(file_path, arcname=os.path.relpath(file_path, 'storage'))

            # Send each zip part as an attachment
            for zip_filepath in os.listdir('temp_storage'):
                await ctx.send(file=discord.File(os.path.join('temp_storage', zip_filepath)))

            # Clean up: delete temporary directory after sending
            shutil.rmtree('temp_storage')

        elif option == '-c':
            # Count the number of Blahaj photos in the storage folder
            num_photos = sum([len(files) for r, d, files in os.walk('storage')])
            await ctx.send(f"There are {num_photos} Blahaj photos in the storage folder.")

        else:
            await ctx.send("Invalid option. Use /shonklib -d to download or /shonklib -c to count the Blahaj photos.")

    except Exception as e:
        logger.error(f"Failed to create/send ShonkLib archive: {e}")
        await ctx.send("Failed to create/send ShonkLib archive.")

@bot.command(name='daily')
async def daily_command(ctx):
    ensure_user_data(ctx.author.id)
    user_id = str(ctx.author.id)

    if is_banned(user_id):
        await ctx.send("You are banned from using this bot.")
        return

    now = datetime.utcnow()

    if user_data[user_id].get('daily_reset', ''):
        reset_date = datetime.fromisoformat(user_data[user_id]['daily_reset'])
        if now < reset_date + timedelta(days=1):
            await ctx.send("You have already collected your daily Blahaj picture. Try again tomorrow!")
            return

    try:
        # Fetch a random Blahaj image from the API
        response = requests.get("https://blahaj.transgirl.dev/images/random")
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        data = response.json()
        image_url = data["url"]

        # Ensure 'storage' directory exists
        if not os.path.exists('storage'):
            os.makedirs('storage')

        # Save the image to storage
        filename = image_url.split('/')[-1]  # Extract filename from URL
        filepath = os.path.join('storage', filename)

        with open(filepath, 'wb') as f:
            f.write(response.content)

        # Update user data
        user_data[user_id]['daily_reset'] = now.isoformat()
        user_data[user_id]['shonks'].append(filename)
        save_user_data(user_data)

        await ctx.send(image_url)

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error occurred: {e}")
        await ctx.send(f"Failed to fetch Blahaj image. HTTP error occurred: {e}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Request error occurred: {e}")
        await ctx.send(f"Failed to fetch Blahaj image. Request error occurred: {e}")

    except Exception as e:
        logger.error(f"Unexpected error occurred: {e}")
        await ctx.send(f"Failed to fetch Blahaj image. An unexpected error occurred: {e}")

@bot.command(name='shonkcollect')
async def shonkcollect_command(ctx):
    ensure_user_data(ctx.author.id)
    user_id = str(ctx.author.id)

    if is_banned(user_id):
        await ctx.send("You are banned from using this bot.")
        return

    shonks_collected = len(user_data[user_id]['shonks'])
    await ctx.send(f"You have collected {shonks_collected} Shonks.")

# Replace 'TOKEN' with your actual bot token from Discord Developer Portal
bot.run('TOKEN')

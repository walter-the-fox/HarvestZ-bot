import discord
import aiohttp
import datetime
import fsonbase
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

from config import *

import sqlite3

database = fsonbase.fsonbase(r"database")
db_applicants = database.connect("applicants")
db_accepted = database.connect("accepted")

class SQL:
    def __init__(self, database):
        self.connection = sqlite3.connect(database)
        self.cursor = self.connection.cursor()

    def check_same_steam_id(self, steam_id: str) -> bool:
        with self.connection:
            return bool(len(self.cursor.execute("SELECT * FROM whitelist WHERE steamid = ?", (steam_id,)).fetchall()))

    def check_same_nickname(self, nickname: str) -> bool:
        with self.connection:
            return bool(len(self.cursor.execute("SELECT * FROM whitelist WHERE username = ?", (nickname,)).fetchall()))
    def close(self):
        self.connection.close()

class ExtraEmbed(discord.Embed):
    def __init__(self, user: discord.User | discord.Member, **kwargs):
        super().__init__(**kwargs)
        #self.color = discord.Color.embed_background()
        try:
            #self.set_thumbnail(url=user.display_avatar.url)
            pass
        except:
            pass


async def parse_steam_id(url: str) -> int:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}?xml=1") as response:
                root = ET.fromstring(await response.text())
                return int(root.find('steamID64').text)
    except:
        return 0

async def is_public(url: str) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}?xml=1") as response:
                root = ET.fromstring(await response.text())
                return root.find('privacyState').text == "public"
    except:
        return False


class SteamValidator:
    def __init__(self):
        pass

    async def get_steam_level(self, url: str) -> int:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                try:
                    data = await response.text()
                    bs_data = BeautifulSoup(data, 'html.parser')
                    return int(bs_data.find("span", {"class": "friendPlayerLevelNum"}).text)
                except Exception as e:
                    return 0

    async def get_played_games(self, url: str) -> int:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}/games/?tab=all&xml=1") as response:
                    root = ET.fromstring(await response.text())
                    return len(list(root.find("games").findall("game")))

        except Exception as e:
            return 0

    async def is_limited(self, url: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}?xml=1") as response:
                    root = ET.fromstring(await response.text())
                    return bool(int(root.find('isLimitedAccount').text))
        except:
            return False

    async def is_vac_banned(self, url: str) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}?xml=1") as response:
                    root = ET.fromstring(await response.text())
                    return bool(int(root.find('vacBanned').text))
        except:
            return False

    async def check_profile(self, url: str) -> bool:
        return (await self.get_steam_level(url) > 4 and
                await self.get_played_games(url) > 3 and
                not await self.is_limited(url) and
                not await self.is_vac_banned(url))


validator = SteamValidator()


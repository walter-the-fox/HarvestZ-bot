import asyncio
import shutil
import os
from sys import exception

import discord

from utils import *

from discord import slash_command
from discord.ext import commands, tasks
from aiomcrcon import Client


class Whitelist(commands.Cog):
    def __init__(self, client):
        self.client: discord.Bot = client
        self.logs_channel: None | discord.TextChannel = None
        self.validate_channel: None | discord.TextChannel = None

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"cog > {self.__class__.__name__} < is loaded")
        self.logs_channel = self.client.get_channel(LOGS_CHANNEL)
        self.validate_channel = self.client.get_channel(VALIDATE_CHANNEL)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not isinstance(interaction.custom_id, str): return

        if interaction.custom_id == "button_register":
            if db_applicants.find_one_document({"user_id": interaction.user.id}):
                await interaction.response.send_message(
                    embed=ExtraEmbed(interaction.user, title="You have already submitted an application!",
                                     description=f"Wait until manual verification is complete",
                                     color=discord.Color.brand_red()),
                    ephemeral=True)
                return

            if db_accepted.find_one_document({"user_id": interaction.user.id}):
                await interaction.response.send_message(
                    embed=ExtraEmbed(interaction.user, title="You are already registered!",
                                     description=f"Your application has been approved",
                                     color=discord.Color.brand_green()),
                    ephemeral=True)
                return

            modal = discord.ui.Modal(title="Registration Form")
            modal.add_item(
                discord.ui.InputText(label="Steam Profile Link",
                                     placeholder="https://steamcommunity.com/profiles/example", min_length=27))
            modal.add_item(
                discord.ui.InputText(label="Username", placeholder="Specify desired username", min_length=3,
                                     max_length=16))
            modal.add_item(
                discord.ui.InputText(label="Password", placeholder="Specify desired password", min_length=3,
                                     max_length=32))

            async def modal_callback(modal_interaction: discord.Interaction):
                profile = modal_interaction.data["components"][0]["components"][0]["value"]
                nickname = modal_interaction.data["components"][1]["components"][0]["value"]
                password = modal_interaction.data["components"][2]["components"][0]["value"]
                if not re.match(r"https:\/\/steamcommunity\.com\/(profiles\/7656\d{13}|id\/[\w-]{3,32})", profile):
                    await modal_interaction.response.send_message(
                        embed=ExtraEmbed(interaction.user, title="Invalid Steam profile link!",
                                         description=f"Example link:\nhttps://steamcommunity.com/profiles/76561198065447572",
                                         color=discord.Color.brand_red()), ephemeral=True)
                    return

                if not re.match(r"[a-zA-Z0-9-_]+", nickname):
                    await modal_interaction.response.send_message(
                        embed=ExtraEmbed(interaction.user, title="Invalid username!",
                                         description="Username should contain only latin symbols and numbers",
                                         color=discord.Color.brand_red()), ephemeral=True)
                    return

                if not re.match(r"[a-zA-Z0-9-_]+", password):
                    await modal_interaction.response.send_message(
                        embed=ExtraEmbed(interaction.user, title="Invalid password!",
                                         description="Password should contain only latin symbols and numbers",
                                         color=discord.Color.brand_red()), ephemeral=True)
                    return

                if not await is_public(profile):
                    await modal_interaction.response.send_message(
                        embed=ExtraEmbed(interaction.user, title="Your profile is private!",
                                         description="Change it to public and try again",
                                         color=discord.Color.brand_red()), ephemeral=True)
                    return

                steam_id = await parse_steam_id(profile)
                shutil.copy(f"{SERVER_DIR}/{SERVERNAME}.db", f"temp/{SERVERNAME}.db")
                database = SQL(f'temp/{SERVERNAME}.db')
                if database.check_same_steam_id(str(steam_id)):
                    await modal_interaction.response.send_message(
                        embed=ExtraEmbed(interaction.user, title="Steam ID is already in use!",
                                         description=f"Player with ID [{steam_id}]({profile}) is already registered\n",
                                         color=discord.Color.brand_red()),
                        ephemeral=True)
                    return
                if database.check_same_nickname(nickname):
                    await modal_interaction.response.send_message(
                        embed=ExtraEmbed(interaction.user, title="Username is already in use!",
                                         description=f"Player **{nickname}** is already registered",
                                         color=discord.Color.brand_red()),
                        ephemeral=True)
                    return
                database.close()

                await modal_interaction.response.defer()

                if not await validator.check_profile(profile):
                    db_applicants.insert_document({"user_id": interaction.user.id})
                    embed = discord.Embed(title="**Manual check required!**",
                                          description=f"""> **[Steam profile]({profile}) of user {interaction.user.mention} looks suspicious**
> **Use the information below to verify it**
⠀
""",
                                          color=discord.Color.orange(), timestamp=datetime.datetime.now())

                    played_games = await validator.get_played_games(profile)
                    if played_games == 0: played_games = "Hidden"

                    embed.add_field(name="Account level:", value=f"```{await validator.get_steam_level(profile)}```")
                    embed.add_field(name="Games played:", value=f"```{played_games}```")
                    embed.add_field(name="VAC banned:", value=f"```{await validator.is_vac_banned(profile)}```")
                    embed.add_field(name="Specified username:", value=f"```{nickname}```", inline=False)
                    embed.add_field(name="Specified password:", value=f"```{password}```", inline=False)
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(label="Accept",
                                                    custom_id=f"accept@@{interaction.user.id}@@{steam_id}@@{nickname}@@{password}",
                                                    style=discord.ButtonStyle.green))
                    view.add_item(discord.ui.Button(label="Decline", custom_id=f"decline@@{interaction.user.id}",
                                                    style=discord.ButtonStyle.red))
                    await self.validate_channel.send(f"<@&{STAFF_ROLE}>", embed=embed, view=view)
                    await modal_interaction.followup.send(
                        embed=ExtraEmbed(interaction.user, title="Additional check required!",
                                         description="Your application has been sent to manual check\nWait for the administrations response...",
                                         color=discord.Color.orange()),
                        ephemeral=True)
                    return

                try:
                    client = Client(RCON_HOST, RCON_PORT, RCON_PWD)
                    await client.connect()
                    response = await client.send_cmd(f'adduser "{nickname}" "{password}" "{steam_id}"')
                    await client.close()
                    await modal_interaction.followup.send(
                        embed=ExtraEmbed(interaction.user, title="Application approved automatically!",
                                         description=f"You have been successfully added to the whitelist",
                                         color=discord.Color.brand_green()),
                        ephemeral=True)

                    embed = discord.Embed(title="**Application approved automatically!**",
                                          description=f"""**[Steam profile]({profile}) of user {interaction.user.mention} looks normal**""",
                                          color=discord.Color.brand_green(), timestamp=datetime.datetime.now())

                    embed.add_field(name="Account level:", value=f"```{await validator.get_steam_level(profile)}```")
                    embed.add_field(name="Games played:", value=f"```{await validator.get_played_games(profile)}```")
                    embed.add_field(name="VAC banned:", value=f"```{await validator.is_vac_banned(profile)}```")
                    embed.add_field(name="Specified username:", value=f"```{nickname}```", inline=False)
                    await self.logs_channel.send(embed=embed)

                    try:
                        embed = discord.Embed(title=f"Your application has been approved!",
                                              description=f"**Use the information below to connect to the server:**",
                                              color=discord.Color.brand_green())
                        embed.add_field(name="IP", value=f"```38.46.216.201```", inline=True)
                        embed.add_field(name="Port", value=f"```25652```", inline=True)
                        embed.add_field(name="Username", value=f"```{nickname}```", inline=False)
                        embed.add_field(name="Password (click to show)", value=f"||```{password}```||", inline=False)
                        await interaction.user.send(embed=embed)
                    except:
                        pass

                    db_accepted.insert_document({"user_id": interaction.user.id})
                except Exception as e:
                    await modal_interaction.followup.send(
                        embed=ExtraEmbed(interaction.user, title="Something went wrong!",
                                         description=f"Error while adding player to whitelist",
                                         color=discord.Color.brand_red()), ephemeral=True)
                    raise e

            modal.callback = modal_callback
            await interaction.response.send_modal(modal)
        elif interaction.custom_id.startswith("accept"):
            action, discord_id, steam_id, nickname, password = interaction.custom_id.split("@@")
            discord_id = int(discord_id)
            steam_id = int(steam_id)
            try:
                client = Client(RCON_HOST, RCON_PORT, RCON_PWD)
                await client.connect()
                response = await client.send_cmd(f'adduser "{nickname}" "{password}" "{steam_id}"')
                await client.close()
            except:
                await interaction.response.send_message(embed=ExtraEmbed(interaction.user, title="Something went wrong!",
                                                                         description=f"Error while adding player to whitelist",
                                                                         color=discord.Color.brand_red()), ephemeral=True)
                return

            old_embed = interaction.message.embeds[0]
            embed = discord.Embed(title=f"Application approved by {interaction.user.display_name}!",
                                  description=old_embed.description, color=discord.Color.brand_green(),
                                  timestamp=datetime.datetime.now(), fields=old_embed.fields)
            await interaction.response.edit_message(embed=embed, view=None)

            embed = discord.Embed(title=f"Your application has been approved!",
                                  description=f"**Use the information below to connect to the server:**",
                                  color=discord.Color.brand_green())
            embed.add_field(name="IP", value=f"```38.46.216.201```", inline=True)
            embed.add_field(name="Port", value=f"```25652```", inline=True)
            embed.add_field(name="Username", value=f"```{nickname}```", inline=False)
            embed.add_field(name="Password (click to show)", value=f"||```{password}```||", inline=False)

            member = await interaction.guild.fetch_member(discord_id)
            try:
                await member.send(embed=embed)
            except:
                pass

            db_applicants.delete_document({"user_id": member.id})
            db_accepted.insert_document({"user_id": member.id})


        elif interaction.custom_id.startswith("decline"):
            action, discord_id = interaction.custom_id.split("@@")

            old_embed = interaction.message.embeds[0]
            embed = discord.Embed(title=f"Application declined by {interaction.user.display_name}!",
                                  description=old_embed.description, color=discord.Color.brand_red(),
                                  timestamp=datetime.datetime.now(), fields=old_embed.fields)
            await interaction.response.edit_message(embed=embed, view=None)

            embed = discord.Embed(title=f"Your application has been declined!",
                                  description=f"If you disagree with the decision, [open a ticket](https://discord.com/channels/793827264508198943/1263183350512881734)",
                                  color=discord.Color.brand_red())

            member = await interaction.guild.fetch_member(int(discord_id))
            try:
                await member.send(embed=embed)
            except:
                pass

            db_applicants.delete_document({"user_id": member.id})

    @slash_command(description="Set up registration button", guild_only=True)
    async def setup(self, ctx: discord.ApplicationContext):
        if not ctx.user.guild_permissions.administrator:
            await ctx.respond("No permission", ephemeral=True)
            return
        embed_upper = discord.Embed(color=discord.Color.embed_background(),
                                    image="https://media.discordapp.net/attachments/1291477355801346090/1292184989332668468/image.png?ex=6702d08d&is=67017f0d&hm=7e5192c7e6bca93336dc8908f33e142f8c56ee73f9264217c3d5e4525e3c0b0e&=&format=webp&quality=lossless")
        embed_lower = discord.Embed(title="✓ ** Registration Form**", description="""```Read the post before applying!```
> **We use a whitelist on our server for player safety.**
> **To get on it, you need to:**

⠀• ⠀**Have public profile on Steam without VAC bans**
⠀• ⠀**Click the button below and fill out the form**

⠀**[How to make my profile public?](https://help.steampowered.com/en/faqs/view/588C-C67D-0251-C276)**
⠀**[What is steam profile link?](https://blog.replug.io/how-to-find-steam-url/)**

*The bot automatically reviews requests and responds to them⠀⠀⠀⠀
In some cases, manual verification may be required*
⠀""", color=discord.Color.embed_background())
        embed_lower.set_footer(text="Accounts that do not meet the requirements will be automatically rejected")
        embeds = [embed_upper, embed_lower]
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(label="Register now!", custom_id="button_register", style=discord.ButtonStyle.green))
        await ctx.channel.send(embeds=embeds, view=view)
        await ctx.respond("Done!", ephemeral=True)


def setup(client):
    client.add_cog(Whitelist(client))
